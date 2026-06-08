"""
Post-extraction validation layer.
Runs AFTER Groq extracts fields.
Catches bad dates, wrong formats, logical contradictions, impossible values.
Every problem found LOWERS the confidence score and adds a specific flag reason.
"""
from __future__ import annotations
import re
import logging
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("docverify.validator")

# ── Minimum H-1B prevailing wage (DOL 2024) ──────────────
H1B_MIN_WAGE_ANNUAL = 60_000   # $60k absolute floor
H1B_MIN_WAGE_HOURLY = 28.0

# ── Countries that are real — basic check ────────────────
OBVIOUSLY_BAD_COUNTRY = re.compile(r'\d')  # any digit in a country name = wrong

# ── Valid visa classifications ────────────────────────────
VALID_VISA_CLASSIFICATIONS = {
    "H-1B", "H-1B1", "H-2A", "H-2B", "H-3",
    "L-1A", "L-1B", "L-1",
    "O-1A", "O-1B", "O-1", "O-2",
    "TN", "E-3",
    "EB-1", "EB-2", "EB-3",
    "F-1", "J-1", "B-1", "B-2",
}

# ── FEIN format: XX-XXXXXXX ───────────────────────────────
FEIN_RE = re.compile(r'^\d{2}-\d{7}$')

# ── US passport: 9 digits, UK: 9 alphanumeric, Indian: 1 letter + 7 digits
PASSPORT_BAD = re.compile(r'\s')  # spaces inside passport number = wrong


@dataclass
class ValidationFlag:
    field_name: str
    severity: str          # "error" | "warning" | "info"
    reason: str
    original_value: str
    suggested_action: str


@dataclass
class ValidationResult:
    flags: list[ValidationFlag] = field(default_factory=list)
    overall_penalty: float = 0.0   # 0.0–1.0, subtracted from confidence

    def add(self, field_name: str, severity: str, reason: str,
            original_value: str, action: str, penalty: float = 0.0):
        self.flags.append(ValidationFlag(
            field_name=field_name,
            severity=severity,
            reason=reason,
            original_value=str(original_value),
            suggested_action=action,
        ))
        self.overall_penalty = min(1.0, self.overall_penalty + penalty)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.flags)

    @property
    def error_fields(self) -> list[str]:
        return [f.field_name for f in self.flags if f.severity == "error"]


