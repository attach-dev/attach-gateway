"""
Attach Gateway - Identity & Memory side-car for LLM engines

Add OIDC SSO, agent-to-agent handoff, and pluggable memory to any Python project.
"""

__version__ = "0.2.1"
__author__ = "Hammad Tariq"
__email__ = "hammad@attach.dev"

# Clean imports - no sys.path hacks needed since everything will be in the wheel
from .gateway import create_app, AttachConfig

__all__ = ["create_app", "AttachConfig", "__version__"] 