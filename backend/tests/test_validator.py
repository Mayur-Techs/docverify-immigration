"""
Validator tests — every rule checked against the exact bad data from the demo PDF.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from extractor.validator import validate_extraction


# ── The exact bad data from the demo ─────────────────────
BAD_DATA = {
    "date_of_birth":          "13/14/1990",   # month 13 — impossible
    "passport_number":        "Z 12 3 45",    # spaces inside
    "passport_issue_date":    "06/20/2023",
    "passport_expiry_date":   "01/01/2021",   # expiry before issue
    "validity_period_start":  "10/01/2026",
    "validity_period_end":    "05/01/2024",   # end before start
    "status_expiry_date":     "01/15/2020",   # 6 years ago
    "annual_wage":            "8000",         # below H-1B minimum
    "visa_classification":    "H1B",          # missing hyphen
    "country_of_citizenship": "INDIA123",     # digits in country
    "employer_fein":          "94-3456789",   # valid format
    "applicant_name":         "James Robert",
    "applicant_family_name":  "James",        # given/family swapped
    "applicant_given_name":   "Robert",
    "petitioner_name":        "TechCorp Solutions Inc.",
    "employer_name":          "TechCorp Solutions Inc.",
}

def test_impossible_date_month_13():
    vr = validate_extraction({"date_of_birth": "13/14/1990"})
    errors = [f for f in vr.flags if f.field_name == "date_of_birth" and f.severity == "error"]
    assert len(errors) > 0, "Should flag month 13 as error"

def test_passport_expiry_before_issue():
    vr = validate_extraction({
        "passport_issue_date": "06/20/2023",
        "passport_expiry_date": "01/01/2021",
    })
    errors = [f for f in vr.flags if f.field_name == "passport_expiry_date" and f.severity == "error"]
    assert len(errors) > 0, "Should flag expiry before issue"

def test_employment_end_before_start():
    vr = validate_extraction({
        "validity_period_start": "10/01/2026",
        "validity_period_end":   "05/01/2024",
    })
    errors = [f for f in vr.flags if f.field_name == "validity_period_end" and f.severity == "error"]
    assert len(errors) > 0, "Should flag end before start"

def test_wage_below_h1b_minimum():
    vr = validate_extraction({
        "annual_wage": "8000",
        "visa_classification": "H-1B",
    })
    errors = [f for f in vr.flags if f.field_name == "annual_wage" and f.severity == "error"]
    assert len(errors) > 0, "Should flag $8,000 wage as below H-1B minimum"

def test_visa_classification_format():
    vr = validate_extraction({"visa_classification": "H1B"})
    flags = [f for f in vr.flags if f.field_name == "visa_classification"]
    assert len(flags) > 0, "Should flag H1B — missing hyphen"

def test_country_with_digits():
    vr = validate_extraction({"country_of_citizenship": "INDIA123"})
    errors = [f for f in vr.flags if f.field_name == "country_of_citizenship"]
    assert len(errors) > 0, "Should flag country name with digits"

def test_passport_number_with_spaces():
    vr = validate_extraction({"passport_number": "Z 12 3 45"})
    flags = [f for f in vr.flags if f.field_name == "passport_number"]
    assert len(flags) > 0, "Should flag passport number with spaces"

def test_status_expired_years_ago():
    vr = validate_extraction({"status_expiry_date": "01/15/2020"})
    flags = [f for f in vr.flags if f.field_name == "status_expiry_date" and f.severity == "warning"]
    assert len(flags) > 0, "Should warn that status expired years ago"

def test_name_fields_swapped():
    vr = validate_extraction({
        "applicant_name": "James Robert",
        "applicant_family_name": "James",
        "applicant_given_name": "Robert",
    })
    flags = [f for f in vr.flags if f.field_name == "applicant_family_name"]
    assert len(flags) > 0, "Should warn that family name 'James' does not appear correctly in full name"

def test_fein_valid_format():
    vr = validate_extraction({"employer_fein": "94-3456789"})
    fein_errors = [f for f in vr.flags if f.field_name == "employer_fein"]
    assert len(fein_errors) == 0, "94-3456789 is valid FEIN format — should not flag"

def test_fein_invalid_format():
    vr = validate_extraction({"employer_fein": "943456789"})
    errors = [f for f in vr.flags if f.field_name == "employer_fein" and f.severity == "error"]
    assert len(errors) > 0, "FEIN without hyphen should be flagged"

def test_full_bad_document_has_errors():
    vr = validate_extraction(BAD_DATA)
    assert vr.has_errors, "Full bad document should have validation errors"
    assert vr.overall_penalty > 0, "Penalty should be applied"

def test_clean_document_passes():
    clean = {
        "date_of_birth": "03/14/1990",
        "passport_issue_date": "01/01/2021",
        "passport_expiry_date": "01/01/2031",
        "validity_period_start": "10/01/2024",
        "validity_period_end": "10/01/2027",
        "annual_wage": "120000",
        "visa_classification": "H-1B",
        "country_of_citizenship": "India",
        "employer_fein": "12-3456789",
        "passport_number": "J8821045",
    }
    vr = validate_extraction(clean)
    errors = [f for f in vr.flags if f.severity == "error"]
    assert len(errors) == 0, f"Clean document should have no errors, got: {[f.reason for f in errors]}"

def test_overall_penalty_applied():
    vr = validate_extraction({"date_of_birth": "13/14/1990", "annual_wage": "8000",
                               "visa_classification": "H-1B"})
    assert vr.overall_penalty > 0.5, "Multiple errors should accumulate significant penalty"
