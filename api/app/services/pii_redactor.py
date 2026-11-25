"""Deterministic Thailand PDPA PII redaction layer (pre-LLM & pre-log).

Masks Thai National IDs, Thai phone numbers, email addresses, bank account numbers,
and structured Thai/English personal names before any payload reaches an external LLM,
application log, or PostgreSQL table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.agent import RedactionSummary

# Ordered from most specific/longest to least specific to prevent partial overlaps
# (e.g., 13-digit Thai National IDs must be redacted before 10-digit phone/bank patterns).
_THAI_NATIONAL_ID_RE = re.compile(
    r"(?<!\d)(?:\d[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d|\d{13})(?!\d)"
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_THAI_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+66[\s-]?(?:0)?[689]\d[\s-]?\d{3}[\s-]?\d{4}"
    r"|0[689]\d[\s-]?\d{3}[\s-]?\d{4}"
    r"|02[\s-]?\d{3}[\s-]?\d{4})(?!\d)"
)
_BANK_ACCOUNT_FORMATTED_RE = re.compile(
    r"(?<!\d)(?:\d{3}-\d-\d{5}-\d|\d{3}-\d{6}-\d)(?!\d)"
)
_BANK_ACCOUNT_LABELED_RE = re.compile(
    r"((?:เลขบัญชี|บัญชีธนาคาร|บัญชี|account\s*(?:no\.?|number|#)?|acct\.?)\s*[:#]?\s*)"
    r"(\d[\d\s-]{8,14}\d)",
    re.IGNORECASE,
)
_THAI_NAME_RE = re.compile(
    r"(?P<prefix>(?:คุณ|นาย|นางสาว|นาง|น\.ส\.|ดร\.))\s*"
    r"(?P<name>[\u0E00-\u0E7F]{2,25}(?:[ \t]+[\u0E00-\u0E7F]{2,25})?)"
)
_EN_NAME_RE = re.compile(
    r"(?P<prefix>(?:Mr\.|Mrs\.|Ms\.|Dr\.|Customer:|Name:))\s*"
    r"(?P<name>[A-Z][a-z]{1,24}(?:[ \t]+[A-Z][a-z]{1,24})?)"
)


@dataclass(frozen=True)
class RedactionResult:
    """Output of redacting a single text string."""

    redacted_text: str
    summary: RedactionSummary


def _mask_preview(entity_type: str, raw_value: str) -> str:
    """Create a non-reversible masked preview safe for audit display."""
    cleaned = raw_value.strip()
    if entity_type == "EMAIL" and "@" in cleaned:
        local, domain = cleaned.split("@", 1)
        head = local[0] if local else "*"
        return f"EMAIL: {head}***@{domain}"
    if entity_type == "THAI_NATIONAL_ID":
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 13:
            return f"THAI_NATIONAL_ID: {digits[0]}-****-*****-**-{digits[-1]}"
        return "THAI_NATIONAL_ID: *************"
    if entity_type == "THAI_PHONE":
        digits = re.sub(r"\D", "", cleaned)
        tail = digits[-2:] if len(digits) >= 2 else "**"
        return f"THAI_PHONE: ***-***-**{tail}"
    if entity_type == "BANK_ACCOUNT":
        digits = re.sub(r"\D", "", cleaned)
        tail = digits[-2:] if len(digits) >= 2 else "**"
        return f"BANK_ACCOUNT: ***-*-***{tail}-*"
    if entity_type == "PERSON_NAME":
        head = cleaned[0] if cleaned else "*"
        return f"PERSON_NAME: {head}***"
    return f"{entity_type}: ***"


def redact_text(text: str) -> RedactionResult:
    """Redact all supported PDPA PII entities from a string deterministically."""
    if not text:
        return RedactionResult(redacted_text=text, summary=RedactionSummary())

    entity_counts: dict[str, int] = {}
    masked_previews: list[str] = []

    def _register(entity_type: str, raw_value: str) -> str:
        count = entity_counts.get(entity_type, 0) + 1
        entity_counts[entity_type] = count
        masked_previews.append(_mask_preview(entity_type, raw_value))
        return f"[{entity_type}_{count}]"

    redacted = text

    # 1. Thai National IDs (13 digits)
    redacted = _THAI_NATIONAL_ID_RE.sub(
        lambda m: _register("THAI_NATIONAL_ID", m.group(0)),
        redacted,
    )

    # 2. Email addresses
    redacted = _EMAIL_RE.sub(
        lambda m: _register("EMAIL", m.group(0)),
        redacted,
    )

    # 3. Thai phone numbers (+66, 06x/08x/09x, 02)
    redacted = _THAI_PHONE_RE.sub(
        lambda m: _register("THAI_PHONE", m.group(0)),
        redacted,
    )

    # 4. Formatted Thai bank accounts (XXX-X-XXXXX-X / XXX-XXXXXX-X)
    redacted = _BANK_ACCOUNT_FORMATTED_RE.sub(
        lambda m: _register("BANK_ACCOUNT", m.group(0)),
        redacted,
    )

    # 5. Labeled bank account numbers (keeps label, redacts account digits)
    def _replace_labeled_bank(match: re.Match[str]) -> str:
        label = match.group(1)
        digits_raw = match.group(2)
        digits_only = re.sub(r"\D", "", digits_raw)
        if len(digits_only) < 9:
            return match.group(0)
        return f"{label}{_register('BANK_ACCOUNT', digits_raw)}"

    redacted = _BANK_ACCOUNT_LABELED_RE.sub(_replace_labeled_bank, redacted)

    # 6. Thai personal names with honorifics (preserves honorific, redacts name)
    redacted = _THAI_NAME_RE.sub(
        lambda m: f"{m.group('prefix')}{_register('PERSON_NAME', m.group('name'))}",
        redacted,
    )

    # 7. English personal names with titles/labels
    redacted = _EN_NAME_RE.sub(
        lambda m: f"{m.group('prefix')} {_register('PERSON_NAME', m.group('name'))}",
        redacted,
    )

    summary = RedactionSummary(
        total_redacted=sum(entity_counts.values()),
        entity_counts=entity_counts,
        masked_previews=masked_previews,
    )
    return RedactionResult(redacted_text=redacted, summary=summary)


def redact_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], RedactionSummary]:
    """Recursively redact all string values inside a JSON-compatible dictionary."""
    merged_counts: dict[str, int] = {}
    merged_previews: list[str] = []

    def _walk(value: Any) -> Any:
        if isinstance(value, str):
            result = redact_text(value)
            for entity, count in result.summary.entity_counts.items():
                merged_counts[entity] = merged_counts.get(entity, 0) + count
            merged_previews.extend(result.summary.masked_previews)
            return result.redacted_text
        if isinstance(value, dict):
            return {k: _walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(item) for item in value]
        return value

    redacted_dict = _walk(payload)
    summary = RedactionSummary(
        total_redacted=sum(merged_counts.values()),
        entity_counts=merged_counts,
        masked_previews=merged_previews,
    )
    return redacted_dict, summary


def find_leaked_pii(text: str, raw_values: list[str]) -> list[str]:
    """Return any raw PII strings that still appear verbatim in `text`."""
    return [value for value in raw_values if value and value in text]
