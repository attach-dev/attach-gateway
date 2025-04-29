from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from proxy.engine import proxy_to_engine
from a2a.routes import router as a2a_router

from middleware.auth import jwt_auth_mw         # ← your auth middleware
from middleware.session import session_mw       # ← generates session-id header

middlewares = [
    # ❶ Auth first (executes first at request time)
    Middleware(BaseHTTPMiddleware, dispatch=jwt_auth_mw),

    # ❷ Session id second (executes after auth; sub is now available)
    Middleware(BaseHTTPMiddleware, dispatch=session_mw),
]

app = FastAPI(title="ump-gateway", middleware=middlewares)
app.include_router(a2a_router, prefix="/a2a")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# catch-all proxy (incl. /api/chat)
app.add_api_route("/{path:path}", proxy_to_engine,
                  methods=["GET", "POST", "PUT", "PATCH"])