from datetime import date
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models import Patient, SexEnum

# Use in-memory SQLite database with StaticPool for fast, isolated test execution
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_session():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
def setup_database():
    """Create fresh tables before each test and drop them after."""
    SQLModel.metadata.create_all(test_engine)
    yield
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_patient_payload():
    return {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "1990-05-15",
        "sex": "Female",
        "phone_number": "4155551234",
        "email": "jane.doe@example.com",
        "address_line_1": "123 Market Street",
        "address_line_2": "Apt 4B",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "insurance_provider": "Blue Cross",
        "insurance_member_id": "BCBS-987654",
        "preferred_language": "English",
        "emergency_contact_name": "John Doe",
        "emergency_contact_phone": "4155559876",
    }


# ==========================================
# 1. Health Probe Tests
# ==========================================

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert data["data"]["status"] == "healthy"
    assert "timestamp" in data["data"]


# ==========================================
# 2. Patient Creation & Validation Tests
# ==========================================

def test_create_patient_success(client, sample_patient_payload):
    response = client.post("/patients", json=sample_patient_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["error"] is None
    data = body["data"]
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Doe"
    assert data["phone_number"] == "4155551234"
    assert data["state"] == "CA"
    assert "patient_id" in data
    assert uuid.UUID(data["patient_id"])


def test_create_patient_validation_errors(client, sample_patient_payload):
    # Invalid phone (less than 10 digits)
    invalid_phone = dict(sample_patient_payload, phone_number="12345")
    resp = client.post("/patients", json=invalid_phone)
    assert resp.status_code == 422
    assert resp.json()["data"] is None
    assert "10-digit" in resp.json()["error"]

    # Future date of birth
    future_dob = dict(sample_patient_payload, date_of_birth="2099-01-01")
    resp = client.post("/patients", json=future_dob)
    assert resp.status_code == 422
    assert "future" in resp.json()["error"]

    # Invalid state abbreviation
    invalid_state = dict(sample_patient_payload, state="ZZ")
    resp = client.post("/patients", json=invalid_state)
    assert resp.status_code == 422
    assert "state" in resp.json()["error"]

    # Missing required field
    missing_name = dict(sample_patient_payload)
    del missing_name["first_name"]
    resp = client.post("/patients", json=missing_name)
    assert resp.status_code == 422


# ==========================================
# 3. Patient Retrieval & Query Filter Tests
# ==========================================

def test_list_patients_and_filters(client, sample_patient_payload):
    # Create patient 1
    client.post("/patients", json=sample_patient_payload)

    # Create patient 2
    p2 = dict(
        sample_patient_payload,
        first_name="Robert",
        last_name="Smith",
        phone_number="2125557890",
        date_of_birth="1982-11-20",
    )
    client.post("/patients", json=p2)

    # List all active
    resp = client.get("/patients")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2

    # Filter by last_name
    resp_name = client.get("/patients?last_name=smith")
    assert resp_name.status_code == 200
    assert len(resp_name.json()["data"]) == 1
    assert resp_name.json()["data"][0]["first_name"] == "Robert"

    # Filter by date_of_birth
    resp_dob = client.get("/patients?date_of_birth=1990-05-15")
    assert resp_dob.status_code == 200
    assert len(resp_dob.json()["data"]) == 1
    assert resp_dob.json()["data"][0]["first_name"] == "Jane"

    # Filter by formatted phone_number
    resp_phone = client.get("/patients?phone_number=(212) 555-7890")
    assert resp_phone.status_code == 200
    assert len(resp_phone.json()["data"]) == 1
    assert resp_phone.json()["data"][0]["first_name"] == "Robert"

    # Invalid query params return 400 Bad Request
    bad_phone = client.get("/patients?phone_number=123")
    assert bad_phone.status_code == 400
    assert "Invalid phone_number" in bad_phone.json()["error"]

    bad_dob = client.get("/patients?date_of_birth=invalid-date")
    assert bad_dob.status_code == 400
    assert "date_of_birth" in bad_dob.json()["error"]


def test_get_patient_by_id(client, sample_patient_payload):
    create_resp = client.post("/patients", json=sample_patient_payload)
    patient_id = create_resp.json()["data"]["patient_id"]

    # Success
    resp = client.get(f"/patients/{patient_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["patient_id"] == patient_id

    # Not found
    non_existent = str(uuid.uuid4())
    resp_404 = client.get(f"/patients/{non_existent}")
    assert resp_404.status_code == 404
    assert resp_404.json()["error"] == "Patient not found"

    # Malformed UUID returns 400 Bad Request
    resp_400 = client.get("/patients/not-a-valid-uuid")
    assert resp_400.status_code == 400
    assert "not a valid UUID" in resp_400.json()["error"]


# ==========================================
# 4. Partial Updates & Soft Deletion
# ==========================================

def test_update_patient_partial(client, sample_patient_payload):
    create_resp = client.post("/patients", json=sample_patient_payload)
    patient_id = create_resp.json()["data"]["patient_id"]

    # Partial update: change city and address_line_2
    update_payload = {"city": "Oakland", "address_line_2": "Suite 300"}
    resp = client.put(f"/patients/{patient_id}", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Oakland"
    assert data["address_line_2"] == "Suite 300"
    # Unmodified fields should remain unchanged
    assert data["first_name"] == "Jane"
    assert data["last_name"] == "Doe"

    # Cannot set required field to null
    resp_null = client.put(f"/patients/{patient_id}", json={"first_name": None})
    assert resp_null.status_code == 422
    assert "first_name cannot be null" in resp_null.json()["error"]


def test_soft_delete_patient(client, sample_patient_payload):
    create_resp = client.post("/patients", json=sample_patient_payload)
    patient_id = create_resp.json()["data"]["patient_id"]

    # Soft delete
    del_resp = client.delete(f"/patients/{patient_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["patient_id"] == patient_id
    assert "deleted_at" in del_resp.json()["data"]

    # Subsequent GET /patients excludes soft-deleted record
    list_resp = client.get("/patients")
    assert len(list_resp.json()["data"]) == 0

    # Subsequent GET /patients/{id} returns 404
    get_resp = client.get(f"/patients/{patient_id}")
    assert get_resp.status_code == 404

    # Duplicate DELETE returns 404
    del_again = client.delete(f"/patients/{patient_id}")
    assert del_again.status_code == 404


# ==========================================
# 5. Vapi Voice Tools & Webhook Dispatch
# ==========================================

def test_vapi_tools_lookup_patient(client, sample_patient_payload):
    # Lookup when database is empty
    resp = client.post("/tools/lookup-patient-by-phone", json={"phone_number": "4155551234"})
    assert resp.status_code == 200
    assert resp.json()["data"]["found"] is False

    # Create patient
    client.post("/patients", json=sample_patient_payload)

    # Direct lookup (REST mode)
    resp = client.post("/tools/lookup-patient-by-phone", json={"phone_number": "4155551234"})
    assert resp.status_code == 200
    assert resp.json()["data"]["found"] is True
    assert resp.json()["data"]["patient"]["first_name"] == "Jane"

    # Vapi tool call mode with toolCallId
    vapi_req = {
        "toolCallId": "call_123",
        "function": {
            "name": "lookup_patient_by_phone",
            "arguments": {"phone_number": "4155551234"},
        },
    }
    resp = client.post("/tools/lookup-patient-by-phone", json=vapi_req)
    assert resp.status_code == 200
    vapi_data = resp.json()
    assert "results" in vapi_data
    assert vapi_data["results"][0]["toolCallId"] == "call_123"
    assert "Jane" in vapi_data["results"][0]["result"]


def test_vapi_tools_create_patient(client, sample_patient_payload):
    vapi_payload = {
        "toolCallId": "call_abc",
        "function": {
            "name": "create_patient",
            "arguments": sample_patient_payload,
        },
    }
    resp = client.post("/tools/create-patient", json=vapi_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert body["results"][0]["toolCallId"] == "call_abc"
    assert "successfully registered" in body["results"][0]["result"]

    # Verify patient exists in DB
    list_resp = client.get("/patients")
    assert len(list_resp.json()["data"]) == 1


def test_vapi_universal_webhook(client, sample_patient_payload):
    # Probe GET
    probe = client.get("/api/vapi/webhook")
    assert probe.status_code == 200
    assert probe.json()["status"] == "ok"

    # Tool calls via Vapi Universal Webhook
    webhook_payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "webhook_call_001",
                    "function": {
                        "name": "create_patient",
                        "arguments": sample_patient_payload,
                    },
                }
            ],
        }
    }
    resp = client.post("/api/vapi/webhook", json=webhook_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert body["results"][0]["toolCallId"] == "webhook_call_001"
    assert "successfully registered" in body["results"][0]["result"]
