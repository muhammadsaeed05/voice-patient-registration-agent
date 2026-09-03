from datetime import date, datetime, timezone
from enum import Enum
import re
from typing import Any, Optional
import uuid

from email_validator import EmailNotValidError, validate_email
from pydantic import field_validator
from sqlmodel import Field, SQLModel

VALID_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

NAME_REGEX = re.compile(r"^[a-zA-Z' -]{1,50}$")
ZIP_REGEX = re.compile(r"^\d{5}(-\d{4})?$")


def normalize_us_phone(v: Any, required: bool = True) -> Optional[str]:
    """Normalize and validate a 10-digit US phone number."""
    if v is None:
        if required:
            raise ValueError("Phone number is required")
        return None
    s = str(v).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(
            f"Phone number must be a valid 10-digit US number (received {len(digits)} digits)"
        )
    # Area code (NPA) and Central Office code (NXX) cannot start with 0 or 1 in NANP
    if digits[0] in ("0", "1"):
        raise ValueError("US phone area code cannot start with 0 or 1")
    return digits


def validate_name_field(v: Any, field_name: str, required: bool = True) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    s = str(v).strip()
    if not (1 <= len(s) <= 50):
        raise ValueError(f"{field_name} must be between 1 and 50 characters")
    if not NAME_REGEX.match(s):
        raise ValueError(
            f"{field_name} must contain only alphabetic characters, hyphens, apostrophes, and spaces"
        )
    return s


