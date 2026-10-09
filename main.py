from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.concurrency import run_in_threadpool
from src.core.database import get_engine
from src.core.migrations import run_migrations
from src.core.config import get_settings
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.routes.routes import router as auth_router
from src.features.users.infrastructure.routes.routes import router as users_router
from src.features.roles.infrastructure.routes.routes import router as roles_router
from src.features.animals.infrastructure.routes import router as animals_router
from src.features.organization.infrastructure.routes import router as organization_router


from src.features.weights.infrastructure.routes import router as weights_router


from src.features.health.infrastructure.routes import router as health_router


from src.features.breeding.infrastructure.routes import router as breeding_router


from src.features.exits.infrastructure.routes import router as exits_router


from src.features.finance.infrastructure.routes import router as finance_router


def create_app(*, migrate_on_startup: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if migrate_on_startup:
            await run_in_threadpool(run_migrations, get_engine())
        yield

    app = FastAPI(title="Pelifolk API", version="0.1.0", lifespan=lifespan)
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

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(roles_router, prefix="/api/v1")
    app.include_router(animals_router, prefix="/api/v1")
    app.include_router(organization_router, prefix="/api/v1")
    app.include_router(weights_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(breeding_router,prefix="/api/v1")
    app.include_router(exits_router, prefix="/api/v1")
    app.include_router(finance_router, prefix="/api/v1")
    return app


app = create_app()
