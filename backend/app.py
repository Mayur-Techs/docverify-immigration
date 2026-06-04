import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import get_settings
from database.connection import init_db
from api.routes import auth, documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docverify")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DocVerify AI — env=%s model=%s hitl_threshold=%d%%",
                settings.environment, settings.groq_primary_model,
                settings.confidence_hitl_threshold)
    init_db()
    logger.info("Database tables ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="DocVerify AI",
    description="Immigration document extraction with confidence scoring and HITL routing.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.environment,
        "model": settings.groq_primary_model,
        "hitl_threshold": f"{settings.confidence_hitl_threshold}%",
    }
