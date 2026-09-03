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

REQUIRED_FIELDS = {
    "first_name", "last_name", "date_of_birth", "sex",
    "phone_number", "address_line_1", "city", "state", "zip_code"
}


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


def validate_name(v: Any, field_name: str = "name") -> str:
    """Validate first or last name (1-50 chars, letters/hyphens/apostrophes/spaces)."""
    if v is None:
        raise ValueError(f"{field_name} is required")
    s = str(v).strip()
    if not (1 <= len(s) <= 50):
        raise ValueError(f"{field_name} must be between 1 and 50 characters")
    if not NAME_REGEX.match(s):
        raise ValueError(
            f"{field_name} must contain only alphabetic characters, hyphens, apostrophes, and spaces"
        )
    return s


def validate_dob(v: Any) -> Optional[date]:
    """Validate date of birth, supporting ISO and US date string formats."""
    if v is None:
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


def validate_sex(v: Any) -> "SexEnum":
    """Validate administrative sex, case-insensitive for voice input."""
    if v is None:
        raise ValueError("sex is required")
    if isinstance(v, SexEnum):
        return v
    s = str(v).strip()
    for member in SexEnum:
        if member.value.lower() == s.lower():
            return member
    valid_options = ", ".join(f"'{m.value}'" for m in SexEnum)
    raise ValueError(f"sex must be one of: {valid_options}")


def validate_state(v: Any) -> str:
    """Validate 2-letter US state postal abbreviation."""
    if v is None:
        raise ValueError("state is required")
    s = str(v).strip().upper()
    if s not in VALID_US_STATES:
        raise ValueError(
            f"state must be a valid 2-letter US state abbreviation (e.g. CA, NY, TX). Received '{s}'"
        )
    return s


def validate_zip(v: Any) -> str:
    """Validate 5-digit US ZIP code or 9-digit ZIP+4."""
    if v is None:
        raise ValueError("zip_code is required")
    s = str(v).strip()
    if not ZIP_REGEX.match(s):
        raise ValueError(
            "zip_code must be a 5-digit US ZIP code or 9-digit ZIP+4 (e.g. 90210 or 90210-1234)"
        )
    return s


def validate_email_field(v: Any) -> Optional[str]:
    """Validate email address format if provided."""
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


def validate_insurance_id(v: Any) -> Optional[str]:
    """Validate alphanumeric insurance member/subscriber ID if provided."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if not re.match(r"^[a-zA-Z0-9-]+$", s):
        raise ValueError("insurance_member_id must be alphanumeric (letters, numbers, hyphens)")
    return s


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
        return validate_name(v, info.field_name)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob_field(cls, v: Any) -> date:
        val = validate_dob(v)
        if val is None:
            raise ValueError("date_of_birth is required")
        return val

    @field_validator("sex", mode="before")
    @classmethod
    def validate_sex_field(cls, v: Any) -> SexEnum:
        return validate_sex(v)

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
        s = str(v).strip() if v is not None else ""
        if not s:
            raise ValueError("address_line_1 cannot be empty")
        return s

    @field_validator("city", mode="before")
    @classmethod
    def validate_city(cls, v: Any) -> str:
        s = str(v).strip() if v is not None else ""
        if not (1 <= len(s) <= 100):
            raise ValueError("city must be between 1 and 100 characters")
        return s

    @field_validator("state", mode="before")
    @classmethod
    def validate_state_field(cls, v: Any) -> str:
        return validate_state(v)

    @field_validator("zip_code", mode="before")
    @classmethod
    def validate_zip_field(cls, v: Any) -> str:
        return validate_zip(v)

    @field_validator("preferred_language", mode="before")
    @classmethod
    def validate_lang(cls, v: Any) -> str:
        return str(v).strip() if v else "English"

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_emerg_phone(cls, v: Any) -> Optional[str]:
        return normalize_us_phone(v, required=False) if v else None

    @field_validator("insurance_member_id", mode="before")
    @classmethod
    def validate_insurance(cls, v: Any) -> Optional[str]:
        return validate_insurance_id(v)

    @field_validator("address_line_2", "insurance_provider", "emergency_contact_name", mode="before")
    @classmethod
    def validate_opt_text(cls, v: Any) -> Optional[str]:
        s = str(v).strip() if v is not None else ""
        return s if s else None


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

    @field_validator("*", mode="before")
    @classmethod
    def validate_update_field(cls, v: Any, info) -> Any:
        field_name = info.field_name
        if v is None:
            if field_name in REQUIRED_FIELDS:
                raise ValueError(f"{field_name} cannot be null")
            return None

        if field_name in ("first_name", "last_name"):
            return validate_name(v, field_name)
        if field_name == "date_of_birth":
            val = validate_dob(v)
            if val is None:
                raise ValueError("date_of_birth cannot be null")
            return val
        if field_name == "sex":
            return validate_sex(v)
        if field_name == "phone_number":
            return normalize_us_phone(v, required=True)
        if field_name == "email":
            return validate_email_field(v)
        if field_name == "address_line_1":
            s = str(v).strip()
            if not s:
                raise ValueError("address_line_1 cannot be empty")
            return s
        if field_name == "city":
            s = str(v).strip()
            if not (1 <= len(s) <= 100):
                raise ValueError("city must be between 1 and 100 characters")
            return s
        if field_name == "state":
            return validate_state(v)
        if field_name == "zip_code":
            return validate_zip(v)
        if field_name == "insurance_member_id":
            return validate_insurance_id(v)
        if field_name == "emergency_contact_phone":
            return normalize_us_phone(v, required=False) if v else None
        if field_name == "preferred_language":
            return str(v).strip() if v else "English"
        if field_name in ("address_line_2", "insurance_provider", "emergency_contact_name"):
            s = str(v).strip()
            return s if s else None
        return v


class PatientRead(PatientBase):
    patient_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
