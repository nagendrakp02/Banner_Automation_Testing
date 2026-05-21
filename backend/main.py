
import sys
import asyncio

# Windows: Playwright needs ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.core.config import settings
from backend.db.session import init_db
from backend.api.routes import banners_router, runs_router, ws_router, misc_router

logger.remove()
logger.add(sys.stdout, level="DEBUG" if settings.debug else "INFO", colorize=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    await init_db()
    logger.info("Database initialised")
    yield
    logger.info("Shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Vision-first Multi-Agent Banner Automation Testing",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(banners_router, prefix=PREFIX)
app.include_router(runs_router,    prefix=PREFIX)
app.include_router(ws_router)
app.include_router(misc_router,    prefix=PREFIX)

# Serve screenshots as static files
try:
    app.mount(
        "/screenshots",
        StaticFiles(directory=str(settings.screenshot_dir)),
        name="screenshots",
    )
except Exception:
    pass
