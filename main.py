from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from src.core.database import get_db, get_engine
from src.core.migrations import run_migrations
from src.core.config import get_settings
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.routes.routes import router as auth_router
from src.features.users.infrastructure.routes.routes import router as users_router
from src.features.users.infrastructure.profile import router as profile_router
from src.features.roles.infrastructure.routes.routes import router as roles_router
from src.features.animals.infrastructure.decisions import router as decisions_router
from src.features.animals.infrastructure.decision_board import router as decision_board_router
from src.features.animals.infrastructure.physical_evaluations import router as physical_router
from src.features.animals.infrastructure.routes import router as animals_router
from src.features.animals.infrastructure.rectifications import router as rectifications_router
from src.features.animals.infrastructure.timeline import router as timeline_router
from src.features.organization.infrastructure.routes import router as organization_router
from src.features.organization.infrastructure.movements import router as movements_router


from src.features.weaning.routes import router as weaning_router
from src.features.weights.infrastructure.routes import router as weights_router


from src.features.health.infrastructure.routes import router as health_router


from src.features.breeding.infrastructure.routes import router as breeding_router
from src.features.breeding.infrastructure.assessments import router as assessments_router
from src.features.breeding.infrastructure.indicators import router as indicators_router
from src.features.breeding.infrastructure.upcoming import router as upcoming_births_router
from src.features.breeding.infrastructure.performance import router as performance_router


from src.features.health.infrastructure.followups import router as followups_router
from src.features.health.infrastructure.doses import router as doses_router
from src.features.health.infrastructure.pricing import router as product_pricing_router
from src.features.finance.infrastructure.group_costs import router as group_costs_router
from src.features.finance.infrastructure.profitability import router as profitability_router
from src.features.health.infrastructure.reactions import router as reactions_router
from src.features.health.infrastructure.incidents import router as incidents_router
from src.features.audit.infrastructure.routes import router as audit_router
from src.features.health.infrastructure.withdrawals import router as withdrawals_router
from src.features.exits.infrastructure.routes import router as exits_router


from src.features.finance.infrastructure.routes import router as finance_router
from src.features.finance.infrastructure.allocations import router as allocations_router


from src.features.feeding.infrastructure.routes import router as feeding_router
from src.features.dashboard.infrastructure.routes import router as dashboard_router
from src.features.reports.infrastructure.routes import router as reports_router
from src.features.reports.infrastructure.health import router as health_reports_router
from src.features.reports.infrastructure.breeding import router as breeding_reports_router
from src.features.reports.infrastructure.finance import router as finance_reports_router
from src.features.reports.infrastructure.feeding import router as feeding_reports_router
from src.features.reports.infrastructure.weights import router as weight_reports_router
from src.features.reports.infrastructure.weanings import router as weaning_reports_router


def create_app(*, migrate_on_startup: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if migrate_on_startup:
            await run_in_threadpool(run_migrations, get_engine())
        settings.profile_photos_dir.mkdir(parents=True, exist_ok=True)
        yield

    production = settings.environment == "production"
    app = FastAPI(title="Pelifolk API", version="0.1.0", lifespan=lifespan,
                  docs_url=None if production else "/docs",
                  redoc_url=None if production else "/redoc",
                  openapi_url=None if production else "/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"type": e["type"], "loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "Duplicate value or invalid relationship"})

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @app.get("/", tags=["Health"])
    def health():
        return {"message": "Pelifolk API is running"}

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(session=Depends(get_db)):
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(roles_router, prefix="/api/v1")
    app.include_router(animals_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(rectifications_router, prefix="/api/v1")
    app.include_router(decisions_router, prefix="/api/v1")
    app.include_router(decision_board_router, prefix="/api/v1")
    app.include_router(physical_router, prefix="/api/v1")
    app.include_router(organization_router, prefix="/api/v1")
    app.include_router(movements_router, prefix="/api/v1")
    app.include_router(weights_router, prefix="/api/v1")
    app.include_router(weaning_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(followups_router, prefix="/api/v1")
    app.include_router(doses_router, prefix="/api/v1")
    app.include_router(product_pricing_router, prefix="/api/v1")
    app.include_router(group_costs_router, prefix="/api/v1")
    app.include_router(profitability_router, prefix="/api/v1")
    app.include_router(reactions_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(withdrawals_router, prefix="/api/v1")
    app.include_router(breeding_router,prefix="/api/v1")
    app.include_router(assessments_router,prefix="/api/v1")
    app.include_router(indicators_router,prefix="/api/v1")
    app.include_router(upcoming_births_router, prefix="/api/v1")
    app.include_router(performance_router, prefix="/api/v1")
    app.include_router(exits_router, prefix="/api/v1")
    app.include_router(finance_router, prefix="/api/v1")
    app.include_router(allocations_router, prefix="/api/v1")
    app.include_router(feeding_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(health_reports_router, prefix="/api/v1")
    app.include_router(breeding_reports_router, prefix="/api/v1")
    app.include_router(finance_reports_router, prefix="/api/v1")
    app.include_router(feeding_reports_router, prefix="/api/v1")
    app.include_router(weight_reports_router, prefix="/api/v1")
    app.include_router(weaning_reports_router, prefix="/api/v1")
    app.mount("/upload/photos_profile", StaticFiles(directory=settings.profile_photos_dir, check_dir=False),
              name="profile_photos")
    return app


app = create_app()
