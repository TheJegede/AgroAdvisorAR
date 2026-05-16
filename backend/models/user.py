"""Pydantic schemas for auth and farmer profile endpoints."""
from pydantic import BaseModel, EmailStr, field_validator
from typing import Literal
from utils.counties import AR_COUNTIES


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    county_fips: str
    primary_crops: list[Literal["rice", "soybeans", "poultry"]] = []
    language: Literal["en", "es"] = "en"

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


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    county_fips: str | None = None
    primary_crops: list[Literal["rice", "soybeans", "poultry"]] | None = None
    language: Literal["en", "es"] | None = None

    @field_validator("county_fips")
    @classmethod
    def validate_fips(cls, v: str | None) -> str | None:
        if v is not None and v not in AR_COUNTIES:
            raise ValueError(f"county_fips {v!r} is not a valid Arkansas county FIPS")
        return v
