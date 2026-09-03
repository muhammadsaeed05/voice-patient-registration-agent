# Voice AI Agent Patient Registration System

A production-grade, end-to-end Voice AI Patient Intake and Registration System built for healthcare clinics. Callers can register as new patients or update existing medical records conversationally over the phone using **Vapi** and **OpenAI (GPT-4o)**, backed by a high-performance **FastAPI** service and persistent **SQLite** database.

---

## Architecture

```
                                  +-----------------------+
                                  |  Clinic Administrator |
                                  |  / Web Dashboard / QA |
                                  +-----------+-----------+
                                              |
                                              | Direct REST (JSON)
                                              v
+------------------+   PSTN / SIP    +------------------+  Tool Calls  +-------------------+  SQLModel  +------------------+
|  Patient Caller  | --------------> |    Vapi Voice    | -----------> |      FastAPI      | ---------> |      SQLite      |
|  (Phone / Web)   | <-------------- |  (OpenAI GPT-4o) | <----------- |   Backend API     | <--------- | (Persistent Vol) |
+------------------+   Audio Stream  +------------------+   Webhook    +-------------------+   Queries  +------------------+
                                        Deepgram Nova-2                 Stdout Structured
                                        ElevenLabs Voice                     Logging
```

### Flow Summary
1. **Inbound Call**: Caller dials into the clinic's dedicated Vapi telephony number.
2. **Speech Recognition**: Deepgram `nova-2` streams real-time speech-to-text with medical keyword formatting.
3. **Conversational Reasoning**: OpenAI GPT-4o processes conversational turns as intake coordinator "Clara".
4. **Duplicate Prevention**: In early turns, Clara calls `lookup_patient_by_phone` to identify existing patients.
5. **Confirmation Gate**: The agent reads back collected details and awaits verbal confirmation.
6. **API Mutation & Persistence**: Clara invokes `create_patient` or `update_patient` against the FastAPI backend, which validates fields server-side, logs payloads to stdout, and commits to persisted SQLite storage.
7. **Direct Querying**: Clinical staff can query, filter, update, or soft-delete patient records at any time via REST endpoints.

---

## Project Structure (Standard FastAPI `app/` Layout)

The repository follows the canonical, clean FastAPI `app/` layout:

```text
voice-patient-registration-agent/
├── app/
│   ├── __init__.py           # Package re-exports (app, models, database, settings)
│   ├── config.py             # Strongly-typed Pydantic BaseSettings (.env loading)
│   ├── database.py           # SQLite engine, session dependency, table init, seed data
│   ├── main.py               # FastAPI factory create_app(), lifespan, error handlers, CLI start()
│   ├── models.py             # SQLModel Patient table, SexEnum, Pydantic field validators
│   ├── schemas.py            # Response envelopes (ResponseEnvelope[T]) and serializers
│   └── routers/
│       ├── __init__.py       # Router aggregator
│       ├── health.py         # GET /health probe
│       ├── patients.py       # REST CRUD: GET, POST, PUT, DELETE /patients
│       └── tools.py          # Vapi tools (/tools/*) and universal webhook (/api/vapi/webhook)
├── Dockerfile                    # Clean container image
├── requirements.txt              # Application dependencies
├── railway.json                  # Railway deployment configuration
├── .dockerignore                 # Container build ignores
├── .gitignore                    # SQLite database, venv, and cache ignores
├── .env.example                  # Environment variable reference template
├── pyproject.toml                # UV / PEP 621 package metadata
├── main.py                       # Root launcher for running 'python main.py' or 'uvicorn main:app'
├── vapi_config.md                # Vapi assistant system prompt, tool schemas & reasoning
└── README.md                     # Documentation & setup guide
```

---

## Tech Stack Justification (3-Hour Assessment Constraint)

| Layer | Technology | Justification under 3-Hour Scope |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI (Python 3.12+)** | Native async performance, automatic OpenAPI documentation, and instant dependency injection out-of-the-box. |
| **Data Validation & ORM** | **SQLModel (SQLAlchemy + Pydantic v2)** | Eliminates code duplication by unifying Pydantic schemas and SQLAlchemy models into a single definition. |
| **Database** | **SQLite (File-based, WAL mode)** | Zero-configuration local development that persists reliably in production via a single Railway volume mount. |
| **Voice & Telephony** | **Vapi** | Turnkey telephony orchestrator handling WebRTC/SIP, low-latency audio streaming, turn-taking, and LLM tool execution. |
| **Intake Intelligence (LLM)**| **OpenAI (GPT-4o)** | Low latency, industry-leading instruction-following, and structured function-calling accuracy, crucial for clinical field parsing. |
| **Hosting & Persistence** | **Railway** | Frictionless Docker deployment with native persistent volume attachment at `/app/data` within minutes. |
| **Observability** | **Python `logging` (Stdout)** | Follows Twelve-Factor App principles, instantly readable via Docker and Railway log streams. |

