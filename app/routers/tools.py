import json
import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from ..database import get_session
from ..models import (
    Patient,
    PatientCreate,
    PatientUpdate,
    normalize_us_phone,
)
from .patients import create_patient, update_patient

logger = logging.getLogger("voice_patient_agent.tools")

router = APIRouter(tags=["Vapi Voice Tools"])


def _parse_args(raw_args: Any) -> Dict[str, Any]:
    """Safely parse arguments into a dictionary."""
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except Exception:
            return {}
    elif isinstance(raw_args, dict):
        return raw_args
    return {}


def _extract_call_id_and_args(payload: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """Extract tool arguments and toolCallId from Vapi payloads or direct calls."""
    message = payload.get("message")
    if isinstance(message, dict):
        payload = message

    calls = payload.get("toolCalls") or payload.get("toolCallList")
    item = calls[0] if isinstance(calls, list) and calls else payload.get("toolCall") or payload

    if isinstance(item, dict):
        call_id = item.get("id") or item.get("toolCallId")
        if "function" in item:
            raw_args = item.get("function", {}).get("arguments", {})
        else:
            raw_args = item.get("arguments") or item.get("parameters") or (item if not call_id else {})
        return call_id, _parse_args(raw_args)

    return None, payload


def _format_tool_response(call_id: Optional[str], data: Any, envelope_fallback: Any = None) -> Any:
    """Format response: return Vapi structure if call_id present, else direct REST envelope."""
    if call_id:
        result_str = data if isinstance(data, str) else json.dumps(data, default=str)
        return {"results": [{"toolCallId": call_id, "result": result_str}]}
    return envelope_fallback if envelope_fallback is not None else {"data": data, "error": None}


def lookup_patient_core(args: Dict[str, Any], session: Session) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Core logic for looking up patient by phone number.

    Returns (tool_result_dict, rest_envelope_dict).
    """
    raw_phone = args.get("phone_number")
    if not raw_phone:
        raise ValueError("Missing required field: phone_number")

    normalized = normalize_us_phone(raw_phone)
    patient = session.exec(
        select(Patient).where(Patient.phone_number == normalized, Patient.deleted_at.is_(None))
    ).first()

    if not patient:
        result = {
            "found": False,
            "message": f"No existing patient record found for phone number {raw_phone}. Proceed with new registration.",
        }
        envelope = {"data": {"found": False, "patient": None}, "error": None}
        return result, envelope

    patient_data = patient.model_dump(mode="json")
    result = {"found": True, **patient_data}
    envelope = {"data": {"found": True, "patient": patient}, "error": None}
    return result, envelope


def create_patient_core(args: Dict[str, Any], session: Session) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Core logic for creating a patient from voice tool arguments."""
    patient_in = PatientCreate.model_validate(args)
    envelope = create_patient(patient_in=patient_in, session=session)
    created = envelope["data"]
    result = {
        "success": True,
        "patient_id": str(created.patient_id),
        "first_name": created.first_name,
        "last_name": created.last_name,
        "phone_number": created.phone_number,
        "message": f"Patient {created.first_name} {created.last_name} successfully registered in clinic database.",
    }
    return result, envelope


def update_patient_core(args: Dict[str, Any], session: Session) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Core logic for updating a patient from voice tool arguments."""
    patient_id = args.get("patient_id")
    if not patient_id:
        raise ValueError("Missing required field: patient_id")

    update_fields = {k: v for k, v in args.items() if k != "patient_id"}
    patient_update = PatientUpdate.model_validate(update_fields)
    envelope = update_patient(id=patient_id, patient_in=patient_update, session=session)
    updated = envelope["data"]
    result = {
        "success": True,
        "patient_id": str(updated.patient_id),
        "first_name": updated.first_name,
        "last_name": updated.last_name,
        "message": f"Patient record for {updated.first_name} {updated.last_name} updated successfully.",
    }
    return result, envelope


@router.post("/tools/lookup_patient_by_phone", status_code=status.HTTP_200_OK)
@router.post("/tools/lookup_patient_by_phone/", status_code=status.HTTP_200_OK)
@router.post("/tools/lookup-patient-by-phone", status_code=status.HTTP_200_OK)
@router.post("/tools/lookup-patient-by-phone/", status_code=status.HTTP_200_OK)
def tool_lookup_patient_by_phone(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to look up existing patient by phone number for duplicate check."""
    logger.info("lookup_patient_by_phone called with payload: %s", json.dumps(payload))
    call_id, args = _extract_call_id_and_args(payload)
    try:
        result, envelope = lookup_patient_core(args, session)
        return _format_tool_response(call_id, result, envelope_fallback=envelope)
    except Exception as e:
        logger.warning("lookup_patient_by_phone failed: %s", e)
        if call_id:
            return _format_tool_response(call_id, {"found": False, "error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tools/create_patient", status_code=status.HTTP_200_OK)
@router.post("/tools/create_patient/", status_code=status.HTTP_200_OK)
@router.post("/tools/create-patient", status_code=status.HTTP_200_OK)
@router.post("/tools/create-patient/", status_code=status.HTTP_200_OK)
def tool_create_patient(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to create patient after verbal confirmation."""
    logger.info("create_patient called with payload: %s", json.dumps(payload))
    call_id, args = _extract_call_id_and_args(payload)
    try:
        result, envelope = create_patient_core(args, session)
        return _format_tool_response(call_id, result, envelope_fallback=envelope)
    except Exception as e:
        logger.error("create_patient tool error: %s", e)
        if call_id:
            return _format_tool_response(
                call_id,
                {"success": False, "error": str(e), "message": "Failed to save patient record."},
            )
        raise


@router.post("/tools/update_patient", status_code=status.HTTP_200_OK)
@router.post("/tools/update_patient/", status_code=status.HTTP_200_OK)
@router.post("/tools/update-patient", status_code=status.HTTP_200_OK)
@router.post("/tools/update-patient/", status_code=status.HTTP_200_OK)
def tool_update_patient(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
):
    """Voice agent tool to update existing patient."""
    logger.info("update_patient called with payload: %s", json.dumps(payload))
    call_id, args = _extract_call_id_and_args(payload)
    try:
        result, envelope = update_patient_core(args, session)
        return _format_tool_response(call_id, result, envelope_fallback=envelope)
    except Exception as e:
        logger.error("update_patient tool error: %s", e)
        if call_id:
            return _format_tool_response(
                call_id,
                {"success": False, "error": str(e), "message": "Failed to update patient record."},
            )
        raise


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

    Dispatches tool calls sent by Vapi in `{ message: { type: 'tool-calls', toolCalls: [...] } }`.
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
            func_name = tool_call.get("function", {}).get("name", "")
            raw_args = tool_call.get("function", {}).get("arguments", {})
            args = _parse_args(raw_args)

            try:
                if func_name in ("lookup_patient_by_phone", "lookup-patient-by-phone"):
                    result_data, _ = lookup_patient_core(args, session)
                elif func_name in ("create_patient", "create-patient"):
                    result_data, _ = create_patient_core(args, session)
                elif func_name in ("update_patient", "update-patient"):
                    result_data, _ = update_patient_core(args, session)
                else:
                    result_data = {"error": f"Unknown tool function: {func_name}"}
            except Exception as e:
                result_data = {"error": str(e)}

            result_str = result_data if isinstance(result_data, str) else json.dumps(result_data, default=str)
            results.append({"toolCallId": call_id, "result": result_str})

        return {"results": results}

    return {"status": "ok"}
