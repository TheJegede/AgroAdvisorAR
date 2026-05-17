from pydantic import BaseModel
from typing import List, Optional, Literal


class Cause(BaseModel):
    cause: str
    explanation: str


class Product(BaseModel):
    product: str
    rate: str
    application_method: str
    pre_harvest_interval: Optional[str] = None


class Citation(BaseModel):
    document_title: str
    section: str
    url: Optional[str] = None


class ContextMeta(BaseModel):
    soil_data_available: bool
    weather_data_available: bool
    county_fips: str


class AdvisoryResponse(BaseModel):
    problem_summary: str
    likely_causes: List[Cause]
    recommended_actions: List[str]
    products_rates: List[Product]
    warnings: List[str]
    citations: List[Citation]
    confidence: Literal["High", "Medium", "Low"]
    confidence_explanation: str
    language: Literal["en", "es"]
    context_meta: ContextMeta