---

## API Specification

All API responses are wrapped in a standard envelope:
```json
{
  "data": { ... },
  "error": null
}
```
Failed responses (status `400`, `404`, `422`, `500`) return:
```json
{
  "data": null,
  "error": "Error description message"
}
```

### Endpoints

| Method | Endpoint | Status | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | `200` | Health check probe for container monitoring. |
| `GET` | `/patients` | `200` | List non-deleted patients. Supports `?last_name=`, `?date_of_birth=`, and `?phone_number=` filters. |
| `GET` | `/patients/{id}` | `200` / `404` | Get single patient by UUID. Returns 404 if missing or soft-deleted. |
| `POST` | `/patients` | `201` / `422` | Create patient with strict server-side validation. Logs payload to stdout. |
| `PUT` | `/patients/{id}` | `200` / `404` | Partial update of patient record. Logs payload to stdout. |
| `DELETE` | `/patients/{id}` | `200` / `404` | Soft-delete patient (sets `deleted_at` timestamp; preserves record for auditing). |
| `POST` | `/tools/lookup-patient-by-phone` | `200` | Tool endpoint for Vapi duplicate detection. |
| `POST` | `/tools/create-patient` | `201` / `422` | Tool endpoint for Vapi patient creation. |
| `POST` | `/tools/update-patient` | `200` / `404` | Tool endpoint for Vapi patient record updates. |
| `POST` | `/api/vapi/webhook` | `200` | Universal Vapi Server URL Webhook handler. |

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.11+ (Python 3.12 or 3.13 recommended)
- `uv` (recommended) or `pip`

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/voice-patient-registration-agent.git
cd voice-patient-registration-agent

# Using uv (fastest):
uv sync

# Or using standard python venv:
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Default `.env` settings will automatically store the local SQLite database at `./data/patients.db`.

### 3. Run Database Initialization & Development Server
```bash
# Using uv:
uv run uvicorn main:app --reload --port 8000

# Or using activated virtualenv:
uvicorn main:app --reload --port 8000
```
On startup, the service automatically creates required database tables and inserts **2 seed patient records** (`Jane Doe` and `Robert Smith-Jones`) if the database is empty.

Interactive Swagger documentation is available at:
👉 **`http://localhost:8000/docs`**

---

## Voice Agent Setup (Vapi)

Detailed system prompts, tool schemas, and technical reasoning are documented in [vapi_config.md](vapi_config.md).

