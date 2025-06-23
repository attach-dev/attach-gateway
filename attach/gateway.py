"""
Main gateway factory - clean imports from packaged modules
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os

# Import version from parent package
from . import __version__

# Clean relative imports 
from auth import verify_jwt
from middleware.auth import jwt_auth_mw
from middleware.session import session_mw
from mem import get_memory_backend
from a2a.routes import router as a2a_router
from proxy.engine import router as proxy_router

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
        config = AttachConfig(
            oidc_issuer=os.getenv("OIDC_ISSUER"),
            oidc_audience=os.getenv("OIDC_AUD"),
            engine_url=os.getenv("ENGINE_URL", "http://localhost:11434"),
            mem_backend=os.getenv("MEM_BACKEND", "none"),
            weaviate_url=os.getenv("WEAVIATE_URL"),
            auth0_domain=os.getenv("AUTH0_DOMAIN"),
            auth0_client=os.getenv("AUTH0_CLIENT"),
        )
    
    app = FastAPI(
        title="Attach Gateway",
        description="Identity & Memory side-car for LLM engines",
        version=__version__
    )
    
    # Add middleware
    app.middleware("http")(jwt_auth_mw)
    app.middleware("http")(session_mw)
    
    # Add routes
    app.include_router(a2a_router)
    app.include_router(proxy_router)
    
    # Setup memory backend
    memory_backend = get_memory_backend(config.mem_backend, config)
    app.state.memory = memory_backend
    app.state.config = config
    
    return app 