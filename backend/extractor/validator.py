"""
Post-extraction validation layer.
Runs AFTER Groq extracts fields.
Catches bad dates, wrong formats, logical contradictions, impossible values.
Every problem found LOWERS the confidence score and adds a specific flag reason.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import datetime
from typing import Optional

logger = logging.getLogger("docverify.validator")

# ── Minimum H-1B prevailing wage (DOL 2024) ───────────────────────────────────
H1B_MIN_WAGE_ANNUAL = 60_000
IMPLAUSIBLY_LOW_WAGE = 15_000

# ── Countries: no digit should appear in a country name ───────────────────────
OBVIOUSLY_BAD_COUNTRY = re.compile(r"\d")

# ── Canonical visa classifications ────────────────────────────────────────────
VALID_VISA_CLASSIFICATIONS = {
    "H-1B", "H-1B1", "H-2A", "H-2B", "H-3",
    "L-1A", "L-1B", "L-1",
    "O-1A", "O-1B", "O-1", "O-2",
    "TN", "E-3",
    "EB-1", "EB-2", "EB-3",
    "F-1", "J-1", "B-1", "B-2",
}

# ── FEIN must be XX-XXXXXXX ───────────────────────────────────────────────────
FEIN_RE = re.compile(r"^\d{2}-\d{7}$")

# ── Any whitespace inside a passport number is wrong ──────────────────────────
PASSPORT_HAS_SPACE = re.compile(r"\s")

# ── Normalise visa strings like "H1B" → "H-1B", "L1A" → "L-1A" ──────────────
VISA_NORMALISE_RE = re.compile(r"^([A-Za-z]+)(\d)")


def _normalise_visa(raw: str) -> str:
    """Insert hyphen between leading letters and first digit if missing."""
    cleaned = raw.strip().upper()
    if "-" in cleaned:
        return cleaned
    m = VISA_NORMALISE_RE.match(cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}{cleaned[m.end():]}"
    return cleaned


@dataclass
class ValidationFlag:
    field_name: str
    severity: str
    reason: str
    original_value: str
    suggested_action: str


@dataclass
class ValidationResult:
    flags: list[ValidationFlag] = field(default_factory=list)
    overall_penalty: float = 0.0

    def add(
        self,
        field_name: str,
        severity: str,
        reason: str,
        original_value: str,
        action: str,
        penalty: float = 0.0,
    ) -> None:
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


_EMPTY = {"not found", "null", "none", "n/a", "unknown", ""}

def _is_empty(val: Optional[str]) -> bool:
    return val is None or str(val).strip().lower() in _EMPTY


def _is_valid_status_enum(value: str) -> bool:
    """Defensive check for valid non-date statuses to prevent false D/S errors."""
    if not value:
        return False
    valid = {
        "d/s", "d/s.", "ds", "duration of status","D/S", "D/S.", "DS",
        "proc", "processing", "n/a", "na", "indefinite"
    }
    return str(value).strip().lower() in valid


def validate_extraction(fields: dict[str, Optional[str]]) -> ValidationResult:
    """
    Run all validation checks.
    Returns ValidationResult listing every problem found.
    """
    vr = ValidationResult()

    # ── 1. DATE FORMAT AND IMPOSSIBLE CALENDAR VALUES ─────────────────────────
    date_field_names = [
        "date_of_birth",
        "passport_issue_date",
        "passport_expiry_date",
        "validity_period_start",
        "validity_period_end",
        "status_expiry_date",
        "priority_date",
        "status_expiry",
    ]
    parsed_dates: dict[str, Optional[date]] = {}

    for fname in date_field_names:
        val = fields.get(fname)
        if _is_empty(val):
            continue

        # Narrow the type strictly to str (fixes the Optional[str] mypy issue without suppression)
        assert val is not None

        # Skip date parsing entirely for valid enum strings
        if _is_valid_status_enum(val):
            continue

        parsed, _ = _parse_date(val)
        parsed_dates[fname] = parsed

        if parsed is None:
            vr.add(
                fname, "error",
                f"Cannot parse date '{val}' — check for invalid month/day",
                val,
                "Manually verify and correct the date",
                penalty=0.3,
            )
        elif parsed.year < 1900 or parsed.year > 2100:
            vr.add(
                fname, "error",
                f"Year {parsed.year} is outside valid range (1900–2100)",
                val,
                "Verify the year is correct",
                penalty=0.3,
            )

    # ── 2. PASSPORT EXPIRY MUST BE AFTER ISSUE ───────────────────────────────
    issue = parsed_dates.get("passport_issue_date")
    expiry = parsed_dates.get("passport_expiry_date")
    if issue and expiry and expiry <= issue:
        vr.add(
            "passport_expiry_date", "error",
            f"Passport expiry ({expiry}) is on or before issue date ({issue})",
            str(expiry),
            "Swap issue and expiry dates — they appear reversed",
            penalty=0.4,
        )

    # ── 3. PASSPORT ALREADY EXPIRED ──────────────────────────────────────────
    if expiry and expiry < date.today():
        vr.add(
            "passport_expiry_date", "warning",
            f"Passport expired on {expiry} — invalid for travel",
            str(expiry),
            "Client must renew passport before visa application proceeds",
            penalty=0.2,
        )

    # ── 4. EMPLOYMENT END MUST BE AFTER START ────────────────────────────────
    start = parsed_dates.get("validity_period_start")
    end = parsed_dates.get("validity_period_end")
    if start and end and end <= start:
        vr.add(
            "validity_period_end", "error",
            f"Employment end date ({end}) is before or same as start date ({start})",
            str(end),
            "Check petition dates — start and end appear swapped",
            penalty=0.4,
        )

    # ── 5. IMMIGRATION STATUS EXPIRED OVER A YEAR AGO ───────────────────────
    status_exp = parsed_dates.get("status_expiry_date") or parsed_dates.get("status_expiry")
    if status_exp:
        years_ago = (date.today() - status_exp).days / 365
        if years_ago > 1:
            vr.add(
                "status_expiry_date", "warning",
                f"Immigration status expired {years_ago:.1f} years ago ({status_exp})",
                str(status_exp),
                "Verify current status with attorney — applicant may be out of status",
                penalty=0.2,
            )

    # ── 6. PASSPORT NUMBER MUST NOT CONTAIN SPACES ───────────────────────────
    passport = fields.get("passport_number")
    if not _is_empty(passport):
        assert passport is not None
        if PASSPORT_HAS_SPACE.search(passport):
            vr.add(
                "passport_number", "error",
                f"Passport number '{passport}' contains spaces",
                passport,
                "Remove all spaces from the passport number",
                penalty=0.3,
            )
        if not 6 <= len(passport.strip()) <= 15:
            vr.add(
                "passport_number", "warning",
                f"Passport number '{passport}' has unusual length ({len(passport.strip())} chars)",
                passport,
                "Verify against the physical document",
                penalty=0.15,
            )

    # ── 7. VISA CLASSIFICATION FORMAT ────────────────────────────────────────
    visa = fields.get("visa_classification")
    if not _is_empty(visa):
        assert visa is not None
        normalised = _normalise_visa(visa)
        if normalised not in VALID_VISA_CLASSIFICATIONS:
            vr.add(
                "visa_classification", "error",
                f"'{visa}' is not a recognised visa classification",
                visa,
                "Correct to standard format e.g. 'H-1B' not 'H1B'",
                penalty=0.25,
            )
        elif visa.strip().upper() != normalised:
            vr.add(
                "visa_classification", "warning",
                f"'{visa}' should be formatted as '{normalised}'",
                visa,
                f"Correct to '{normalised}'",
                penalty=0.05,
            )

    # ── 8. WAGE SANITY CHECK ─────────────────────────────────────────────────
    visa_upper = (fields.get("visa_classification") or "").strip().upper()
    wage_raw = fields.get("annual_wage") or fields.get("salary")
    if not _is_empty(wage_raw):
        assert wage_raw is not None
        wage = _parse_wage(wage_raw)
        if wage is not None and wage > 0:
            is_h1b = "H-1B" in visa_upper or "H1B" in visa_upper
            if is_h1b and wage < H1B_MIN_WAGE_ANNUAL:
                vr.add(
                    "annual_wage", "error",
                    f"Wage ${wage:,.0f}/yr is below the H-1B DOL minimum",
                    str(wage_raw),
                    "Verify — likely missing zeros",
                    penalty=0.4,
                )
            elif wage < IMPLAUSIBLY_LOW_WAGE:
                vr.add(
                    "annual_wage", "error",
                    f"Wage ${wage:,.0f}/yr is implausibly low",
                    str(wage_raw),
                    "Verify — likely extracted incorrectly",
                    penalty=0.35,
                )

    # ── 9. COUNTRY NAMES MUST NOT CONTAIN DIGITS ─────────────────────────────
    for cfield in ("nationality", "country_of_citizenship", "country_of_birth", "beneficiary_country_of_birth", "beneficiary_country_of_citizenship"):
        cval = fields.get(cfield)
        if not _is_empty(cval):
            assert cval is not None
            if OBVIOUSLY_BAD_COUNTRY.search(cval):
                vr.add(
                    cfield, "error",
                    f"Country name '{cval}' contains digits",
                    cval,
                    "Remove digits — likely OCR error",
                    penalty=0.3,
                )

    # ── 10. FEIN FORMAT: XX-XXXXXXX ──────────────────────────────────────────
    fein = fields.get("employer_fein") or fields.get("petitioner_fein")
    if not _is_empty(fein):
        assert fein is not None
        if not FEIN_RE.match(fein.strip()):
            vr.add(
                "employer_fein", "error",
                f"FEIN '{fein}' does not match format XX-XXXXXXX",
                fein,
                "Verify FEIN from W-2",
                penalty=0.2,
            )

    # ── 11. PETITIONER NAME MUST MATCH EMPLOYER NAME ─────────────────────────
    pet = (fields.get("petitioner_name") or "").strip().lower()
    emp = (fields.get("employer_name") or "").strip().lower()
    if pet and emp and pet != emp:
        vr.add(
            "petitioner_name", "warning",
            "Petitioner name differs from employer name",
            str(fields.get("petitioner_name")),
            "Verify both fields refer to the same entity",
            penalty=0.1,
        )

    # ── 12. GIVEN / FAMILY NAME SWAP DETECTION ───────────────────────────────
    full = (fields.get("applicant_name") or "").strip()
    family = (fields.get("applicant_family_name") or fields.get("beneficiary_surname") or "").strip()
    given = (fields.get("applicant_given_name") or fields.get("beneficiary_given_names") or "").strip()
    if full and family and given and family.lower() != given.lower():
        full_parts = [p.lower() for p in full.split()]
        if full_parts and full_parts[0] == family.lower() and full_parts[-1] == given.lower():
            vr.add(
                "applicant_family_name", "warning",
                f"Family name '{family}' appears to be the first (given) name",
                family,
                "Verify if given/family fields are swapped",
                penalty=0.15,
            )

    return vr


def _parse_date(val: str) -> tuple[Optional[date], Optional[str]]:
    val = val.strip()
    for fmt in (
        "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d",
        "%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y",
        "%m-%d-%Y", "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(val, fmt).date(), None
        except ValueError:
            continue
    return None, f"Could not parse '{val}' as a date"


def _parse_wage(val: str) -> Optional[float]:
    trimmed = val.split("/")[0].split("per")[0].split("Per")[0]
    cleaned = re.sub(r"[^\d.]", "", trimmed)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None