### Quick Vapi Setup Steps:
1. Log in to your [Vapi Dashboard](https://dashboard.vapi.ai/).
2. Create a new Assistant and select:
   - **Model Provider**: `OpenAI`
   - **Model**: `gpt-4o` (or `gpt-4o-mini`)
   - **Transcriber**: Deepgram `nova-2`
   - **Voice**: ElevenLabs (e.g., Sarah / Rachel)
3. Paste the **System Prompt** from [vapi_config.md](vapi_config.md).
4. Under **Tools**, import the 3 functions defined in [vapi_config.md](vapi_config.md):
   - `lookup_patient_by_phone` $\rightarrow$ `https://<YOUR_DEPLOYED_URL>/tools/lookup-patient-by-phone`
   - `create_patient` $\rightarrow$ `https://<YOUR_DEPLOYED_URL>/tools/create-patient`
   - `update_patient` $\rightarrow$ `https://<YOUR_DEPLOYED_URL>/tools/update-patient`
5. Connect your Vapi phone number to this assistant.

---

## Deployment to Railway (with Persistent Volume)

The backend is packaged as a lightweight Docker container with a persistent volume mounted at `/app/data` to ensure SQLite data survives container restarts and new deployments.

### Option A: Deploy via Railway CLI

1. **Install & Authenticate Railway CLI**:
   ```bash
   npm i -g @railway/cli
   railway login
   ```

2. **Initialize Project**:
   ```bash
   railway init
   ```

3. **Create & Attach Persistent Volume**:
   ```bash
   # Create volume for persistent SQLite storage
   railway volume add --mount-path /app/data
   ```

4. **Set Environment Variables**:
   ```bash
   railway variables set DATABASE_URL=sqlite:////app/data/patients.db
   railway variables set LOG_LEVEL=INFO
   ```

5. **Deploy**:
   ```bash
   railway up
   ```

6. **Generate Public Domain**:
   ```bash
   railway domain
   ```

---

### Option B: Deploy via Railway Web Dashboard

1. Push your code to a GitHub repository.
2. Open [railway.app](https://railway.app) $\rightarrow$ Click **New Project** $\rightarrow$ **Deploy from GitHub repo**.
3. Once the service is created, go to the service **Settings**:
   - Under **Volumes**, click **Add Volume**.
   - Set **Mount Path** to: `/app/data`.
4. Go to **Variables** tab and add:
   - `DATABASE_URL`: `sqlite:////app/data/patients.db`
   - `PORT`: `8000`
5. Go to **Networking** $\rightarrow$ Click **Generate Domain** (e.g. `voice-patient-agent-production.up.railway.app`).
6. Update Vapi Tool webhook URLs to point to your Railway domain.

---

## Persistence Verification Checklist

To prove that patient data persists across redeployments:

1. **Call 1 (New Registration)**:
   - Call the clinic phone number.
   - Register a new patient (e.g. "Samantha Cruz", phone `(512) 555-4321`, DOB `1992-03-10`).
   - Confirm Clara reads back details and saves successfully.

2. **Verify via REST API**:
   - Query your deployed API:
     ```bash
     curl -s "https://<YOUR_RAILWAY_URL>/patients?phone_number=5125554321" | jq .
     ```
   - Confirm status code is `200` and Samantha's record is returned.

3. **Trigger Container Restart / Redeployment**:
   - In Railway CLI or Dashboard, click **Restart** or trigger a new deployment commit.
   - Wait until the new container passes health check on `/health`.

4. **Call 2 (Persistence & Duplicate Check)**:
   - Call from the same number or provide `(512) 555-4321` when Clara asks for your phone number.
   - **Verification Passed**: Clara identifies Samantha immediately: *"Welcome back, Samantha! I see we already have an account on file for you. Are you calling today to update your information...?"*

---

## Environment Variables Reference

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | No | `sqlite:///data/patients.db` | SQLAlchemy SQLite connection string. Set to `sqlite:////app/data/patients.db` on Railway. |
| `PORT` | No | `8000` | HTTP port for Uvicorn server. Provided automatically by Railway. |
| `HOST` | No | `0.0.0.0` | Bind host IP address. |
| `LOG_LEVEL` | No | `INFO` | Python stdout log level (`DEBUG`, `INFO`, `WARNING`). |
| `VAPI_API_KEY` | Optional | None | Vapi private API key for programmatic assistant synchronization. |
| `VAPI_ASSISTANT_ID` | Optional | None | Vapi assistant identifier. |
| `OPENAI_API_KEY` | Optional | None | OpenAI API key used within Vapi's model provider configuration. |

---

## Known Limitations & Trade-Offs

- **SQLite vs. PostgreSQL**: SQLite was chosen for zero-dependency simplicity and fast setup within the 3-hour limit. While WAL mode supports concurrent readers, high write concurrency (e.g., hundreds of simultaneous calls) can encounter database lock contention. A production system with high call volume should use PostgreSQL with connection pooling.
- **HIPAA Compliance**: While this architecture enforces field validation, audit timestamps, and soft-deletes, it does not include encryption-at-rest with customer-managed keys, signed BAA agreements, or complete audit logging required for certified HIPAA environments.
- **Authentication & Authorization**: The API endpoints are currently open without JWT/OAuth2 tokens or API key authentication to prioritize frictionless webhook delivery and testing within the assessment timeframe.
- **Spoken Ambiguity Handling**: Speech recognition may occasionally mishear complex surnames or street abbreviations; while spelling out characters is supported by the prompt, phonetic alphanumeric tokenization (e.g., NATO phonetic alphabet fallback) would improve accuracy.

---

## Next Steps & Production Roadmap

Given more engineering time, the following enhancements are prioritized:

1. **PostgreSQL Migration**: Swap SQLite engine for async PostgreSQL (`asyncpg`) with Alembic database migrations.
2. **Authentication & RBAC**: Implement OAuth2 / JWT bearer authentication for clinic administrators and signed webhook HMAC verification (`vapi-secret-key`) on `/tools/*` and `/api/vapi/webhook`.
3. **Multilingual Support**: Add automated language detection in Vapi so Clara can seamlessly switch to Spanish, Mandarin, or French and persist the caller's `preferred_language`.
4. **Appointment Scheduling Integration**: Expand the state machine to offer immediate appointment slot booking with EHR/calendar integrations (e.g. AthenaHealth, Epic, or Google Calendar) after registration.
5. **Call Transcripts & Audio Recordings Storage**: Ingest Vapi end-of-call webhooks and persist encrypted audio recording URLs and formatted clinical dialogue summaries directly linked to the `patient_id`.
6. **Clinical Admin Dashboard**: Build a Next.js / Tailwind management dashboard with real-time WebSocket feeds showing incoming registrations, patient search, and soft-delete restorations.
