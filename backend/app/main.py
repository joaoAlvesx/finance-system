from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.accounts import router as accounts_router
from app.api.routes.assistant import router as assistant_router
from app.api.routes.categories import router as categories_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.planning import router as planning_router
from app.api.routes.transactions import router as transactions_router
from app.core.config import get_settings
from app.core.correlation import correlation_id_middleware
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, use_json=settings.environment == "production")
    docs_enabled = settings.environment != "production"
    application = FastAPI(
        title=settings.app_name,
        version="0.6.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID", "Authorization"],
    )
    application.middleware("http")(correlation_id_middleware)
    application.include_router(accounts_router, prefix="/api/v1")
    application.include_router(assistant_router, prefix="/api/v1")
    application.include_router(categories_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(imports_router, prefix="/api/v1")
    application.include_router(integrations_router, prefix="/api/v1")
    application.include_router(planning_router, prefix="/api/v1")
    application.include_router(transactions_router, prefix="/api/v1")
    return application


app = create_app()
