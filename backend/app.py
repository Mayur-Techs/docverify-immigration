import gc
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.routes import auth
from api.routes import documents
from config import get_settings
from database.connection import engine
from database.connection import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docverify")
settings = get_settings()

# ── Semaphore: max 2 documents processed at the same time ─────────────────────
# Each processing job uses ~150-200MB. Free tier has 512MB.
# 2 concurrent = ~400MB peak. Keeps us inside the limit.
import asyncio  # noqa: E402
_processing_semaphore = asyncio.Semaphore(2)


def get_semaphore() -> asyncio.Semaphore:
    return _processing_semaphore


def run_safe_migrations() -> None:
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        checks = [
            ("extracted_fields", "validation_flags_json", "TEXT",
             "SELECT COUNT(*) FROM pragma_table_info('extracted_fields') WHERE name='validation_flags_json'"),
            ("extracted_fields", "validation_severity", "VARCHAR(20) DEFAULT ''",
             "SELECT COUNT(*) FROM pragma_table_info('extracted_fields') WHERE name='validation_severity'"),
        ]
        with engine.connect() as conn:
            for table, col, col_type, check_sql in checks:
                try:
                    exists = conn.execute(text(check_sql)).scalar()
                    if not exists:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                        conn.commit()
                        logger.info("Migration: added %s.%s", table, col)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Migration skipped: %s", e)
    else:
        pg = [
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_fields' AND column_name='validation_flags_json')
                THEN ALTER TABLE extracted_fields ADD COLUMN validation_flags_json TEXT; END IF;
            END $$;""",
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_fields' AND column_name='validation_severity')
                THEN ALTER TABLE extracted_fields ADD COLUMN validation_severity VARCHAR(20) DEFAULT ''; END IF;
            END $$;""",
        ]
        with engine.connect() as conn:
            for sql in pg:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as e:  # noqa: BLE001
                    logger.warning("Migration skipped: %s", e)
    logger.info("Migrations complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    run_safe_migrations()
    logger.info("DocVerify AI ready — env=%s model=%s", settings.environment, settings.groq_primary_model)
    yield
    gc.collect()


app = FastAPI(title="DocVerify AI", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


@app.exception_handler(MemoryError)
async def memory_error_handler(request: Request, exc: MemoryError):
    gc.collect()
    logger.error("MemoryError on %s", request.url)
    return JSONResponse(status_code=503, content={
        "detail": "Server is processing other documents. Please retry in 30 seconds.",
    })


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.2.0",
        "environment": settings.environment,
        "model": settings.groq_primary_model,
        "hitl_threshold": f"{settings.confidence_hitl_threshold}%",
        "validation_rules": 12,
        "max_concurrent_processing": 2,
    }
