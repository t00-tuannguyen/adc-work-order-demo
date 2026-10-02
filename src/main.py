import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agents.graph import get_throughput_config
from src.api.auth import auth_router
from src.api.routes import router
from src.services.db import migrate_db
from src.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # File cấu hình throughput sai → không khởi động (ADC-002)
    config = get_throughput_config()
    migrate_db()
    logger.info("Starting %s in %s mode, throughput config %s", settings.app_name, settings.app_env, config.version)
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Multi-agent work order control tower cho 2 line chiếu xạ (MFG 08)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(auth_router)


@app.middleware("http")
async def no_store_for_private_responses(request, call_next):
    """Sau đăng xuất, bấm Back không hiện lại dữ liệu từ cache trình duyệt (ADC-008 TC7)."""
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/auth/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
