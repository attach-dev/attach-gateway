"""
Main gateway factory - clean imports from packaged modules
"""

import os
from typing import Optional

import weaviate
from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from a2a.routes import router as a2a_router

# Clean relative imports
from auth import verify_jwt
from auth.oidc import _require_env
#from logs import router as logs_router
from mem import get_memory_backend
from middleware.auth import jwt_auth_mw
from middleware.session import session_mw
from proxy.engine import router as proxy_router

# Import version from parent package
from . import __version__

mem_router = APIRouter(prefix="/mem", tags=["memory"])


@mem_router.get("/events")
async def get_memory_events(request: Request, limit: int = 10):
    """Fetch recent MemoryEvent objects from Weaviate."""
    try:
        user_sub = getattr(request.state, "sub", None)
        if not user_sub:
            raise HTTPException(status_code=401, detail="User not authenticated")

        client = weaviate.Client(os.getenv("WEAVIATE_URL", "http://localhost:6666"))
        if not client.is_ready():
            raise HTTPException(status_code=503, detail="Weaviate is not ready")

        try:
            schema = client.schema.get()
            classes = {c["class"] for c in schema.get("classes", [])}
            if "MemoryEvent" not in classes:
                return {"data": {"Get": {"MemoryEvent": []}}}
        except Exception:
            return {"data": {"Get": {"MemoryEvent": []}}}

        result = (
            client.query.get("MemoryEvent", ["timestamp", "role", "content"])
            .with_additional(["id"])
            .with_limit(limit)
            .with_sort([{"path": ["timestamp"], "order": "desc"}])
            .do()
        )

        if "errors" in result or "data" not in result:
            raise HTTPException(status_code=500, detail="Error fetching events")

        events = result["data"]["Get"]["MemoryEvent"]
        try:
            raw_objects = client.data_object.get(class_name="MemoryEvent", limit=limit)
            id_map = {
                obj.get("id"): obj.get("properties", {})
                for obj in raw_objects.get("objects", [])
            }
            for event in events:
                eid = event.get("_additional", {}).get("id")
                if eid in id_map:
                    props = id_map[eid]
                    if "result" in props:
                        event["result"] = props["result"]
                    for field in ["event", "session_id", "task_id", "user"]:
                        if field in props:
                            event[field] = props[field]
        except Exception:
            pass

        return result
    except Exception as e:  # pragma: no cover - error path
        raise HTTPException(
            status_code=500, detail=f"Error fetching memory events: {e}"
        )


class AttachConfig(BaseModel):
    """Configuration for Attach Gateway"""

    oidc_issuer: str
    oidc_audience: str
    engine_url: str = "http://localhost:11434"
    mem_backend: str = "none"
    weaviate_url: Optional[str] = None
    auth0_domain: Optional[str] = None
    auth0_client: Optional[str] = None


def create_app(config: Optional[AttachConfig] = None) -> FastAPI:
    """
    Create a FastAPI app with Attach Gateway functionality

    Usage:
        from attach import create_app, AttachConfig

        config = AttachConfig(
            oidc_issuer="https://your-domain.auth0.com",
            oidc_audience="your-api-identifier"
        )
        app = create_app(config)
    """
    if config is None:
        issuer = os.getenv("OIDC_ISSUER") or _require_env("OIDC_ISSUER")
        audience = os.getenv("OIDC_AUD") or _require_env("OIDC_AUD")
        config = AttachConfig(
            oidc_issuer=issuer,
            oidc_audience=audience,
            engine_url=os.getenv("ENGINE_URL", "http://localhost:11434"),
            mem_backend=os.getenv("MEM_BACKEND", "none"),
            weaviate_url=os.getenv("WEAVIATE_URL"),
            auth0_domain=os.getenv("AUTH0_DOMAIN"),
            auth0_client=os.getenv("AUTH0_CLIENT"),
        )

    app = FastAPI(
        title="Attach Gateway",
        description="Identity & Memory side-car for LLM engines",
        version=__version__,
    )

    # Add middleware
    app.middleware("http")(jwt_auth_mw)
    app.middleware("http")(session_mw)

    # Add routes
    app.include_router(a2a_router)
    app.include_router(proxy_router)
    #app.include_router(logs_router)
    app.include_router(mem_router)

    # Setup memory backend
    memory_backend = get_memory_backend(config.mem_backend, config)
    app.state.memory = memory_backend
    app.state.config = config

    return app
