from fastapi import FastAPI

from app.api.routes.health import router as health_router


app = FastAPI(
    title="URPP API",
    version="0.0.1",
    description="Personal Professor V0 backend",
)

app.include_router(health_router)
