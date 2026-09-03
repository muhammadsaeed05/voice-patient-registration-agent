import json
import logging
from typing import Any, Dict, Optional, Tuple

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
    """Extract tool arguments and toolCallId whether called by Vapi webhook or direct REST."""
    message = payload.get("message")
    if isinstance(message, dict):
        tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
        if tool_calls and isinstance(tool_calls, list):
            first_call = tool_calls[0]
            call_id = first_call.get("id")
            raw_args = first_call.get("function", {}).get("arguments", {})
            return call_id, _parse_args(raw_args)

    tool_calls = payload.get("toolCalls") or payload.get("toolCallList")
    if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
        first_call = tool_calls[0]
        call_id = first_call.get("id")
        raw_args = first_call.get("function", {}).get("arguments", {})
        return call_id, _parse_args(raw_args)

    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        call_id = tool_call.get("id")
        raw_args = tool_call.get("function", {}).get("arguments", {})
        return call_id, _parse_args(raw_args)

    if "function" in payload:
        call_id = payload.get("id")
        raw_args = payload.get("function", {}).get("arguments", {})
        return call_id, _parse_args(raw_args)

    if "toolCallId" in payload:
        call_id = payload.get("toolCallId")
        raw_args = payload.get("arguments") or payload.get("parameters") or payload
        return call_id, _parse_args(raw_args)

    return None, payload


def _format_tool_response(call_id: Optional[str], data: Any, envelope_fallback: Any = None) -> Any:
    """Format response: if called by Vapi (call_id present), return Vapi's required structure:

    { "results": [ { "toolCallId": "...", "result": "<STRING>" } ] }
    Otherwise return standard REST format.
    """
    if call_id:
        result_str = data if isinstance(data, str) else json.dumps(data, default=str)
        return {
            "results": [
                {
                    "toolCallId": call_id,
                    "result": result_str,
                }
            ]
        }
    return envelope_fallback if envelope_fallback is not None else data


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
    raw_phone = args.get("phone_number")
    if not raw_phone:
        if call_id:
            return _format_tool_response(
                call_id,
                {"found": False, "error": "Missing required field: phone_number. Ask caller for their 10-digit phone number."},
            )
        raise HTTPException(status_code=400, detail="Missing required field: phone_number")

    try:
        normalized = normalize_us_phone(raw_phone)
    except ValueError as e:
        if call_id:
            return _format_tool_response(
                call_id,
                {"found": False, "error": f"Invalid phone number '{raw_phone}': {str(e)}"},
            )
        raise HTTPException(status_code=400, detail=str(e))

    patient = session.exec(
        select(Patient).where(Patient.phone_number == normalized, Patient.deleted_at.is_(None))
    ).first()

    if not patient:
        return _format_tool_response(
            call_id,
            {
                "found": False,
                "message": f"No existing patient record found for phone number {raw_phone}. Proceed with new registration.",
            },
            envelope_fallback={"data": {"found": False, "patient": None}, "error": None},
        )

    patient_dict = {
        "found": True,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": str(patient.date_of_birth),
        "sex": patient.sex.value if hasattr(patient.sex, "value") else str(patient.sex),
        "phone_number": patient.phone_number,
        "email": patient.email,
        "address_line_1": patient.address_line_1,
        "address_line_2": patient.address_line_2,
        "city": patient.city,
        "state": patient.state,
        "zip_code": patient.zip_code,
        "insurance_provider": patient.insurance_provider,
        "insurance_member_id": patient.insurance_member_id,
        "preferred_language": patient.preferred_language,
        "emergency_contact_name": patient.emergency_contact_name,
        "emergency_contact_phone": patient.emergency_contact_phone,
        "patient_id": str(patient.patient_id),
    }
    return _format_tool_response(
        call_id,
        patient_dict,
        envelope_fallback={"data": {"found": True, "patient": patient}, "error": None},
    )


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
        patient_in = PatientCreate.model_validate(args)
        envelope = create_patient(patient_in=patient_in, session=session)
        created = envelope["data"]
        result_dict = {
            "success": True,
            "patient_id": str(created.patient_id),
            "first_name": created.first_name,
            "last_name": created.last_name,
            "phone_number": created.phone_number,
            "message": f"Patient {created.first_name} {created.last_name} successfully registered in clinic database.",
        }
        return _format_tool_response(call_id, result_dict, envelope_fallback=envelope)
    except Exception as e:
        logger.error("create_patient error: %s", str(e), exc_info=True)
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
    patient_id = args.get("patient_id")
    if not patient_id:
        if call_id:
            return _format_tool_response(
                call_id,
                {"success": False, "error": "Missing patient_id in arguments."},
            )
        raise HTTPException(status_code=400, detail="Missing patient_id in payload")

    update_fields = {k: v for k, v in args.items() if k != "patient_id"}
    try:
        patient_update = PatientUpdate.model_validate(update_fields)
        envelope = update_patient(id=patient_id, patient_in=patient_update, session=session)
        updated = envelope["data"]
        result_dict = {
            "success": True,
            "patient_id": str(updated.patient_id),
            "first_name": updated.first_name,
            "last_name": updated.last_name,
            "message": f"Patient record for {updated.first_name} {updated.last_name} updated successfully.",
        }
        return _format_tool_response(call_id, result_dict, envelope_fallback=envelope)
    except Exception as e:
        logger.error("update_patient error: %s", str(e), exc_info=True)
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
            func_name = tool_call.get("function", {}).get("name")
            raw_args = tool_call.get("function", {}).get("arguments", {})
            args = _parse_args(raw_args)

            result_data = None
            try:
                if func_name in ("lookup_patient_by_phone", "lookup-patient-by-phone"):
                    res = tool_lookup_patient_by_phone(payload=tool_call, session=session)
                    result_data = res.get("results", [{}])[0].get("result") if isinstance(res, dict) and "results" in res else res
                elif func_name in ("create_patient", "create-patient"):
                    res = tool_create_patient(payload=tool_call, session=session)
                    result_data = res.get("results", [{}])[0].get("result") if isinstance(res, dict) and "results" in res else res
                elif func_name in ("update_patient", "update-patient"):
                    res = tool_update_patient(payload=tool_call, session=session)
                    result_data = res.get("results", [{}])[0].get("result") if isinstance(res, dict) and "results" in res else res
                else:
                    result_data = json.dumps({"error": f"Unknown tool function: {func_name}"})
            except Exception as e:
                result_data = json.dumps({"error": str(e)})

            # Vapi STRICT REQUIREMENT: result must be a STRING
            result_str = result_data if isinstance(result_data, str) else json.dumps(result_data, default=str)

            results.append({
                "toolCallId": call_id,
                "result": result_str,
            })
        return {"results": results}

    return {"status": "ok"}