def validate_dob(v: Any, required: bool = True) -> Optional[date]:
    if v is None:
        if required:
            raise ValueError("date_of_birth is required")
        return None
    if isinstance(v, str):
        v_str = v.strip()
        try:
            v = date.fromisoformat(v_str)
        except ValueError:
            parsed = None
            for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
                try:
                    parsed = datetime.strptime(v_str, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed is not None:
                v = parsed
            else:
                raise ValueError("date_of_birth must be a valid date in MM/DD/YYYY or YYYY-MM-DD format")
    elif isinstance(v, datetime):
        v = v.date()
    elif not isinstance(v, date):
        raise ValueError("date_of_birth must be a valid date")

    if v > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    if v.year < 1900:
        raise ValueError("date_of_birth cannot be earlier than 1900")
    return v


def validate_sex(v: Any, required: bool = True) -> Optional["SexEnum"]:
    if v is None:
        if required:
            raise ValueError("sex is required")
        return None
    if isinstance(v, SexEnum):
        return v
    s = str(v).strip()
    # Case-insensitive matching for friendly voice parsing
    for member in SexEnum:
        if member.value.lower() == s.lower():
            return member
    valid_options = ", ".join(f"'{m.value}'" for m in SexEnum)
    raise ValueError(f"sex must be one of: {valid_options}")


def validate_address_line_1(v: Any, required: bool = True) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError("address_line_1 is required")
        return None
    s = str(v).strip()
    if not s:
        raise ValueError("address_line_1 cannot be empty")
    return s


def validate_city(v: Any, required: bool = True) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError("city is required")
        return None
    s = str(v).strip()
    if not (1 <= len(s) <= 100):
        raise ValueError("city must be between 1 and 100 characters")
    return s


def validate_state(v: Any, required: bool = True) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError("state is required")
        return None
    s = str(v).strip().upper()
    if s not in VALID_US_STATES:
        raise ValueError(
            f"state must be a valid 2-letter US state abbreviation (e.g. CA, NY, TX). Received '{s}'"
        )
    return s


def validate_zip(v: Any, required: bool = True) -> Optional[str]:
    if v is None:
        if required:
            raise ValueError("zip_code is required")
        return None
    s = str(v).strip()
    if not ZIP_REGEX.match(s):
        raise ValueError(
            "zip_code must be a 5-digit US ZIP code or 9-digit ZIP+4 (e.g. 90210 or 90210-1234)"
        )
    return s


def validate_email_field(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        validated = validate_email(s, check_deliverability=False)
        return validated.normalized
    except EmailNotValidError as e:
        raise ValueError(f"Invalid email address: {e}")


def validate_optional_text(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def validate_language(v: Any) -> str:
    if v is None:
        return "English"
    s = str(v).strip()
    return s if s else "English"


class SexEnum(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE_TO_ANSWER = "Decline to Answer"


class PatientBase(SQLModel):
    first_name: str = Field(index=True)
    last_name: str = Field(index=True)
    date_of_birth: date = Field(index=True)
    sex: SexEnum
    phone_number: str = Field(index=True)
    email: Optional[str] = Field(default=None)
    address_line_1: str
    address_line_2: Optional[str] = Field(default=None)
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = Field(default=None)
    insurance_member_id: Optional[str] = Field(default=None)
    preferred_language: Optional[str] = Field(default="English")
    emergency_contact_name: Optional[str] = Field(default=None)
    emergency_contact_phone: Optional[str] = Field(default=None)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate_names(cls, v: Any, info) -> str:
        return validate_name_field(v, info.field_name, required=True)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v: Any) -> date:
        return validate_dob(v, required=True)

    @field_validator("sex", mode="before")
    @classmethod
    def validate_sex(cls, v: Any) -> SexEnum:
        return validate_sex(v, required=True)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, v: Any) -> str:
        return normalize_us_phone(v, required=True)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: Any) -> Optional[str]:
        return validate_email_field(v)

    @field_validator("address_line_1", mode="before")
    @classmethod
    def validate_addr1(cls, v: Any) -> str:
        return validate_address_line_1(v, required=True)

    @field_validator("city", mode="before")
    @classmethod
    def validate_city(cls, v: Any) -> str:
        return validate_city(v, required=True)

    @field_validator("state", mode="before")
    @classmethod
    def validate_state(cls, v: Any) -> str:
        return validate_state(v, required=True)

    @field_validator("zip_code", mode="before")
    @classmethod
    def validate_zip(cls, v: Any) -> str:
        return validate_zip(v, required=True)

    @field_validator("preferred_language", mode="before")
    @classmethod
    def validate_lang(cls, v: Any) -> str:
        return validate_language(v)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_emerg_phone(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return normalize_us_phone(v, required=False)

    @field_validator(
        "address_line_2",
        "insurance_provider",
        "insurance_member_id",
        "emergency_contact_name",
        mode="before",
    )
    @classmethod
    def validate_opt_text(cls, v: Any) -> Optional[str]:
        return validate_optional_text(v)


class Patient(PatientBase, table=True):
    __tablename__ = "patients"

    patient_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        nullable=True,
        index=True,
    )


class PatientCreate(PatientBase):
    pass


class PatientUpdate(SQLModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[SexEnum] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator(
        "first_name",
        "last_name",
        "date_of_birth",
        "sex",
        "phone_number",
        "address_line_1",
        "city",
        "state",
        "zip_code",
        mode="before",
    )
    @classmethod
    def reject_null_required_fields(cls, v: Any, info) -> Any:
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def validate_names(cls, v: Any, info) -> Optional[str]:
        return validate_name_field(v, info.field_name, required=False)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v: Any) -> Optional[date]:
        return validate_dob(v, required=False)

    @field_validator("sex", mode="before")
    @classmethod
    def validate_sex(cls, v: Any) -> Optional[SexEnum]:
        return validate_sex(v, required=False)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, v: Any) -> Optional[str]:
        return normalize_us_phone(v, required=False)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: Any) -> Optional[str]:
        return validate_email_field(v)

    @field_validator("address_line_1", mode="before")
    @classmethod
    def validate_addr1(cls, v: Any) -> Optional[str]:
        return validate_address_line_1(v, required=False)

    @field_validator("city", mode="before")
    @classmethod
    def validate_city(cls, v: Any) -> Optional[str]:
        return validate_city(v, required=False)

    @field_validator("state", mode="before")
    @classmethod
    def validate_state(cls, v: Any) -> Optional[str]:
        return validate_state(v, required=False)

    @field_validator("zip_code", mode="before")
    @classmethod
    def validate_zip(cls, v: Any) -> Optional[str]:
        return validate_zip(v, required=False)

    @field_validator("preferred_language", mode="before")
    @classmethod
    def validate_lang(cls, v: Any) -> Optional[str]:
        return validate_language(v) if v is not None else None

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_emerg_phone(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        return normalize_us_phone(v, required=False)

    @field_validator(
        "address_line_2",
        "insurance_provider",
        "insurance_member_id",
        "emergency_contact_name",
        mode="before",
    )
    @classmethod
    def validate_opt_text(cls, v: Any) -> Optional[str]:
        return validate_optional_text(v)


class PatientRead(PatientBase):
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
