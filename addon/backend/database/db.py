import logging
from sqlmodel import SQLModel, create_engine, Session, text
from backend.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.db_path, echo=False)

def init_db():
    # Import models so SQLModel metadata is fully registered before create_all.
    from backend import models  # noqa: F401
    SQLModel.metadata.create_all(engine)

    # Migrations
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN force_next_run BOOLEAN DEFAULT 0"))
        except Exception:
            pass  # column likely exists
        try:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN smart_watering BOOLEAN DEFAULT 0"))
        except Exception:
            pass
            
        # Zones migrations
        for col in ["area_m2 FLOAT", "flow_lpm FLOAT", "soil_type VARCHAR(20)", "sun_exposure VARCHAR(20)"]:
            try:
                conn.execute(text(f"ALTER TABLE zones ADD COLUMN {col}"))
            except Exception:
                pass


def get_session():
    with Session(engine) as session:
        yield session
