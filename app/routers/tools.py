import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..database import get_session
from ..models import (
    Patient,
    PatientCreate,
    PatientRead,
    PatientUpdate,
    normalize_us_phone,
)
from ..schemas import PatientLookupData, ResponseEnvelope
from .patients import create_patient, update_patient

logger = logging.getLogger("voice_patient_agent.tools")

router = APIRouter(tags=["Vapi Voice Tools"])


def _extract_args(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract tool arguments whether sent as direct JSON or wrapped in Vapi's webhook format."""
    message = payload.get("message")
    if isinstance(message, dict) and message.get("type") == "tool-calls":
        tool_calls = message.get("toolCalls", [])
        if tool_calls:
            raw_args = tool_calls[0].get("function", {}).get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    return json.loads(raw_args)
                except Exception:
                    return {}
            elif isinstance(raw_args, dict):
                return raw_args
    return payload


@router.post("/tools/lookup_patient_by_phone", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientLookupData])
@router.post("/tools/lookup_patient_by_phone/", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientLookupData])
@router.post("/tools/lookup-patient-by-phone", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientLookupData])
@router.post("/tools/lookup-patient-by-phone/", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientLookupData])
def tool_lookup_patient_by_phone(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to look up existing patient by phone number for duplicate check."""
    args = _extract_args(payload)
    raw_phone = args.get("phone_number")
    if not raw_phone:
        raise HTTPException(status_code=400, detail="Missing required field: phone_number")
    try:
        normalized = normalize_us_phone(raw_phone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    patient = session.exec(
        select(Patient).where(Patient.phone_number == normalized, Patient.deleted_at.is_(None))
    ).first()

    if not patient:
        return {"data": {"found": False, "patient": None}, "error": None}

    return {"data": {"found": True, "patient": patient}, "error": None}


@router.post("/tools/create_patient", status_code=status.HTTP_201_CREATED, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/create_patient/", status_code=status.HTTP_201_CREATED, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/create-patient", status_code=status.HTTP_201_CREATED, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/create-patient/", status_code=status.HTTP_201_CREATED, response_model=ResponseEnvelope[PatientRead])
def tool_create_patient(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to create patient after verbal confirmation."""
    args = _extract_args(payload)
    patient_in = PatientCreate.model_validate(args)
    return create_patient(patient_in=patient_in, session=session)


@router.post("/tools/update_patient", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/update_patient/", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/update-patient", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
@router.post("/tools/update-patient/", status_code=status.HTTP_200_OK, response_model=ResponseEnvelope[PatientRead])
def tool_update_patient(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to update existing patient."""
    args = _extract_args(payload)
    patient_id = args.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="Missing patient_id in payload")

    update_fields = {k: v for k, v in args.items() if k != "patient_id"}
    patient_update = PatientUpdate.model_validate(update_fields)
    return update_patient(id=patient_id, patient_in=patient_update, session=session)


@router.get("/api/vapi/webhook", status_code=status.HTTP_200_OK)
@router.get("/api/vapi/webhook/", status_code=status.HTTP_200_OK)
def vapi_webhook_probe():
    """Health/ping probe for Vapi server URL webhook."""
    return {"status": "ok", "message": "Vapi webhook endpoint is ready"}


@router.post("/api/vapi/webhook", status_code=status.HTTP_200_OK)
@router.post("/api/vapi/webhook/", status_code=status.HTTP_200_OK)
async def vapi_server_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    """Universal Vapi Server URL Webhook handler.

    Dispatches tool calls sent by Vapi in the `{ message: { type: 'tool-calls', toolCalls: [...] } }` format.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    logger.info("Vapi Webhook Received: %s", json.dumps(body))

    message = body.get("message", {})
    if message.get("type") == "tool-calls":
        results = []
        for tool_call in message.get("toolCalls", []):
            call_id = tool_call.get("id")
            func_name = tool_call.get("function", {}).get("name")
            raw_args = tool_call.get("function", {}).get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args

            result_payload = None
            try:
                if func_name in ("lookup_patient_by_phone", "lookup-patient-by-phone"):
                    result_payload = tool_lookup_patient_by_phone(payload=args, session=session)
                elif func_name in ("create_patient", "create-patient"):
                    model = PatientCreate(**args)
                    result_payload = create_patient(patient_in=model, session=session)
                elif func_name in ("update_patient", "update-patient"):
                    result_payload = tool_update_patient(payload=args, session=session)
                else:
                    result_payload = {"error": f"Unknown tool function: {func_name}"}
            except HTTPException as e:
                result_payload = {"error": e.detail}
            except Exception as e:
                result_payload = {"error": str(e)}

            results.append({
                "toolCallId": call_id,
                "result": result_payload,
            })
        return {"results": results}

    return {"status": "ok"}
