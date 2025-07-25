import os

import weaviate
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from a2a.routes import router as a2a_router
import logs
logs_router = logs.router
from middleware.auth import jwt_auth_mw
from middleware.session import session_mw
from proxy.engine import router as proxy_router
from usage.factory import _select_backend, get_usage_backend
from usage.metrics import mount_metrics
from utils.env import int_env

try:
    from middleware.quota import TokenQuotaMiddleware
    QUOTA_AVAILABLE = True
except ImportError:
    QUOTA_AVAILABLE = False

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
            client.query.get(
                "MemoryEvent",
                ["timestamp", "event", "user", "state"],
            )
            .with_additional(["id"])
            .with_limit(limit)
            .with_sort([{"path": ["timestamp"], "order": "desc"}])
            .do()
        )

        if "errors" in result:
            raise HTTPException(
                status_code=500, detail=f"GraphQL error: {result['errors']}"
            )

        if "data" not in result:
            raise HTTPException(status_code=500, detail="No data in response")

        events = result["data"]["Get"]["MemoryEvent"]

        try:
            raw_objects = client.data_object.get(class_name="MemoryEvent", limit=limit)

            id_to_full_object = {}
            for obj in raw_objects.get("objects", []):
                obj_id = obj.get("id")
                if obj_id:
                    id_to_full_object[obj_id] = obj.get("properties", {})

            for event in events:
                event_id = event.get("_additional", {}).get("id")
                if event_id and event_id in id_to_full_object:
                    full_props = id_to_full_object[event_id]
                    if "result" in full_props:
                        event["result"] = full_props["result"]
                    for field in ["event", "session_id", "task_id", "user"]:
                        if field in full_props:
                            event[field] = full_props[field]
        except Exception:
            pass

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching memory events: {str(e)}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    backend_selector = _select_backend()
    app.state.usage = get_usage_backend(backend_selector)
    mount_metrics(app)
    
    yield
    
    if hasattr(app.state.usage, 'aclose'):
        await app.state.usage.aclose()

app = FastAPI(title="attach-gateway", lifespan=lifespan)

# Add middleware in correct order (CORS outer-most)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000", "http://127.0.0.1:9000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Only add quota middleware if available and explicitly configured
limit = int_env("MAX_TOKENS_PER_MIN", 60000)
if QUOTA_AVAILABLE and limit is not None:
    app.add_middleware(TokenQuotaMiddleware)

app.add_middleware(BaseHTTPMiddleware, dispatch=jwt_auth_mw)
app.add_middleware(BaseHTTPMiddleware, dispatch=session_mw)

@app.get("/auth/config")
async def auth_config():
    return {
        "domain": os.getenv("AUTH0_DOMAIN"),
        "client_id": os.getenv("AUTH0_CLIENT"),
        "audience": os.getenv("OIDC_AUD"),
    }

app.include_router(a2a_router, prefix="/a2a")
app.include_router(logs_router)
app.include_router(mem_router)
app.include_router(proxy_router)
