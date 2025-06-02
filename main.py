import os

from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from a2a.routes import router as a2a_router
from logs import router as logs_router
from middleware.auth import jwt_auth_mw  # ← your auth middleware
from middleware.session import session_mw  # ← generates session-id header
from proxy.engine import proxy_to_engine

middlewares = [
    # ❶ Auth first (executes first at request time)
    Middleware(BaseHTTPMiddleware, dispatch=jwt_auth_mw),
    # ❷ Session id second (executes after auth; sub is now available)
    Middleware(BaseHTTPMiddleware, dispatch=session_mw),
]

app = FastAPI(title="attach-gateway", middleware=middlewares)
app.include_router(a2a_router, prefix="/a2a")
app.include_router(logs_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# catch-all proxy (incl. /api/chat)
app.add_api_route(
    "/{path:path}", proxy_to_engine, methods=["GET", "POST", "PUT", "PATCH"]
)


@app.get("/auth/config")
async def auth_config():
    return {
        "domain": os.getenv("AUTH0_DOMAIN"),
        "client_id": os.getenv("AUTH0_CLIENT"),
        "audience": os.getenv("OIDC_AUD"),
    }