def validate_extraction(fields: dict[str, str | None]) -> ValidationResult:
    """
    Run all validation checks against a dict of {field_name: field_value}.
    Returns ValidationResult with every problem found.
    """
    vr = ValidationResult()

    # ── 1. DATE FORMAT AND IMPOSSIBLE DATE VALUES ─────────
    date_fields = [
        "date_of_birth",
        "passport_issue_date",
        "passport_expiry_date",
        "validity_period_start",
        "validity_period_end",
        "status_expiry_date",
        "priority_date",
    ]
    parsed_dates: dict[str, Optional[date]] = {}
    for fname in date_fields:
        val = fields.get(fname)
        if val and val.lower() not in ("not found", "null", "none", ""):
            parsed, error = _parse_date(val)
            parsed_dates[fname] = parsed
            if parsed is None:
                vr.add(fname, "error",
                       f"Cannot parse date '{val}' — check for invalid month/day (e.g. month 13)",
                       val,
                       "Manually verify and correct the date",
                       penalty=0.3)
            else:
                # Check for obviously impossible dates
                if parsed.year < 1900 or parsed.year > 2100:
                    vr.add(fname, "error",
                           f"Year {parsed.year} is outside valid range",
                           val, "Verify year is correct", penalty=0.3)

    # ── 2. PASSPORT EXPIRY BEFORE ISSUE ──────────────────
    issue = parsed_dates.get("passport_issue_date")
    expiry = parsed_dates.get("passport_expiry_date")
    if issue and expiry:
        if expiry <= issue:
            vr.add("passport_expiry_date", "error",
                   f"Passport expiry ({expiry}) is on or before issue date ({issue})"
                   " — dates are swapped or corrupted",
                   str(expiry),
                   "Swap issue and expiry dates — they appear reversed",
                   penalty=0.4)

    # ── 3. PASSPORT ALREADY EXPIRED ──────────────────────
    if expiry:
        today = date.today()
        if expiry < today:
            vr.add("passport_expiry_date", "warning",
                   f"Passport expired on {expiry} — invalid for travel",
                   str(expiry),
                   "Client must renew passport before visa application proceeds",
                   penalty=0.2)

    # ── 4. EMPLOYMENT END BEFORE START ───────────────────
    start = parsed_dates.get("validity_period_start")
    end = parsed_dates.get("validity_period_end")
    if start and end:
        if end <= start:
            vr.add("validity_period_end", "error",
                   f"Employment end date ({end}) is before or same as start date ({start})"
                   " — dates are reversed",
                   str(end),
                   "Check petition dates — start and end appear swapped",
                   penalty=0.4)

    # ── 5. STATUS ALREADY EXPIRED ────────────────────────
    status_exp = parsed_dates.get("status_expiry_date")
    if status_exp:
        today = date.today()
        years_ago = (today - status_exp).days / 365
        if years_ago > 1:
            vr.add("status_expiry_date", "warning",
                   f"Immigration status expired {years_ago:.1f} years ago ({status_exp})"
                   " — applicant may be out of status",
                   str(status_exp),
                   "Verify current immigration status with attorney — may affect eligibility",
                   penalty=0.2)

    # ── 6. PASSPORT NUMBER FORMAT ────────────────────────
    passport = fields.get("passport_number")
    if passport and passport.lower() not in ("not found", "null", "none", ""):
        if PASSPORT_BAD.search(passport):
            vr.add("passport_number", "error",
                   f"Passport number '{passport}' contains spaces — "
                   "spaces are not part of any passport number format",
                   passport,
                   "Remove spaces from passport number",
                   penalty=0.3)
        if len(passport) < 6 or len(passport) > 15:
            vr.add("passport_number", "warning",
                   f"Passport number '{passport}' has unusual length ({len(passport)} chars)"
                   " — most passports are 8–9 characters",
                   passport,
                   "Verify passport number against physical document",
                   penalty=0.15)

    # ── 7. VISA CLASSIFICATION FORMAT ────────────────────
    visa = fields.get("visa_classification")
    if visa and visa.lower() not in ("not found", "null", "none", ""):
        visa_clean = visa.strip().upper()
        # Normalise common OCR errors: H1B → H-1B, L1A → L-1A
        normalised = re.sub(r'^([A-Z]+)(\d)', r'\1-\2', visa_clean)
        if normalised not in VALID_VISA_CLASSIFICATIONS:
            vr.add("visa_classification", "error",
                   f"'{visa}' is not a recognised visa classification. "
                   f"Did you mean '{normalised}'?",
                   visa,
                   f"Correct to standard format e.g. 'H-1B' not 'H1B'",
                   penalty=0.25)
        elif visa_clean != normalised:
            vr.add("visa_classification", "warning",
                   f"'{visa}' should be formatted as '{normalised}'",
                   visa,
                   f"Correct to '{normalised}'",
                   penalty=0.05)

    # ── 8. WAGE SANITY CHECK ─────────────────────────────
    visa_type = (fields.get("visa_classification") or "").upper().replace("-", "")
    wage_raw = fields.get("annual_wage") or fields.get("salary")
    if wage_raw and wage_raw.lower() not in ("not found", "null", "none", ""):
        wage = _parse_wage(wage_raw)
        if wage is not None:
            if "H1B" in visa_type or "H-1B" in visa_type:
                if wage < H1B_MIN_WAGE_ANNUAL:
                    vr.add("annual_wage", "error",
                           f"Annual wage ${wage:,.0f} is below the H-1B minimum prevailing "
                           f"wage threshold of ${H1B_MIN_WAGE_ANNUAL:,}. "
                           "This will fail DOL review.",
                           str(wage_raw),
                           "Verify wage — likely missing zeros (e.g. 8000 should be 80000)",
                           penalty=0.4)
            if wage < 15_000 and wage > 0:
                vr.add("annual_wage", "error",
                       f"Annual wage ${wage:,.0f} is implausibly low for any US work visa. "
                       "Value may be missing digits.",
                       str(wage_raw),
                       "Verify — likely extracted incorrectly (e.g. 8000 instead of 80000)",
                       penalty=0.35)

    # ── 9. COUNTRY NAME CONTAINS DIGITS ──────────────────
    for cfield in ["nationality", "country_of_citizenship", "country_of_birth"]:
        cval = fields.get(cfield)
        if cval and cval.lower() not in ("not found", "null", "none", ""):
            if OBVIOUSLY_BAD_COUNTRY.search(cval):
                vr.add(cfield, "error",
                       f"Country name '{cval}' contains numbers — "
                       "no valid country name contains digits",
                       cval,
                       "Remove digits — likely OCR error combining adjacent text",
                       penalty=0.3)

    # ── 10. FEIN FORMAT ───────────────────────────────────
    fein = fields.get("employer_fein")
    if fein and fein.lower() not in ("not found", "null", "none", ""):
        if not FEIN_RE.match(fein.strip()):
            vr.add("employer_fein", "error",
                   f"FEIN '{fein}' does not match required format XX-XXXXXXX "
                   "(2 digits, hyphen, 7 digits)",
                   fein,
                   "Verify FEIN from W-2 or IRS correspondence",
                   penalty=0.2)

    # ── 11. DUPLICATE FIELD DETECTION ────────────────────
    # Petitioner name vs employer name — should match
    pet = (fields.get("petitioner_name") or "").strip().lower()
    emp = (fields.get("employer_name") or "").strip().lower()
    if pet and emp and pet != emp:
        vr.add("petitioner_name", "warning",
               f"Petitioner name '{fields.get('petitioner_name')}' does not match "
               f"employer name '{fields.get('employer_name')}' — should be identical on I-129",
               str(fields.get("petitioner_name")),
               "Verify both fields refer to the same entity",
               penalty=0.1)

    # ── 12. NAME FIELD CONSISTENCY ───────────────────────
    full = (fields.get("applicant_name") or "").strip()
    family = (fields.get("applicant_family_name") or "").strip()
    given = (fields.get("applicant_given_name") or "").strip()
    if full and family and given:
        full_parts = [p.lower() for p in full.split()]
        # If given name appears first in the full name but is stored as family name
        # e.g. full="James Robert", family="James", given="Robert" — names are swapped
        # On USCIS forms, family name always comes LAST in Western names
        # Check: if the "family" name is the FIRST word of full name and "given" is the LAST word
        # that is a classic first/last swap
        family_lower = family.lower()
        given_lower = given.lower()
        if (full_parts and
            full_parts[0] == family_lower and
            full_parts[-1] == given_lower and
            family_lower != given_lower):
            vr.add("applicant_family_name", "warning",
                   f"Family name '{family}' appears to be the first name, not last name. "
                   f"On USCIS forms, family name = surname (last name). "
                   f"'{given}' may be the correct family name.",
                   family,
                   "Verify: on I-129 'Family Name' means SURNAME (last name), not first name",
                   penalty=0.15)

    return vr


# ── Helpers ───────────────────────────────────────────────

def _parse_date(val: str) -> tuple[Optional[date], Optional[str]]:
    """Try multiple date formats. Return (date, None) or (None, error_msg)."""
    val = val.strip()
    formats = [
        "%m/%d/%Y",   # 06/20/2023
        "%d/%m/%Y",   # 20/06/2023
        "%Y-%m-%d",   # 2023-06-20
        "%d %b %Y",   # 20 Jun 2023
        "%d %B %Y",   # 20 June 2023
        "%B %d, %Y",  # June 20, 2023
        "%b %d, %Y",  # Jun 20, 2023
        "%m-%d-%Y",   # 06-20-2023
        "%d-%m-%Y",   # 20-06-2023
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt).date(), None
        except ValueError:
            continue
    return None, f"Could not parse '{val}' as a date"


def _parse_wage(val: str) -> Optional[float]:
    """Extract numeric wage from string like '$80,000', '80000', '80,000/year'."""
    cleaned = re.sub(r'[^\d.]', '', val.split('/')[0].split('per')[0])
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None
