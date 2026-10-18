from app.routes.disasters import router as disasters_router
from app.routes.zones import router as zones_router
from app.routes.resources import router as resources_router
from app.routes.dashboard import router as dashboard_router

__all__ = [
    "disasters_router",
    "zones_router",
    "resources_router",
    "dashboard_router",
]
