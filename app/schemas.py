from typing import Generic, Optional, TypeVar
from pydantic import BaseModel
from .models import PatientRead

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standardized response envelope contract."""
    data: Optional[T] = None
    error: Optional[str] = None


class HealthData(BaseModel):
    status: str
    timestamp: str


class SoftDeleteData(BaseModel):
    patient_id: str
    message: str
    deleted_at: str


class PatientLookupData(BaseModel):
    found: bool
    patient: Optional[PatientRead] = None
