"""FastAPI product boundary for the SignalDesk analyst workspace."""

from .app import create_app
from .config import APIConfig
from .service import SignalDeskService

__all__ = ["APIConfig", "SignalDeskService", "create_app"]
