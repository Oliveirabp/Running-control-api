"""Ponto de entrada: `uvicorn app.main:app --reload`."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, migrate, scheduler
from app.api import actions, admin, auth, employees, kpi, records, settings
from app.config import settings as env
from app.db import SessionLocal
from app.exceptions import DomainError
from app.services import config_store
from app.services.auth import bootstrap_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
    migrate.upgrade()  # cria/atualiza o esquema pelas migrações (Alembic)
    with SessionLocal() as db:
        config_store.seed(db)
        bootstrap_admin(db)
    sched = scheduler.start() if env.enable_scheduler else None
    yield
    if sched:
        sched.shutdown(wait=False)


def create_app(init_db: bool = True) -> FastAPI:
    """`init_db=False` nos testes: o banco é preparado pela fixture, não pelo app."""
    app = FastAPI(
        title="Running Control API",
        version=__version__,
        description="Controle de permanência de peças em estações de carregamento (running test).",
        lifespan=lifespan if init_db else None,
    )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(status_code=exc.status_code, headers=headers,
                            content={"code": exc.code, "message": exc.message, "errors": exc.errors})

    @app.get("/health", tags=["Sistema"])
    def health():
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router)
    app.include_router(employees.router)
    app.include_router(records.router)
    app.include_router(settings.router)
    app.include_router(admin.router)
    app.include_router(kpi.router)
    app.include_router(actions.router)

    # Interface web (etapa 3): HTML + JS sem build, consumindo a própria API.
    web = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    def page(name: str):
        return lambda: FileResponse(web / name, headers={"Cache-Control": "no-cache"})

    for path, name in (("/", "index.html"), ("/tv", "tv.html"), ("/config", "config.html"),
                       ("/indicadores", "kpi.html"), ("/plano", "plano.html")):
        app.add_api_route(path, page(name), include_in_schema=False, methods=["GET"])
    return app


app = create_app()
