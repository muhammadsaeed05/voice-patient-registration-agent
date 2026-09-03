from datetime import datetime, timezone
from fastapi import APIRouter, status
from ..schemas import HealthData, ResponseEnvelope

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    response_model=ResponseEnvelope[HealthData],
    summary="Health check probe",
)
def health_check():
    """Health check endpoint for container monitoring and deployment probes."""
    return {
        "data": {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "error": None,
    }
