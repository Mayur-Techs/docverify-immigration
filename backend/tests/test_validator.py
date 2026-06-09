"""
Validator tests — every rule tested against the exact bad data from the demo PDF.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from extractor.validator import validate_extraction  # noqa: E402

BAD_DATA = {
    "date_of_birth":          "13/14/1990",
    "passport_number":        "Z 12 3 45",
    "passport_issue_date":    "06/20/2023",
    "passport_expiry_date":   "01/01/2021",
    "validity_period_start":  "10/01/2026",
    "validity_period_end":    "05/01/2024",
    "status_expiry_date":     "01/15/2020",
    "annual_wage":            "8000",
    "visa_classification":    "H-1B",
    "country_of_citizenship": "INDIA123",
    "employer_fein":          "94-3456789",
    "applicant_name":         "James Robert",
    "applicant_family_name":  "James",
    "applicant_given_name":   "Robert",
    "petitioner_name":        "TechCorp Solutions Inc.",
    "employer_name":          "TechCorp Solutions Inc.",
}


def test_impossible_date_month_13():
    vr = validate_extraction({"date_of_birth": "13/14/1990"})
    errors = [f for f in vr.flags if f.field_name == "date_of_birth" and f.severity == "error"]
    assert len(errors) > 0


def test_passport_expiry_before_issue():
    vr = validate_extraction({
        "passport_issue_date": "06/20/2023",
        "passport_expiry_date": "01/01/2021",
    })
    errors = [f for f in vr.flags if f.field_name == "passport_expiry_date" and f.severity == "error"]
    assert len(errors) > 0


def test_employment_end_before_start():
    vr = validate_extraction({
        "validity_period_start": "10/01/2026",
        "validity_period_end": "05/01/2024",
    })
    errors = [f for f in vr.flags if f.field_name == "validity_period_end" and f.severity == "error"]
    assert len(errors) > 0


def test_wage_below_h1b_minimum():
    vr = validate_extraction({"annual_wage": "8000", "visa_classification": "H-1B"})
    errors = [f for f in vr.flags if f.field_name == "annual_wage" and f.severity == "error"]
    assert len(errors) > 0


def test_visa_classification_h1b_without_hyphen():
    vr = validate_extraction({"visa_classification": "H1B"})
    flags = [f for f in vr.flags if f.field_name == "visa_classification"]
    assert len(flags) > 0


def test_valid_visa_classification_not_flagged():
    """H-1B with proper hyphen must NOT trigger an error."""
    vr = validate_extraction({"visa_classification": "H-1B"})
    errors = [f for f in vr.flags if f.field_name == "visa_classification" and f.severity == "error"]
    assert len(errors) == 0


def test_valid_l1a_not_flagged():
    """L-1A with proper formatting must NOT trigger an error."""
    vr = validate_extraction({"visa_classification": "L-1A"})
    errors = [f for f in vr.flags if f.field_name == "visa_classification" and f.severity == "error"]
    assert len(errors) == 0


def test_country_with_digits():
    vr = validate_extraction({"country_of_citizenship": "INDIA123"})
    errors = [f for f in vr.flags if f.field_name == "country_of_citizenship"]
    assert len(errors) > 0


def test_clean_country_not_flagged():
    """India without digits must NOT be flagged."""
    vr = validate_extraction({"country_of_citizenship": "India"})
    errors = [f for f in vr.flags if f.field_name == "country_of_citizenship"]
    assert len(errors) == 0


def test_passport_number_with_spaces():
    vr = validate_extraction({"passport_number": "Z 12 3 45"})
    flags = [f for f in vr.flags if f.field_name == "passport_number"]
    assert len(flags) > 0


def test_clean_passport_not_flagged():
    """J8821045 is a valid Indian passport number — must not be flagged."""
    vr = validate_extraction({"passport_number": "J8821045"})
    errors = [f for f in vr.flags if f.field_name == "passport_number" and f.severity == "error"]
    assert len(errors) == 0


def test_status_expired_years_ago():
    vr = validate_extraction({"status_expiry_date": "01/15/2020"})
    flags = [f for f in vr.flags if f.field_name == "status_expiry_date" and f.severity == "warning"]
    assert len(flags) > 0


def test_name_fields_swapped():
    vr = validate_extraction({
        "applicant_name": "James Robert",
        "applicant_family_name": "James",
        "applicant_given_name": "Robert",
    })
    flags = [f for f in vr.flags if f.field_name == "applicant_family_name"]
    assert len(flags) > 0


def test_fein_valid_format():
    vr = validate_extraction({"employer_fein": "94-3456789"})
    errors = [f for f in vr.flags if f.field_name == "employer_fein"]
    assert len(errors) == 0


def test_fein_invalid_format():
    vr = validate_extraction({"employer_fein": "943456789"})
    errors = [f for f in vr.flags if f.field_name == "employer_fein" and f.severity == "error"]
    assert len(errors) > 0


def test_full_bad_document_has_errors():
    vr = validate_extraction(BAD_DATA)
    assert vr.has_errors
    assert vr.overall_penalty > 0


def test_clean_document_passes():
    clean = {
        "date_of_birth":          "03/14/1990",
        "passport_issue_date":    "01/01/2021",
        "passport_expiry_date":   "01/01/2031",
        "validity_period_start":  "10/01/2024",
        "validity_period_end":    "10/01/2027",
        "annual_wage":            "120000",
        "visa_classification":    "H-1B",
        "country_of_citizenship": "India",
        "employer_fein":          "12-3456789",
        "passport_number":        "J8821045",
    }
    vr = validate_extraction(clean)
    errors = [f for f in vr.flags if f.severity == "error"]
    assert len(errors) == 0, f"Clean doc should have no errors, got: {[f.reason for f in errors]}"


def test_overall_penalty_applied():
    vr = validate_extraction({
        "date_of_birth": "13/14/1990",
        "annual_wage": "8000",
        "visa_classification": "H-1B",
    })
    assert vr.overall_penalty > 0.5
