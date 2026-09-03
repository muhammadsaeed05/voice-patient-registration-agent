from datetime import date, datetime, timezone
import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from ..database import get_session
from ..models import (
    Patient,
    PatientCreate,
    PatientRead,
    PatientUpdate,
    normalize_us_phone,
)
from ..schemas import ResponseEnvelope, SoftDeleteData

logger = logging.getLogger("voice_patient_agent.patients")

router = APIRouter(prefix="/patients", tags=["Patients"])


def get_patient_or_404(session: Session, patient_id_str: str) -> Patient:
    """Retrieve an active patient by UUID string, or raise appropriate 400/404."""
    try:
        patient_uuid = uuid.UUID(patient_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{patient_id_str}' is not a valid UUID",
        )

    patient = session.get(Patient, patient_uuid)
    if not patient or patient.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )
    return patient


@router.get("", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[List[PatientRead]])
def list_patients(
    last_name: Optional[str] = Query(None, description="Filter by patient last name"),
    date_of_birth: Optional[str] = Query(None, description="Filter by date of birth (YYYY-MM-DD)"),
    phone_number: Optional[str] = Query(None, description="Filter by 10-digit US phone number"),
    session: Session = Depends(get_session),
):
    """List active patients with optional last_name, date_of_birth, and phone_number filters."""
    query = select(Patient).where(Patient.deleted_at.is_(None))

    if last_name:
        query = query.where(func.lower(Patient.last_name) == last_name.strip().lower())

    if date_of_birth:
        dob_str = date_of_birth.strip()
        parsed_dob = None
        try:
            parsed_dob = date.fromisoformat(dob_str)
        except ValueError:
            for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
                try:
                    parsed_dob = datetime.strptime(dob_str, fmt).date()
                    break
                except ValueError:
                    continue
        if parsed_dob is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_of_birth must be a valid date in MM/DD/YYYY or YYYY-MM-DD format",
            )
        query = query.where(Patient.date_of_birth == parsed_dob)

    if phone_number:
        try:
            normalized_phone = normalize_us_phone(phone_number)
            query = query.where(Patient.phone_number == normalized_phone)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid phone_number query parameter: {str(e)}",
            )

    results = session.exec(query.order_by(Patient.created_at.desc())).all()
    return {"data": results, "error": None}


@router.get("/{id}", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
def get_patient(
    id: str,
    session: Session = Depends(get_session),
):
    """Get a single patient by UUID, returning 404 if missing or soft-deleted."""
    patient = get_patient_or_404(session, id)
    return {"data": patient, "error": None}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ResponseEnvelope[PatientRead])
def create_patient(
    patient_in: PatientCreate,
    session: Session = Depends(get_session),
):
    """Create a new patient with server-side validation. Returns 201 + created record."""
    patient = Patient.model_validate(patient_in)
    session.add(patient)
    session.commit()
    session.refresh(patient)

    # Log payload to stdout as required by clinical audit specification
    logger.info("CREATED PATIENT PAYLOAD: %s", patient.model_dump_json())

    return {"data": patient, "error": None}


@router.put("/{id}", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
def update_patient(
    id: str,
    patient_in: PatientUpdate,
    session: Session = Depends(get_session),
):
    """Partial update of a patient record. Returns 404 if missing or soft-deleted."""
    patient = get_patient_or_404(session, id)

    update_data = patient_in.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(patient, key, value)
        patient.updated_at = datetime.now(timezone.utc)
        session.add(patient)
        session.commit()
        session.refresh(patient)

    # Log payload to stdout as required by clinical audit specification
    logger.info("UPDATED PATIENT PAYLOAD: %s", patient.model_dump_json())

    return {"data": patient, "error": None}


@router.delete("/{id}", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[SoftDeleteData])
def delete_patient(
    id: str,
    session: Session = Depends(get_session),
):
    """Soft-delete patient record by setting deleted_at timestamp."""
    patient = get_patient_or_404(session, id)

    now = datetime.now(timezone.utc)
    patient.deleted_at = now
    patient.updated_at = now
    session.add(patient)
    session.commit()

    logger.info("SOFT-DELETED PATIENT: id=%s at %s", patient.patient_id, now.isoformat())
    return {
        "data": {
            "patient_id": str(patient.patient_id),
            "message": "Patient successfully soft-deleted",
            "deleted_at": now.isoformat(),
        },
        "error": None,
    }
