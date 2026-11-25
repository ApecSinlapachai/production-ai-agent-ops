"""Unit tests for the Thailand PDPA PII redaction layer (zero-leak verification)."""

import json
from pathlib import Path

from app.services.pii_redactor import find_leaked_pii, redact_payload, redact_text

FIXTURES_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fixtures" / "synthetic_payloads.json"
)


def test_redact_thai_national_id_formats() -> None:
    """Both hyphenated and contiguous 13-digit synthetic Thai IDs are fully masked."""
    text = "เลขบัตร 1-1099-00000-01-9 และอีกเลข 1109900000027"
    result = redact_text(text)

    assert result.summary.entity_counts == {"THAI_NATIONAL_ID": 2}
    assert result.summary.total_redacted == 2
    assert "[THAI_NATIONAL_ID_1]" in result.redacted_text
    assert "[THAI_NATIONAL_ID_2]" in result.redacted_text
    assert find_leaked_pii(result.redacted_text, ["1-1099-00000-01-9", "1109900000027"]) == []


def test_redact_thai_phones_emails_and_bank_accounts() -> None:
    """Phone numbers, emails, and formatted/labeled bank accounts are masked without leakage."""
    text = (
        "โทร 081-234-5678 หรือ +66 89-555-0199 "
        "อีเมล test.user@example.com บัญชี 123-4-56789-0 "
        "account no. 9876543210"
    )
    raw_values = [
        "081-234-5678",
        "+66 89-555-0199",
        "test.user@example.com",
        "123-4-56789-0",
        "9876543210",
    ]
    result = redact_text(text)

    assert result.summary.entity_counts["THAI_PHONE"] == 2
    assert result.summary.entity_counts["EMAIL"] == 1
    assert result.summary.entity_counts["BANK_ACCOUNT"] == 2
    assert find_leaked_pii(result.redacted_text, raw_values) == []
    # Masked previews must never expose full raw values
    previews_blob = " ".join(result.summary.masked_previews)
    assert find_leaked_pii(previews_blob, raw_values) == []


def test_redact_thai_and_english_person_names() -> None:
    """Thai honorifics and English titles preserve prefix while redacting the name."""
    text = "คุณสมชาย ทดสอบ ติดต่อร่วมกับ Mr. Somchai Demo และ Name: Jane Doe"
    result = redact_text(text)

    assert result.summary.entity_counts == {"PERSON_NAME": 3}
    assert "คุณ[PERSON_NAME_1]" in result.redacted_text
    assert "Mr. [PERSON_NAME_2]" in result.redacted_text
    assert "Name: [PERSON_NAME_3]" in result.redacted_text
    assert find_leaked_pii(result.redacted_text, ["สมชาย ทดสอบ", "Somchai Demo", "Jane Doe"]) == []


def test_clean_text_without_pii_passes_through_unchanged() -> None:
    """Non-PII operational messages produce zero redactions and identical text."""
    text = "Please check order ORD-2026-8841 delivery SLA."
    result = redact_text(text)

    assert result.redacted_text == text
    assert result.summary.total_redacted == 0
    assert result.summary.entity_counts == {}
    assert result.summary.masked_previews == []


def test_synthetic_fixtures_achieve_zero_pii_leak_rate() -> None:
    """Every synthetic fixture in data/fixtures/synthetic_payloads.json has 0.00 PII leak rate."""
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    assert len(fixtures) >= 5

    for case in fixtures:
        redacted_dict, summary = redact_payload({"message": case["message"]})
        leaked = find_leaked_pii(redacted_dict["message"], case["raw_pii_values"])
        assert leaked == [], f"PII leaked in {case['case_id']}: {leaked}"
        assert summary.entity_counts == case["expected_pii_entities"], (
            f"Entity count mismatch in {case['case_id']}: "
            f"{summary.entity_counts} != {case['expected_pii_entities']}"
        )
