import os

import weaviate
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from a2a.routes import router as a2a_router
from auth.oidc import verify_jwt  # Fixed: was auth.jwt, now auth.oidc
from logs import router as logs_router
from mem import write as mem_write  # Import memory write function
from middleware.auth import jwt_auth_mw  # ← your auth middleware
from middleware.session import session_mw  # ← generates session-id header
from proxy.engine import router as proxy_router

# At the top, make the import conditional
try:
    from middleware.quota import TokenQuotaMiddleware
    QUOTA_AVAILABLE = True
except ImportError:
    QUOTA_AVAILABLE = False

# Memory router
mem_router = APIRouter(prefix="/mem", tags=["memory"])


@mem_router.get("/events")
async def get_memory_events(request: Request, limit: int = 10):
    """Fetch recent MemoryEvent objects from Weaviate"""
    try:
        # Get user info from request state (set by jwt_auth_mw middleware)
        user_sub = getattr(request.state, "sub", None)
        if not user_sub:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Use the exact same client setup as demo_view_memory.py
        client = weaviate.Client("http://localhost:6666")

        # Test connection first
        if not client.is_ready():
            raise HTTPException(status_code=503, detail="Weaviate is not ready")

        # Check schema the same way as demo_view_memory.py
        try:
            schema = client.schema.get()
            classes = {c["class"] for c in schema.get("classes", [])}

            if "MemoryEvent" not in classes:
                return {"data": {"Get": {"MemoryEvent": []}}}
        except Exception:
            return {"data": {"Get": {"MemoryEvent": []}}}

        # Query with descending order by timestamp (newest first)
        result = (
            client.query.get(
                "MemoryEvent",
                ["timestamp", "event", "user", "state"]
            )
            .with_additional(["id"])
            .with_limit(limit)
            .with_sort([{"path": ["timestamp"], "order": "desc"}])
            .do()
        )

        # Check for GraphQL errors like demo_view_memory.py does
        if "errors" in result:
            raise HTTPException(
                status_code=500, detail=f"GraphQL error: {result['errors']}"
            )

        if "data" not in result:
            raise HTTPException(status_code=500, detail="No data in response")

        events = result["data"]["Get"]["MemoryEvent"]

        # Add the result field from the raw objects for richer display
        try:
            raw_objects = client.data_object.get(class_name="MemoryEvent", limit=limit)

            # Create a mapping of IDs to full objects
            id_to_full_object = {}
            for obj in raw_objects.get("objects", []):
                obj_id = obj.get("id")
                if obj_id:
                    id_to_full_object[obj_id] = obj.get("properties", {})

            # Enrich the GraphQL results with data from raw objects
            for event in events:
                event_id = event.get("_additional", {}).get("id")
                if event_id and event_id in id_to_full_object:
                    full_props = id_to_full_object[event_id]
                    # Add the result field if it exists
                    if "result" in full_props:
                        event["result"] = full_props["result"]
                    # Add other useful fields
                    for field in ["event", "session_id", "task_id", "user"]:
                        if field in full_props:
                            event[field] = full_props[field]
        except Exception:
            pass  # Silently fail if we can't enrich with raw object data

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching memory events: {str(e)}"
        )


middlewares = [
    # ❶ CORS first (so it executes last and handles responses properly)
    Middleware(CORSMiddleware,
               allow_origins=["http://localhost:9000", "http://127.0.0.1:9000"],
               allow_methods=["*"],
               allow_headers=["*"],
               allow_credentials=True),
    # ❷ Auth middleware
    Middleware(BaseHTTPMiddleware, dispatch=jwt_auth_mw),
    # ❸ Session middleware  
    Middleware(BaseHTTPMiddleware, dispatch=session_mw),
]

# Only add quota middleware if tiktoken is available AND user configured it
if QUOTA_AVAILABLE and os.getenv("MAX_TOKENS_PER_MIN"):
    middlewares.append(Middleware(TokenQuotaMiddleware))

# Create app without middleware first
app = FastAPI(title="attach-gateway", middleware=middlewares)

@app.get("/auth/config")
async def auth_config():
    return {
        "domain": os.getenv("AUTH0_DOMAIN"),
        "client_id": os.getenv("AUTH0_CLIENT"),
        "audience": os.getenv("OIDC_AUD"),
    }

# Add middleware after routes are defined
app.include_router(a2a_router, prefix="/a2a")
app.include_router(logs_router)
app.include_router(mem_router)
app.include_router(proxy_router)  # ← ADD THIS BACK
