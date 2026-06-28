"""Re-export mission template context from projects.smarty.context."""
from projects.smarty.context import *  # noqa: F403
from projects.smarty.context import mission_context

__all__ = ["mission_context"]
