from datetime import date
import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .models import Patient, SexEnum

logger = logging.getLogger("voice_patient_agent.database")


def _prepare_db_path(db_url: str) -> str:
    """Ensure directory exists for file-based SQLite databases."""
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
        path_str = db_url.replace("sqlite:///", "", 1)
        db_path = Path(path_str).expanduser()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured SQLite database directory exists at: {db_path.parent}")
            return db_url
        except OSError as e:
            fallback_dir = Path.cwd() / "data"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            logger.warning(
                f"Could not create database directory at {db_path.parent} ({e}). Falling back to local directory {fallback_dir}"
            )
            return f"sqlite:///{fallback_dir}/patients.db"
    return db_url


effective_db_url = _prepare_db_path(settings.DATABASE_URL)

connect_args = {"check_same_thread": False} if effective_db_url.startswith("sqlite") else {}
engine = create_engine(effective_db_url, echo=False, connect_args=connect_args)

# Enable WAL mode on SQLite connections for high-concurrency read/write performance
if effective_db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding database sessions."""
    with Session(engine) as session:
        yield session


def seed_database(session: Session) -> None:
    """Insert 2 realistic seed patient records if the Patient table is empty."""
    statement = select(Patient)
    existing_patient = session.exec(statement).first()
    if existing_patient is not None:
        logger.info("Database already contains patient records. Skipping seed.")
        return

    logger.info("Seeding database with 2 initial patient records...")
    seed_patients = [
        Patient(
            first_name="Jane",
            last_name="Doe",
            date_of_birth=date(1985, 4, 12),
            sex=SexEnum.FEMALE,
            phone_number="4155551234",
            email="jane.doe@example.com",
            address_line_1="123 Market Street",
            address_line_2="Apt 4B",
            city="San Francisco",
            state="CA",
            zip_code="94105",
            insurance_provider="Blue Cross Blue Shield",
            insurance_member_id="BCBS-12345678",
            preferred_language="English",
            emergency_contact_name="John Doe",
            emergency_contact_phone="4155559876",
        ),
        Patient(
            first_name="Robert",
            last_name="Smith-Jones",
            date_of_birth=date(1972, 11, 23),
            sex=SexEnum.MALE,
            phone_number="2125557890",
            email="robert.sj@example.com",
            address_line_1="456 Broadway",
            address_line_2=None,
            city="New York",
            state="NY",
            zip_code="10013-1234",
            insurance_provider="Aetna",
            insurance_member_id="AET-998877",
            preferred_language="English",
            emergency_contact_name="Sarah Smith",
            emergency_contact_phone="2125554321",
        ),
    ]

    for patient in seed_patients:
        session.add(patient)
    session.commit()
    logger.info("Database successfully seeded with 2 patients.")


def create_db_and_tables() -> None:
    """Create all SQLModel tables and seed initial data."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session)
