from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api import api_router
from app.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        from app.config import get_settings
        from scripts.seed_neo4j import seed as seed_neo
        from scripts.seed_qdrant import seed as seed_qdr

        settings = get_settings()
        try:
            seed_neo(
                settings.neo4j_uri,
                settings.neo4j_username,
                settings.neo4j_password.get_secret_value(),
            )
            logger.info("neo4j_seeded")
        except Exception as exc:
            logger.warning("neo4j_seed_skipped", extra={"error": str(exc)})
        try:
            seed_qdr()
            logger.info("qdrant_seeded")
        except Exception as exc:
            logger.warning("qdrant_seed_skipped", extra={"error": str(exc)})
    except Exception as exc:
        logger.warning("startup_seed_failed", extra={"error": str(exc)})
    yield


app = FastAPI(title="ChronoGuard", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")
