import logging
from sqlmodel import SQLModel, create_engine, Session
from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.db_path, echo=False)

# Each entry: (table, column, column_definition)
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("schedules", "extra_zone_ids", "TEXT"),
    ("zones", "plant_type", "VARCHAR(20) DEFAULT 'grass'"),
    ("zones", "emitter_type", "VARCHAR(20) DEFAULT 'rotor'"),
    ("zones", "soil_type", "VARCHAR(20) DEFAULT 'loam'"),
    ("zones", "sun_exposure", "VARCHAR(20) DEFAULT 'full'"),
    ("zones", "area_m2", "FLOAT DEFAULT 10.0"),
    ("zones", "flow_lpm", "FLOAT DEFAULT 10.0"),
    ("zones", "current_depletion_mm", "FLOAT DEFAULT 0.0"),
    ("sensors", "zone_id", "INTEGER"),
]


def _run_migrations() -> None:
    """Apply incremental ALTER TABLE migrations for columns added after initial release."""
    with engine.connect() as conn:
        for table, column, col_def in _MIGRATIONS:
            rows = conn.exec_driver_sql(
                f"PRAGMA table_info({table})"  # noqa: S608
            ).fetchall()
            existing = {row[1] for row in rows}
            if column not in existing:
                logger.info("Migration: adding column %s.%s", table, column)
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"  # noqa: S608
                )
                conn.commit()


def init_db():
    # Import models so SQLModel metadata is fully registered before create_all.
    from backend import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def get_session():
    with Session(engine) as session:
        yield session
