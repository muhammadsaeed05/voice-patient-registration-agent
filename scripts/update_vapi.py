import sys
import httpx
from app.config import settings

VAPI_API_KEY = settings.VAPI_API_KEY
ASSISTANT_ID = settings.VAPI_ASSISTANT_ID
RAILWAY_URL = settings.RAILWAY_URL

missing = []
if not VAPI_API_KEY:
    missing.append("VAPI_API_KEY")
if not ASSISTANT_ID:
    missing.append("VAPI_ASSISTANT_ID")
if not RAILWAY_URL:
    missing.append("RAILWAY_URL")

if missing:
    print(f"Error: Missing required environment variable(s): {', '.join(missing)}")
    print("Please define them in your .env file before running this script.")
    sys.exit(1)

RAILWAY_URL = RAILWAY_URL.rstrip("/")

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
}

tools_definitions = [
    {
        "type": "function",
        "function": {
            "name": "lookup_patient_by_phone",
            "description": "Searches for an existing active patient record using a 10-digit US phone number to prevent duplicate registrations and facilitate record updates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "10-digit US phone number with or without formatting, e.g. '4155551234' or '(415) 555-1234'",
                    }
                },
                "required": ["phone_number"],
            },
        },
        "server": {
            "url": f"{RAILWAY_URL}/tools/lookup-patient-by-phone",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_patient",
            "description": "Creates a new patient registration record in the clinic database. ONLY call this function after reading back the full record and receiving explicit confirmation from the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "Patient's legal first name"},
                    "last_name": {"type": "string", "description": "Patient's legal last name"},
                    "date_of_birth": {
                        "type": "string",
                        "description": "Patient date of birth in ISO YYYY-MM-DD format. Must not be in the future.",
                    },
                    "sex": {
                        "type": "string",
                        "enum": ["Male", "Female", "Other", "Decline to Answer"],
                        "description": "Patient administrative sex",
                    },
                    "phone_number": {"type": "string", "description": "Patient's 10-digit US phone number"},
                    "email": {"type": "string", "description": "Optional patient email address"},
                    "address_line_1": {"type": "string", "description": "Primary street address (e.g. 123 Main St)"},
                    "address_line_2": {"type": "string", "description": "Optional secondary address (e.g. Apt 4B, Suite 200)"},
                    "city": {"type": "string", "description": "City name"},
                    "state": {"type": "string", "description": "Two-letter US state postal code (e.g. CA, NY, TX)"},
                    "zip_code": {"type": "string", "description": "5-digit US ZIP code or 9-digit ZIP+4"},
                    "insurance_provider": {"type": "string", "description": "Optional name of health insurance carrier"},
                    "insurance_member_id": {"type": "string", "description": "Optional insurance member or policy ID"},
                    "preferred_language": {"type": "string", "description": "Preferred spoken language, defaults to English"},
                    "emergency_contact_name": {"type": "string", "description": "Optional full name of emergency contact person"},
                    "emergency_contact_phone": {"type": "string", "description": "Optional 10-digit US phone number for emergency contact"},
                },
                "required": [
                    "first_name",
                    "last_name",
                    "date_of_birth",
                    "sex",
                    "phone_number",
                    "address_line_1",
                    "city",
                    "state",
                    "zip_code",
                ],
            },
        },
        "server": {
            "url": f"{RAILWAY_URL}/tools/create-patient",
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_patient",
            "description": "Updates an existing patient record by patient UUID. Call this when an existing patient calls to update their information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "UUID of the patient record to update"},
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "date_of_birth": {"type": "string"},
                    "sex": {"type": "string", "enum": ["Male", "Female", "Other", "Decline to Answer"]},
                    "phone_number": {"type": "string"},
                    "email": {"type": "string"},
                    "address_line_1": {"type": "string"},
                    "address_line_2": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "zip_code": {"type": "string"},
                    "insurance_provider": {"type": "string"},
                    "insurance_member_id": {"type": "string"},
                    "preferred_language": {"type": "string"},
                    "emergency_contact_name": {"type": "string"},
                    "emergency_contact_phone": {"type": "string"},
                },
                "required": ["patient_id"],
            },
        },
        "server": {
            "url": f"{RAILWAY_URL}/tools/update-patient",
        },
    },
]

print("1. Checking Vapi Global Tools Library...")
existing_tools_resp = httpx.get("https://api.vapi.ai/tool", headers=headers)
if existing_tools_resp.status_code != 200:
    print(f"Error fetching tools library: {existing_tools_resp.status_code} - {existing_tools_resp.text}")
    sys.exit(1)

existing_tools_map = {
    t.get("function", {}).get("name"): t.get("id")
    for t in existing_tools_resp.json()
    if "function" in t and "name" in t.get("function", {})
}

tool_ids = []
for tool_def in tools_definitions:
    name = tool_def["function"]["name"]
    if name in existing_tools_map:
        tool_id = existing_tools_map[name]
        print(f"Updating existing tool in library: {name} (ID: {tool_id})...")
        patch_resp = httpx.patch(f"https://api.vapi.ai/tool/{tool_id}", headers=headers, json=tool_def)
        if patch_resp.status_code == 200:
            tool_ids.append(tool_id)
        else:
            print(f"Warning: Failed to patch tool {name}: {patch_resp.text}")
            tool_ids.append(tool_id)
    else:
        print(f"Creating tool in global library: {name}...")
        create_resp = httpx.post("https://api.vapi.ai/tool", headers=headers, json=tool_def)
        if create_resp.status_code in (200, 201):
            created_id = create_resp.json().get("id")
            print(f"✓ Created {name} (ID: {created_id})")
            tool_ids.append(created_id)
        else:
            print(f"Error creating tool {name}: {create_resp.status_code} - {create_resp.text}")
            sys.exit(1)

print("\n2. Linking tools to your Assistant...")
assistant_url = f"https://api.vapi.ai/assistant/{ASSISTANT_ID}"
asst_resp = httpx.get(assistant_url, headers=headers)
if asst_resp.status_code != 200:
    print(f"Error fetching assistant: {asst_resp.status_code} - {asst_resp.text}")
    sys.exit(1)

asst = asst_resp.json()
model_config = asst.get("model", {})
existing_tool_ids = set(model_config.get("toolIds", []))
all_tool_ids = list(existing_tool_ids.union(set(tool_ids)))

model_config["toolIds"] = all_tool_ids

payload = {
    "model": model_config,
    "server": {
        "url": f"{RAILWAY_URL}/api/vapi/webhook/",
        "timeoutSeconds": 20,
    },
}

asst_patch = httpx.patch(assistant_url, headers=headers, json=payload)
if asst_patch.status_code == 200:
    print("\n✓ Successfully registered all 3 tools in your Vapi Tools Dashboard & linked to assistant!")
    print(f"Assistant: {asst.get('name')}")
    print("Dashboard Tools:")
    for t_def in tools_definitions:
        print(f"  - {t_def['function']['name']}")
else:
    print(f"Error linking tools to assistant: {asst_patch.status_code} - {asst_patch.text}")
    sys.exit(1)
