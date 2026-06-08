import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import get_settings
from database.connection import init_db, engine
from api.routes import auth, documents
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docverify")
settings = get_settings()


def run_safe_migrations() -> None:
    """
    Add new columns if they don't exist.
    Uses IF NOT EXISTS syntax — safe to run on every startup.
    Works on both SQLite (dev) and PostgreSQL (production).
    Never fails if columns already exist.
    """
    is_sqlite = settings.database_url.startswith("sqlite")

    migrations = []

    if is_sqlite:
        # SQLite does not support IF NOT EXISTS for ALTER TABLE
        # Check column existence manually
        migrations = [
            ("extracted_fields", "validation_flags_json", "TEXT",
             "SELECT COUNT(*) FROM pragma_table_info('extracted_fields') WHERE name='validation_flags_json'"),
            ("extracted_fields", "validation_severity", "VARCHAR(20) DEFAULT ''",
             "SELECT COUNT(*) FROM pragma_table_info('extracted_fields') WHERE name='validation_severity'"),
        ]
        with engine.connect() as conn:
            for table, col, col_type, check_sql in migrations:
                try:
                    result = conn.execute(text(check_sql))
                    exists = result.scalar()
                    if not exists:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                        conn.commit()
                        logger.info("Migration: added column %s.%s", table, col)
                    else:
                        logger.info("Migration: column %s.%s already exists — skipped", table, col)
                except Exception as e:
                    logger.warning("Migration check skipped: %s", e)
    else:
        # PostgreSQL supports DO $$ blocks for safe conditional migrations
        pg_migrations = [
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_fields'
                    AND column_name='validation_flags_json'
                ) THEN
                    ALTER TABLE extracted_fields ADD COLUMN validation_flags_json TEXT;
                    RAISE NOTICE 'Added column validation_flags_json';
                END IF;
            END $$;
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='extracted_fields'
                    AND column_name='validation_severity'
                ) THEN
                    ALTER TABLE extracted_fields ADD COLUMN validation_severity VARCHAR(20) DEFAULT '';
                    RAISE NOTICE 'Added column validation_severity';
                END IF;
            END $$;
            """,
        ]
        with engine.connect() as conn:
            for sql in pg_migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as e:
                    logger.warning("Migration skipped: %s", e)

    logger.info("Migrations complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DocVerify AI — env=%s model=%s hitl_threshold=%d%%",
                settings.environment, settings.groq_primary_model,
                settings.confidence_hitl_threshold)
    init_db()                  # creates tables if they don't exist
    run_safe_migrations()      # adds new columns if they don't exist
    logger.info("Database ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="DocVerify AI",
    description="Immigration document extraction with confidence scoring, "
                "validation engine, and HITL routing.",
    version="1.1.0",
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
        "version": "1.1.0",
        "environment": settings.environment,
        "model": settings.groq_primary_model,
        "hitl_threshold": f"{settings.confidence_hitl_threshold}%",
        "validation_rules": 12,
    }
