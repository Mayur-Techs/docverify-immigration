from __future__ import annotations

from typing import Any

# ── Document Type Schemas ─────────────────────────────────────────────────────

PASSPORT_SCHEMA = [
    {"field_name": "surname", "description": "Family name / surname on passport bio page", "required": True, "data_type": "text"},
    {"field_name": "given_names", "description": "Given names / first and middle names on passport bio page", "required": True, "data_type": "text"},
    {"field_name": "passport_number", "description": "Machine-readable passport number, top right of bio page", "required": True, "data_type": "passport_number"},
    {"field_name": "nationality", "description": "Country of citizenship as printed on passport", "required": True, "data_type": "country"},
    {"field_name": "date_of_birth", "description": "Date of birth in DD MMM YYYY or MM/DD/YYYY format", "required": True, "data_type": "date"},
    {"field_name": "date_of_issue", "description": "Passport issue date", "required": True, "data_type": "date"},
    {"field_name": "date_of_expiry", "description": "Passport expiry date — critical for visa validity checks", "required": True, "data_type": "date"},
    {"field_name": "place_of_birth", "description": "City and country of birth if shown", "required": False, "data_type": "text"},
    {"field_name": "mrz_line_1", "description": "First line of machine-readable zone at bottom of bio page", "required": False, "data_type": "text"},
    {"field_name": "mrz_line_2", "description": "Second line of machine-readable zone", "required": False, "data_type": "text"},
    {"field_name": "issuing_authority", "description": "Issuing authority or issuing state as printed", "required": False, "data_type": "text"},
]

I129_SCHEMA = [
    {"field_name": "petitioner_name", "description": "Name of petitioning employer / company filing the H-1B", "required": True, "data_type": "text"},
    {"field_name": "petitioner_fein", "description": "Federal Employer Identification Number in XX-XXXXXXX format", "required": True, "data_type": "text"},
    {"field_name": "petitioner_address", "description": "Street address of petitioning employer", "required": False, "data_type": "text"},
    {"field_name": "beneficiary_surname", "description": "Family name of the H-1B beneficiary (the worker)", "required": True, "data_type": "text"},
    {"field_name": "beneficiary_given_names", "description": "Given names of the H-1B beneficiary", "required": True, "data_type": "text"},
    {"field_name": "beneficiary_dob", "description": "Date of birth of beneficiary", "required": True, "data_type": "date"},
    {"field_name": "beneficiary_country_of_birth", "description": "Country of birth of beneficiary", "required": True, "data_type": "country"},
    {"field_name": "beneficiary_country_of_citizenship", "description": "Country of citizenship of beneficiary", "required": True, "data_type": "country"},
    {"field_name": "beneficiary_passport_number", "description": "Passport number of beneficiary", "required": True, "data_type": "passport_number"},
    {"field_name": "visa_classification", "description": "Visa classification being petitioned e.g. H-1B, H-1B1, E-3", "required": True, "data_type": "visa_code"},
    {"field_name": "job_title", "description": "Specific job title / position title as stated on petition", "required": True, "data_type": "text"},
    {"field_name": "annual_wage", "description": "Annual wage or salary offered, in USD", "required": True, "data_type": "currency"},
    {"field_name": "lca_case_number", "description": "Labor Condition Application case number, format I-200-XX-XXX-XXXXXXX", "required": True, "data_type": "text"},
    {"field_name": "validity_start", "description": "Requested employment start date", "required": True, "data_type": "date"},
    {"field_name": "validity_end", "description": "Requested employment end date", "required": True, "data_type": "date"},
    {"field_name": "petition_number", "description": "USCIS receipt number if already issued, format XXXXXXXXXXXXX", "required": False, "data_type": "text"},
    {"field_name": "priority_date", "description": "Priority date for the petition if available", "required": False, "data_type": "date"},
    {"field_name": "employer_naics_code", "description": "NAICS industry code of employer", "required": False, "data_type": "text"},
]

DS160_SCHEMA = [
    {"field_name": "surname", "description": "Family name as on DS-160 confirmation page", "required": True, "data_type": "text"},
    {"field_name": "given_names", "description": "Given names as on DS-160 confirmation page", "required": True, "data_type": "text"},
    {"field_name": "application_id", "description": "DS-160 barcode / application ID number", "required": True, "data_type": "text"},
    {"field_name": "date_of_birth", "description": "Applicant date of birth", "required": True, "data_type": "date"},
    {"field_name": "nationality", "description": "Country of citizenship", "required": True, "data_type": "country"},
    {"field_name": "passport_number", "description": "Passport number entered on DS-160", "required": True, "data_type": "passport_number"},
    {"field_name": "passport_expiry", "description": "Passport expiry date entered on DS-160", "required": True, "data_type": "date"},
    {"field_name": "visa_category", "description": "Nonimmigrant visa category applied for e.g. B-1, B-2, F-1, H-1B", "required": True, "data_type": "visa_code"},
    {"field_name": "us_contact_name", "description": "Name of US point of contact or petitioner", "required": False, "data_type": "text"},
    {"field_name": "us_contact_address", "description": "Address of US point of contact", "required": False, "data_type": "text"},
    {"field_name": "interview_location", "description": "US Embassy or Consulate where interview is scheduled", "required": False, "data_type": "text"},
    {"field_name": "travel_purpose", "description": "Purpose of travel to US as stated", "required": False, "data_type": "text"},
]

GENERAL_SCHEMA = [
    {"field_name": "document_type_detected", "description": "What type of immigration document this appears to be", "required": True, "data_type": "text"},
    {"field_name": "applicant_surname", "description": "Family name of the primary applicant", "required": False, "data_type": "text"},
    {"field_name": "applicant_given_names", "description": "Given names of the primary applicant", "required": False, "data_type": "text"},
    {"field_name": "date_of_birth", "description": "Date of birth if present", "required": False, "data_type": "date"},
    {"field_name": "nationality", "description": "Country of citizenship if present", "required": False, "data_type": "country"},
    {"field_name": "passport_number", "description": "Passport number if present", "required": False, "data_type": "passport_number"},
    {"field_name": "status_expiry", "description": "Immigration status expiry date or D/S if Duration of Status", "required": False, "data_type": "date"},
    {"field_name": "document_number", "description": "Any primary document reference number", "required": False, "data_type": "text"},
    {"field_name": "issue_date", "description": "Date document was issued", "required": False, "data_type": "date"},
    {"field_name": "expiry_date", "description": "Date document expires", "required": False, "data_type": "date"},
]


def get_schema_for_type(document_type: str) -> list[dict[str, Any]]:
    """Returns the strict field schema for a given document type."""
    normalized = document_type.strip().lower()
    if normalized == "passport":
        return PASSPORT_SCHEMA
    if normalized == "i129":
        return I129_SCHEMA
    if normalized == "ds160":
        return DS160_SCHEMA
    return GENERAL_SCHEMA


def get_liberate_mapping(document_type: str) -> dict[str, str | None]:
    """
    Returns mapping from internal schema to Linetime Liberate field names.
    Values are None pending schema definition from IT director.
    """
    schema = get_schema_for_type(document_type)
    return {field["field_name"]: None for field in schema}
