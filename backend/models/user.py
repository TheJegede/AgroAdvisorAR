"""Pydantic schemas for auth and farmer profile endpoints."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal, Optional
from datetime import date
from utils.counties import AR_COUNTIES
from utils.crops import CropKey


class RiceField(BaseModel):
    field_name: str
    acres: Optional[float] = None
    last_flood_date: date
    irrigation_method: Literal["continuous flood", "intermittent", "awd"] = "continuous flood"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    county_fips: str
    primary_crops: list[CropKey] = Field(default_factory=list)
    language: Literal["en", "es"] = "en"
    rice_fields: list[RiceField] = Field(default_factory=list)

    @field_validator("county_fips")
    @classmethod
    def validate_fips(cls, v: str) -> str:
        if v not in AR_COUNTIES:
            raise ValueError(f"county_fips {v!r} is not a valid Arkansas county FIPS")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    access_token: str
    refresh_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class FarmerProfile(BaseModel):
    id: str
    full_name: str
    county_fips: str
    county_name: str
    primary_crops: list[str]
    language: str
    created_at: str
    last_active: str
    is_admin: bool = False
    rice_fields: list[dict] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    county_fips: str | None = None
    primary_crops: list[CropKey] | None = None
    language: Literal["en", "es"] | None = None
    rice_fields: Optional[list[RiceField]] = None

    @field_validator("county_fips")
    @classmethod
    def validate_fips(cls, v: str | None) -> str | None:
        if v is not None and v not in AR_COUNTIES:
            raise ValueError(f"county_fips {v!r} is not a valid Arkansas county FIPS")
        return v
