"""
Attach Gateway - Identity & Memory side-car for LLM engines

Add OIDC SSO, agent-to-agent handoff, and pluggable memory to any Python project.
"""

__version__ = "0.3.7"
__author__ = "Hammad Tariq"
__email__ = "hammad@attach.dev"

# Remove this line that causes early failure:
# from .gateway import create_app, AttachConfig

# Optional: Add lazy import for convenience
def create_app(*args, **kwargs):
    from .gateway import create_app as _real
    return _real(*args, **kwargs)

def AttachConfig(*args, **kwargs):
    from .gateway import AttachConfig as _real
    return _real(*args, **kwargs)

__all__ = ["create_app", "AttachConfig", "__version__"] 