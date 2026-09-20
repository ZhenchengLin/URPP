import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.repositories.numeric_sqlite_engine_v01 import (
    create_numeric_sqlite_engine,
)

from app.repositories.numeric_repository_bundle_v01 import (
    create_numeric_repository_bundle,
)

from app.api.routes.health import router as health_router


@asynccontextmanager
async def numeric_sqlite_lifespan(app: FastAPI):
    """Optionally initialize the guarded Numeric SQLite Engine.

    The current application has no database-backed routes.
    Database startup is therefore explicit and opt-in.

    This does not create a database, run migrations, or
    automatically configure repositories.
    """

    database_path = os.environ.get(
        'URPP_NUMERIC_SQLITE_DATABASE_PATH'
    )

    if database_path is None:
        # Preserve the existing health-only application startup.
        yield
        return

    if not database_path.strip():
        raise RuntimeError(
            'URPP_NUMERIC_SQLITE_DATABASE_PATH is set '
            'but is empty.'
        )

    # The factory checks the existing database before creating
    # the Engine and enforces foreign_keys on its connections.
    engine = create_numeric_sqlite_engine(
        database_path
    )

    app.state.numeric_sqlite_engine = engine

    try:
        # All three repositories share a Session factory
        # bound to the guarded startup Engine.
        repositories = create_numeric_repository_bundle(
            engine
        )
        app.state.numeric_repositories = repositories

        yield
    finally:
        try:
            engine.dispose()
        finally:
            if hasattr(app.state, 'numeric_repositories'):
                del app.state.numeric_repositories
            del app.state.numeric_sqlite_engine


app = FastAPI(
    title="URPP API",
    lifespan=numeric_sqlite_lifespan,
    version="0.0.1",
    description="Personal Professor V0 backend",
)

app.include_router(health_router)
