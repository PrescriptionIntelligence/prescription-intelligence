"""
Comprehensive tests for Prescription Intelligence backend.

Tests cover:
  - OCR quality assessment
  - Medicine candidate detection
  - Medicine normalization (using vocabulary)
  - Dose calculation
  - Prescription validator
  - Safety checker (duplicates, interactions, ambiguous, dose limits)
  - Full pipeline (process_prescription)

These tests do NOT require a running database or Tesseract.
"""
from urllib import response

import pytest

# =========================================================
# Safety checker tests
# =========================================================

from backend.services.safety_checker import (
    check_duplicate_medicines,
    check_drug_interactions,
    check_ambiguous_medicines,
    check_daily_dose_limits,
)


class TestDuplicateMedicines:

    def test_no_duplicates(self):
        medicines = [
            {"name": "Paracetamol", "generic_name": "Paracetamol"},
            {"name": "Ibuprofen", "generic_name": "Ibuprofen"},
        ]
        flags = check_duplicate_medicines(medicines)
        assert flags == []

    def test_detects_duplicate_by_generic_name(self):
        medicines = [
            {"name": "Paracetamol", "generic_name": "Paracetamol"},
            {"name": "Paracetamol 500mg", "generic_name": "Paracetamol"},
        ]
        flags = check_duplicate_medicines(medicines)
        assert len(flags) == 1
        assert flags[0]["type"] == "duplicate_medicine"
        assert flags[0]["severity"] == "medium"

    def test_detects_duplicate_case_insensitive(self):
        medicines = [
            {"name": "cetirizine", "generic_name": None},
            {"name": "Cetirizine", "generic_name": None},
        ]
        flags = check_duplicate_medicines(medicines)
        assert len(flags) == 1

    def test_empty_list(self):
        assert check_duplicate_medicines([]) == []

    def test_single_medicine(self):
        medicines = [{"name": "Omeprazole", "generic_name": "Omeprazole"}]
        assert check_duplicate_medicines(medicines) == []

    def test_medicine_with_no_name_skipped(self):
        medicines = [
            {"name": None, "generic_name": None},
            {"name": None, "generic_name": None},
        ]
        flags = check_duplicate_medicines(medicines)
        assert flags == []


class TestDrugInteractions:

    def test_no_interactions(self):
        medicines = [
            {"name": "Amoxicillin", "generic_name": "Amoxicillin"},
            {"name": "Omeprazole", "generic_name": "Omeprazole"},
        ]
        flags = check_drug_interactions(medicines)
        assert flags == []

    def test_warfarin_aspirin_interaction(self):
        medicines = [
            {"name": "Warfarin", "generic_name": "Warfarin"},
            {"name": "Aspirin", "generic_name": "Aspirin"},
        ]
        flags = check_drug_interactions(medicines)
        assert len(flags) == 1
        assert flags[0]["type"] == "drug_interaction"
        assert flags[0]["severity"] == "high"
        assert "Warfarin" in flags[0]["message"] or "warfarin" in flags[0]["message"].lower()

    def test_warfarin_ibuprofen_interaction(self):
        medicines = [
            {"name": "Warfarin", "generic_name": "Warfarin"},
            {"name": "Ibuprofen", "generic_name": "Ibuprofen"},
        ]
        flags = check_drug_interactions(medicines)
        assert len(flags) == 1
        assert flags[0]["severity"] == "high"

    def test_empty_list(self):
        assert check_drug_interactions([]) == []

    def test_single_medicine_no_interaction(self):
        medicines = [{"name": "Warfarin", "generic_name": "Warfarin"}]
        flags = check_drug_interactions(medicines)
        assert flags == []


class TestAmbiguousMedicines:

    def test_high_confidence_not_flagged(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "normalization_confidence": 0.95,
                "needs_review": False,
                "status": "VERIFIED",
            }
        ]
        flags = check_ambiguous_medicines(medicines)
        assert flags == []

    def test_low_confidence_flagged(self):
        medicines = [
            {
                "name": "Unknown Drug",
                "generic_name": "Unknown Drug",
                "normalization_confidence": 0.50,
                "needs_review": False,
                "status": "",
            }
        ]
        flags = check_ambiguous_medicines(medicines)
        assert len(flags) == 1
        assert flags[0]["type"] == "low_identification_confidence"

    def test_needs_review_flagged(self):
        medicines = [
            {
                "name": "Ambiguous Medicine",
                "generic_name": "Ambiguous Medicine",
                "normalization_confidence": 0.80,
                "needs_review": True,
                "status": "",
            }
        ]
        flags = check_ambiguous_medicines(medicines)
        assert len(flags) == 1
        assert flags[0]["type"] == "ambiguous_medicine"

    def test_unknown_status_flagged(self):
        medicines = [
            {
                "name": "Something",
                "generic_name": "Something",
                "normalization_confidence": 0.80,
                "needs_review": False,
                "status": "UNKNOWN",
            }
        ]
        flags = check_ambiguous_medicines(medicines)
        assert len(flags) == 1

    def test_empty_list(self):
        assert check_ambiguous_medicines([]) == []


class TestDailyDoseLimits:

    def test_within_limit(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "daily_dose_value": 2000.0,
                "daily_dose_unit": "mg",
            }
        ]
        flags = check_daily_dose_limits(medicines)
        assert flags == []

    def test_exceeds_paracetamol_limit(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "daily_dose_value": 6000.0,
                "daily_dose_unit": "mg",
            }
        ]
        flags = check_daily_dose_limits(medicines)
        assert len(flags) == 1
        assert flags[0]["type"] == "daily_dose_limit_exceeded"
        assert flags[0]["severity"] == "high"

    def test_exceeds_cetirizine_limit(self):
        medicines = [
            {
                "name": "Cetirizine",
                "generic_name": "Cetirizine",
                "daily_dose_value": 20.0,
                "daily_dose_unit": "mg",
            }
        ]
        flags = check_daily_dose_limits(medicines)
        assert len(flags) == 1

    def test_no_daily_dose_skipped(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "daily_dose_value": None,
                "daily_dose_unit": None,
            }
        ]
        flags = check_daily_dose_limits(medicines)
        assert flags == []

    def test_unknown_medicine_not_flagged(self):
        medicines = [
            {
                "name": "ExoticDrugXYZ",
                "generic_name": "ExoticDrugXYZ",
                "daily_dose_value": 99999.0,
                "daily_dose_unit": "mg",
            }
        ]
        # We don't flag medicines we don't have data on.
        flags = check_daily_dose_limits(medicines)
        assert flags == []


# =========================================================
# Dose calculator tests
# =========================================================

from backend.services.dose_calculator import calculate_daily_dose, calculate_daily_doses


class TestDoseCalculator:

    def test_normal_dose_calculation(self):
        medicine = {
            "name": "Paracetamol",
            "strength_value": 500.0,
            "strength_unit": "mg",
            "dose_value": 1.0,
            "dose_unit": "tablet",
            "frequency_value": 3.0,
            "frequency_unit": "daily",
        }
        result = calculate_daily_dose(medicine)
        assert result["daily_dose_value"] == 1500.0
        assert result["daily_dose_unit"] == "mg"

    def test_missing_strength_returns_none(self):
        medicine = {
            "name": "Paracetamol",
            "strength_value": None,
            "dose_value": 1.0,
            "frequency_value": 2.0,
        }
        result = calculate_daily_dose(medicine)
        assert result["daily_dose_value"] is None

    def test_missing_dose_returns_none(self):
        medicine = {
            "name": "Paracetamol",
            "strength_value": 500.0,
            "dose_value": None,
            "frequency_value": 2.0,
        }
        result = calculate_daily_dose(medicine)
        assert result["daily_dose_value"] is None

    def test_combination_strength(self):
        medicine = {
            "name": "Combimed",
            "strength_value": "3+2",
            "strength_components": [
                {"value": 3.0, "unit": "mg"},
                {"value": 2.0, "unit": "mg"},
            ],
            "dose_value": 1.0,
            "frequency_value": 2.0,
        }
        result = calculate_daily_dose(medicine)
        assert result["daily_dose_value"] is None  # combination
        assert len(result["daily_dose_components"]) == 2
        assert result["daily_dose_components"][0]["value"] == 6.0
        assert result["daily_dose_components"][1]["value"] == 4.0

    def test_calculate_daily_doses_list(self):
        medicines = [
            {
                "name": "Paracetamol",
                "strength_value": 500.0,
                "strength_unit": "mg",
                "dose_value": 2.0,
                "frequency_value": 2.0,
            },
            {
                "name": "Ibuprofen",
                "strength_value": 400.0,
                "strength_unit": "mg",
                "dose_value": 1.0,
                "frequency_value": 3.0,
            },
        ]
        results = calculate_daily_doses(medicines)
        assert results[0]["daily_dose_value"] == 2000.0
        assert results[1]["daily_dose_value"] == 1200.0

    def test_zero_frequency(self):
        medicine = {
            "name": "Paracetamol",
            "strength_value": 500.0,
            "dose_value": 1.0,
            "frequency_value": 0.0,
        }
        result = calculate_daily_dose(medicine)
        assert result["daily_dose_value"] == 0.0


# =========================================================
# Prescription validator tests
# =========================================================

from backend.services.prescription_validator import validate_medicines


class TestPrescriptionValidator:

    def test_valid_medicine_no_flags(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "strength_value": 500.0,
                "dose_value": 1.0,
                "frequency_value": 3.0,
                "daily_dose_value": 1500.0,
                "extraction_confidence": 0.90,
                "normalization_confidence": 0.92,
            }
        ]
        flags = validate_medicines(medicines)
        assert flags == []

    def test_missing_name_flagged(self):
        medicines = [
            {
                "name": None,
                "generic_name": None,
                "strength_value": 500.0,
            }
        ]
        flags = validate_medicines(medicines)
        assert any(f["type"] == "missing_medicine_name" for f in flags)

    def test_missing_strength_flagged(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "strength_value": None,
                "dose_value": 1.0,
                "frequency_value": 2.0,
                "extraction_confidence": 0.90,
                "normalization_confidence": 0.90,
            }
        ]
        flags = validate_medicines(medicines)
        assert any(f["type"] == "missing_strength" for f in flags)

    def test_low_extraction_confidence_flagged(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "strength_value": 500.0,
                "dose_value": 1.0,
                "frequency_value": 2.0,
                "daily_dose_value": 1000.0,
                "extraction_confidence": 0.45,
                "normalization_confidence": 0.90,
            }
        ]
        flags = validate_medicines(medicines)
        assert any(f["type"] == "low_extraction_confidence" for f in flags)

    def test_combination_strength_valid(self):
        """Combination strength such as '3+2' should be valid."""
        medicines = [
            {
                "name": "Combimed",
                "generic_name": "Combimed",
                "strength_value": "3+2",
                "dose_value": 1.0,
                "frequency_value": 2.0,
            }
        ]
        flags = validate_medicines(medicines)
        # Should not flag "invalid_strength"
        assert not any(f["type"] == "invalid_strength" for f in flags)

    def test_invalid_strength_flagged(self):
        medicines = [
            {
                "name": "Paracetamol",
                "generic_name": "Paracetamol",
                "strength_value": "-100",
                "dose_value": 1.0,
                "frequency_value": 2.0,
                "extraction_confidence": 0.90,
                "normalization_confidence": 0.90,
            }
        ]
        flags = validate_medicines(medicines)
        assert any(f["type"] == "invalid_strength" for f in flags)

    def test_empty_list_no_flags(self):
        assert validate_medicines([]) == []


# =========================================================
# OCR quality assessment tests
# =========================================================

from backend.services.prescription_pipeline import _assess_ocr_quality


class TestOCRQualityAssessment:

    def test_empty_text_fails(self):
        quality = _assess_ocr_quality("")
        assert quality["level"] == "failed"
        assert quality["score"] == 0

    def test_blank_text_fails(self):
        quality = _assess_ocr_quality("   \n  ")
        assert quality["level"] == "failed"

    def test_good_prescription_text(self):
        text = (
            "Tab Paracetamol 500mg\n"
            "Twice daily after meals\n"
            "Duration 5 days\n"
            "Tab Cetirizine 10mg\n"
            "Once daily at night\n"
        )
        quality = _assess_ocr_quality(text)
        assert quality["level"] in ("good", "fair")
        assert quality["score"] > 40

    def test_short_garbled_text_is_poor(self):
        quality = _assess_ocr_quality("abc")
        assert quality["level"] in ("poor", "failed")

    def test_quality_dict_has_required_keys(self):
        quality = _assess_ocr_quality("Tab Paracetamol 500mg once daily")
        assert "score" in quality
        assert "level" in quality
        assert "issues" in quality
        assert "word_count" in quality
        assert "line_count" in quality


# =========================================================
# Full pipeline tests
# =========================================================

from backend.services.prescription_pipeline import process_prescription


class TestPrescriptionPipeline:

    def test_empty_text_returns_structured_result(self):
        result = process_prescription("")
        assert "medicines" in result
        assert "safety_flags" in result
        assert "analysis_metadata" in result

    def test_empty_text_has_no_medicines(self):
        result = process_prescription("")
        assert result["medicines"] == []

    def test_analysis_metadata_present(self):
        result = process_prescription("Tab Paracetamol 500mg twice daily")
        meta = result["analysis_metadata"]
        assert "ocr_quality" in meta
        assert "medicine_count" in meta
        assert "safety_flag_count" in meta
        assert "needs_review" in meta

    def test_ocr_failed_text_flags_extraction_failure(self):
        result = process_prescription("abcxyz###")
        # Either extraction_failed or ambiguous/poor-quality flag
        has_quality_flag = any(
            f.get("type") in (
                "ocr_extraction_failed",
                "poor_ocr_quality",
            )
            for f in result["safety_flags"]
        )
        assert has_quality_flag or result["medicines"] == []

    def test_duplicate_detection_in_pipeline(self):
        text = (
            "Tab Paracetamol 500mg once daily\n"
            "Tab Paracetamol 500mg twice daily\n"
        )
        result = process_prescription(text)
        duplicate_flags = [
            f for f in result["safety_flags"]
            if f["type"] == "duplicate_medicine"
        ]
        # If both extractions succeed, should detect duplicate
        if len(result["medicines"]) >= 2:
            assert len(duplicate_flags) >= 1

    def test_result_structure(self):
        result = process_prescription("Tab Paracetamol 500mg")
        assert isinstance(result["medicines"], list)
        assert isinstance(result["safety_flags"], list)
        assert isinstance(result["analysis_metadata"], dict)


# =========================================================
# Bare medicine line detection + noisy OCR regression tests
# =========================================================

from backend.services.prescription_parser import (
    _is_bare_medicine_line,
    _split_prescription_blocks,
    extract_medicines,
)
from backend.services.medicine_normalizer import load_medicine_vocabulary


class TestBareMedicineLine:
    """Unit tests for the _is_bare_medicine_line() helper."""

    @pytest.fixture(scope="class")
    def vocab(self):
        return load_medicine_vocabulary()

    # ---- lines that MUST pass ----

    def test_noisy_azithromycin_passes(self, vocab):
        assert _is_bare_medicine_line("Azithromycin 200 og/ smb", vocab) is True

    def test_bare_pantoprazole_with_strength_passes(self, vocab):
        assert _is_bare_medicine_line("Pantoprazole 40mg once daily", vocab) is True

    def test_bare_paracetamol_passes(self, vocab):
        assert _is_bare_medicine_line("Paracetamol 500mg twice daily", vocab) is True

    def test_bare_cetirizine_passes(self, vocab):
        assert _is_bare_medicine_line("Cetirizine 10 mg at night", vocab) is True

    def test_alias_pcm_passes(self, vocab):
        # PCM is an alias for Paracetamol in the vocabulary
        assert _is_bare_medicine_line("PCM 500 twice daily", vocab) is True

    # ---- lines that MUST be rejected ----

    def test_patient_metadata_rejected(self, vocab):
        assert _is_bare_medicine_line("Patient 25 years old", vocab) is False

    def test_weight_metadata_rejected(self, vocab):
        assert _is_bare_medicine_line("Weight 65 kg", vocab) is False

    def test_day_instruction_rejected(self, vocab):
        assert _is_bare_medicine_line("Day 2 4.8 mL", vocab) is False

    def test_dispense_instruction_rejected(self, vocab):
        assert _is_bare_medicine_line("Dispense s mg/mL solution, 390 mL", vocab) is False

    def test_date_metadata_rejected(self, vocab):
        assert _is_bare_medicine_line("Date 12/05/2024", vocab) is False

    def test_garbled_rejected(self, vocab):
        assert _is_bare_medicine_line("xyz### @!@ 111", vocab) is False

    def test_medicine_name_without_number_rejected(self, vocab):
        # "Paracetamol allergy noted" scores 1.0 in vocabulary but has no numeric
        assert _is_bare_medicine_line("Paracetamol allergy noted", vocab) is False

    def test_continue_medicine_without_number_rejected(self, vocab):
        # "Continue Pantoprazole as before" — medicine name present, no number
        assert _is_bare_medicine_line("Continue Pantoprazole as before", vocab) is False

    def test_empty_line_rejected(self, vocab):
        assert _is_bare_medicine_line("", vocab) is False

    def test_none_equivalent_rejected(self, vocab):
        assert _is_bare_medicine_line("   ", vocab) is False


class TestNoisyHandwrittenPipeline:
    """
    Integration tests: noisy/handwritten prescriptions that lack the
    standard numbered or dosage-form-prefix format.
    """

    def test_noisy_azithromycin_produces_one_medicine(self):
        """
        Core regression: the handwritten OCR sample must surface
        Azithromycin rather than returning an empty medicines list.
        """
        raw = (
            "Azithromycin 200 og/ smb\n"
            "Day i is ah\n"
            "Day 2 4.8 mL\n"
            "Dispense s mg/mL solution, 390 mL"
        )
        result = process_prescription(raw)
        assert len(result["medicines"]) == 1

    def test_noisy_azithromycin_name_contains_azithromycin(self):
        """The resolved or raw name must refer to Azithromycin."""
        raw = (
            "Azithromycin 200 og/ smb\n"
            "Day i is ah\n"
            "Day 2 4.8 mL"
        )
        result = process_prescription(raw)
        med = result["medicines"][0]
        # The normalizer may return the brand name "Azithral" or the
        # generic "Azithromycin".  Either is acceptable — what matters
        # is that the medicine was identified, not silently dropped.
        name_text = " ".join([
            med.get("name") or "",
            med.get("generic_name") or "",
            med.get("matched_term") or "",
        ]).lower()
        assert "azithromycin" in name_text or "azithral" in name_text

    def test_noisy_azithromycin_has_low_extraction_confidence(self):
        """
        OCR noise must reduce extraction_confidence.
        The noisy line cannot match the clean strength regex so
        _parse_prescription_block assigns extraction_confidence=0.65.
        """
        raw = (
            "Azithromycin 200 og/ smb\n"
            "Day i is ah\n"
            "Day 2 4.8 mL"
        )
        result = process_prescription(raw)
        med = result["medicines"][0]
        assert med["extraction_confidence"] <= 0.70

    def test_noisy_azithromycin_no_ocr_extraction_failed_flag(self):
        """
        Once the candidate is surfaced, ocr_extraction_failed must
        NOT appear — that flag means no medicine was found at all.
        """
        raw = (
            "Azithromycin 200 og/ smb\n"
            "Day i is ah\n"
            "Day 2 4.8 mL"
        )
        result = process_prescription(raw)
        flag_types = [f["type"] for f in result["safety_flags"]]
        assert "ocr_extraction_failed" not in flag_types

    def test_bare_pantoprazole_produces_medicine(self):
        """Bare 'Pantoprazole 40mg' (no Tab prefix, no number) must work."""
        result = process_prescription("Pantoprazole 40mg once daily")
        assert len(result["medicines"]) == 1

    def test_printed_tab_prefix_unchanged(self):
        """Existing Tab-prefixed path must still work after the change."""
        result = process_prescription("Tab Paracetamol 500mg twice daily")
        assert len(result["medicines"]) == 1
        assert result["medicines"][0]["needs_review"] is False

    def test_numbered_prescription_unchanged(self):
        """Existing numbered path must still work after the change."""
        result = process_prescription(
            "1. Azithromycin 500mg\n"
            "Frequency: once daily"
        )
        assert len(result["medicines"]) == 1

    def test_garbled_text_still_zero_medicines(self):
        """Completely unreadable OCR must still produce no medicines."""
        result = process_prescription("xyz### @!@ 111")
        assert result["medicines"] == []

    def test_metadata_lines_produce_no_medicines(self):
        """
        A block of metadata lines must not be mistaken for medicines
        even though some contain numbers.
        """
        raw = (
            "Patient 25 years old\n"
            "Weight 65 kg\n"
            "Date 12/05/2024"
        )
        result = process_prescription(raw)
        assert result["medicines"] == []

    def test_medicine_in_allergy_context_not_extracted(self):
        """
        A medicine name appearing in a non-prescription sentence
        (no numeric) must not be extracted as a medicine.
        """
        result = process_prescription("Paracetamol allergy noted")
        assert result["medicines"] == []

    def test_split_blocks_numbered_still_one_block(self):
        vocab = load_medicine_vocabulary()
        blocks = _split_prescription_blocks(
            "1. Cetirizine 10mg\nDose: 1 tablet",
            vocabulary=vocab,
        )
        assert len(blocks) == 1

    def test_split_blocks_bare_medicine_one_block(self):
        vocab = load_medicine_vocabulary()
        blocks = _split_prescription_blocks(
            "Azithromycin 200 og/ smb\nDay i is ah",
            vocabulary=vocab,
        )
        assert len(blocks) == 1

    def test_split_blocks_garbled_zero_blocks(self):
        vocab = load_medicine_vocabulary()
        blocks = _split_prescription_blocks(
            "xyz### @!@ 111",
            vocabulary=vocab,
        )
        assert len(blocks) == 0


# =========================================================
# OCR text scoring (unit test, no Tesseract needed)
# =========================================================

from backend.services.ocr_service import _score_ocr_text


class TestOCRTextScorer:

    def test_empty_text_scores_zero(self):
        assert _score_ocr_text("") == 0

    def test_none_text_scores_zero(self):
        assert _score_ocr_text(None) == 0

    def test_prescription_keywords_increase_score(self):
        score_with = _score_ocr_text(
            "Tab Paracetamol 500mg twice daily after meals"
        )
        score_without = _score_ocr_text("xyz abc def ghi")
        assert score_with > score_without

    def test_short_text_penalized(self):
        score_short = _score_ocr_text("hi")
        score_long = _score_ocr_text(
            "Tab Paracetamol 500mg once daily\n"
            "Tab Cetirizine 10mg at night\n"
            "Duration 7 days\n"
        )
        assert score_long > score_short


# =========================================================
# Auth router — _authenticate helper and /auth/token tests
#
# Uses a module-scoped in-memory SQLite database so no
# PostgreSQL connection is required.
# =========================================================

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import (
    UserDB,
    OrganizationDB,
    CustomerDB,
    PrescriptionDB,
    ReviewAuditDB,
)
from backend.security import hash_password
from backend.routers.auth import _authenticate


# ------------------------------------------------------------------
# Module-scoped in-memory SQLite — one DB shared across the module.
#
# StaticPool forces every engine.connect() call to reuse the SAME
# underlying sqlite3 connection, so tables created in one session
# are visible to all other sessions (including the TestClient's
# override_get_db).  Without it, each new connection gets a fresh,
# empty in-memory database and queries fail with "no such table".
# ------------------------------------------------------------------

SQLITE_URL = "sqlite://"  # pure in-memory, no file


@pytest.fixture(scope="module")
def auth_db_engine():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def auth_db_session(auth_db_engine):
    """
    Module-scoped session. All seed fixtures write once; tests are
    read-only afterwards so no per-test rollback is needed.
    """
    Session = sessionmaker(bind=auth_db_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="module")
def active_user(auth_db_session):
    """Insert one active user, reused by every test in the module."""
    existing = (
        auth_db_session.query(UserDB)
        .filter(UserDB.email == "test@example.com")
        .first()
    )
    if existing:
        return existing

    org = OrganizationDB(name="Test Pharmacy", slug="test-pharmacy-auth")
    auth_db_session.add(org)
    auth_db_session.flush()

    user = UserDB(
        organization_id=org.id,
        name="Test User",
        email="test@example.com",
        password_hash=hash_password("correct-password"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    auth_db_session.add(user)
    auth_db_session.commit()
    auth_db_session.refresh(user)
    return user


@pytest.fixture(scope="module")
def inactive_user(auth_db_session):
    """Insert one inactive user, reused by every test in the module."""
    existing = (
        auth_db_session.query(UserDB)
        .filter(UserDB.email == "inactive@example.com")
        .first()
    )
    if existing:
        return existing

    org = OrganizationDB(name="Inactive Pharmacy", slug="inactive-pharmacy-auth")
    auth_db_session.add(org)
    auth_db_session.flush()

    user = UserDB(
        organization_id=org.id,
        name="Inactive User",
        email="inactive@example.com",
        password_hash=hash_password("password123"),
        role="pharmacist",
        is_active=False,
    )
    auth_db_session.add(user)
    auth_db_session.commit()
    auth_db_session.refresh(user)
    return user


# ------------------------------------------------------------------
# _authenticate() unit tests  (no HTTP layer)
# ------------------------------------------------------------------

class TestAuthenticateHelper:

    def test_valid_credentials_return_token(self, active_user, auth_db_session):
        result = _authenticate("test@example.com", "correct-password", auth_db_session)
        assert "access_token" in result
        assert result["token_type"] == "bearer"
        assert result["user"]["email"] == "test@example.com"

    def test_email_is_case_insensitive(self, active_user, auth_db_session):
        result = _authenticate("TEST@EXAMPLE.COM", "correct-password", auth_db_session)
        assert "access_token" in result

    def test_email_with_surrounding_whitespace(self, active_user, auth_db_session):
        result = _authenticate("  test@example.com  ", "correct-password", auth_db_session)
        assert "access_token" in result

    def test_wrong_password_raises_401(self, active_user, auth_db_session):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _authenticate("test@example.com", "wrong-password", auth_db_session)
        assert exc_info.value.status_code == 401

    def test_unknown_email_raises_401(self, active_user, auth_db_session):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _authenticate("nobody@example.com", "correct-password", auth_db_session)
        assert exc_info.value.status_code == 401

    def test_inactive_user_raises_403(self, inactive_user, auth_db_session):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _authenticate("inactive@example.com", "password123", auth_db_session)
        assert exc_info.value.status_code == 403

    def test_response_includes_user_fields(self, active_user, auth_db_session):
        result = _authenticate("test@example.com", "correct-password", auth_db_session)
        user = result["user"]
        assert user["email"] == "test@example.com"
        assert user["name"] == "Test User"
        assert user["role"] == "pharmacist"
        assert "id" in user

    def test_response_includes_organization(self, active_user, auth_db_session):
        result = _authenticate("test@example.com", "correct-password", auth_db_session)
        assert result["organization"] is not None
        assert "slug" in result["organization"]


# ------------------------------------------------------------------
# /auth/token endpoint tests  (TestClient, in-memory DB)
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_app(auth_db_engine):
    """
    Mount a TestClient for the FastAPI app, overriding get_db to use
    the same in-memory SQLite engine so no PostgreSQL is needed.
    """
    from backend.main import app

    Session = sessionmaker(bind=auth_db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def token_test_user(auth_db_session):
    """
    User created once in the shared engine, used by all HTTP endpoint tests.
    """
    existing = (
        auth_db_session.query(UserDB)
        .filter(UserDB.email == "token@example.com")
        .first()
    )
    if existing:
        return existing

    org = OrganizationDB(name="Token Pharmacy", slug="token-pharmacy")
    auth_db_session.add(org)
    auth_db_session.flush()

    user = UserDB(
        organization_id=org.id,
        name="Token User",
        email="token@example.com",
        password_hash=hash_password("token-password-99"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )
    auth_db_session.add(user)
    auth_db_session.commit()
    auth_db_session.refresh(user)
    return user


class TestTokenEndpoint:

    def test_valid_form_credentials_return_200(
        self, test_app, token_test_user
    ):
        response = test_app.post(
            "/auth/token",
            data={
                "username": "token@example.com",
                "password": "token-password-99",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_token_endpoint_wrong_password_returns_401(
        self, test_app, token_test_user
    ):
        response = test_app.post(
            "/auth/token",
            data={
                "username": "token@example.com",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401

    def test_token_endpoint_unknown_user_returns_401(
        self, test_app, token_test_user
    ):
        response = test_app.post(
            "/auth/token",
            data={
                "username": "nobody@example.com",
                "password": "doesnt-matter",
            },
        )
        assert response.status_code == 401

    def test_token_endpoint_json_body_returns_422(
        self, test_app, token_test_user
    ):
        """
        /auth/token requires form-encoded body; a JSON body must be rejected.
        """
        response = test_app.post(
            "/auth/token",
            json={
                "username": "token@example.com",
                "password": "token-password-99",
            },
        )
        assert response.status_code == 422

    def test_login_endpoint_still_accepts_json(
        self, test_app, token_test_user
    ):
        """
        Adding /auth/token must not break the existing JSON /auth/login endpoint.
        """
        response = test_app.post(
            "/auth/login",
            json={
                "email": "token@example.com",
                "password": "token-password-99",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_endpoint_rejects_form_body(
        self, test_app, token_test_user
    ):
        """
        /auth/login still requires a JSON body, not form-encoded data.
        """
        response = test_app.post(
            "/auth/login",
            data={
                "email": "token@example.com",
                "password": "token-password-99",
            },
        )
        assert response.status_code == 422

    def test_issued_token_authorizes_users_me(
        self, test_app, token_test_user
    ):
        """
        A token from /auth/token can be used with Bearer auth on /users/me.
        """
        # Get token via the OAuth2 form endpoint
        token_response = test_app.post(
            "/auth/token",
            data={
                "username": "token@example.com",
                "password": "token-password-99",
            },
        )
        assert token_response.status_code == 200
        access_token = token_response.json()["access_token"]

        # Use it on /users/me
        me_response = test_app.get(
            "/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "token@example.com"

    def test_token_and_login_issue_equivalent_tokens(
        self, test_app, token_test_user
    ):
        """
        Both endpoints produce tokens that authorize the same user on /users/me.
        """
        form_resp = test_app.post(
            "/auth/token",
            data={
                "username": "token@example.com",
                "password": "token-password-99",
            },
        )
        json_resp = test_app.post(
            "/auth/login",
            json={
                "email": "token@example.com",
                "password": "token-password-99",
            },
        )
        form_token = form_resp.json()["access_token"]
        json_token = json_resp.json()["access_token"]

        me_form = test_app.get(
            "/users/me",
            headers={"Authorization": f"Bearer {form_token}"},
        )
        me_json = test_app.get(
            "/users/me",
            headers={"Authorization": f"Bearer {json_token}"},
        )
        assert me_form.status_code == 200
        assert me_json.status_code == 200
        assert me_form.json()["email"] == me_json.json()["email"]

# =========================================================

# =========================================================
# Strength-aware medicine resolution regression tests
# =========================================================

def test_exact_strength_is_accepted():
    result = process_prescription(
        "Warfarin 5 mg\nTake 1 tablet once daily."
    )

    assert result["medicines"]

    medicine = result["medicines"][0]

    assert medicine["name"] == "Warfarin"
    assert medicine["strength_value"] == 5.0
    assert medicine["strength_unit"] == "mg"
    assert medicine["needs_review"] is False
    assert medicine["raw_strength_verified"] is True
    assert medicine["strength_verification"] == "strength_match"


def test_conflicting_strength_requires_review():
    result = process_prescription(
        "Warfarin 10 mg\nTake 1 tablet once daily."
    )

    assert result["medicines"]

    medicine = result["medicines"][0]

    assert medicine["name"] == "Warfarin"
    assert medicine["strength_value"] == 10.0
    assert medicine["strength_unit"] == "mg"
    assert medicine["needs_review"] is True
    assert medicine["raw_strength_verified"] is False
    assert (
        medicine["strength_verification"]
        == "strength_conflict:10mg_vs_5mg"
    )
    assert result["analysis_metadata"]["needs_review"] is True


def test_ocr_like_unreliable_medicine_does_not_silently_resolve():
    result = process_prescription(
        "Warfln 5 mg\nTake 1 tablet once daily."
    )

    assert result["analysis_metadata"]["needs_review"] is True

    # Current candidate detector intentionally does not force
    # an unreliable OCR typo into a medicine identity.
    if result["medicines"]:
        medicine = result["medicines"][0]
        assert medicine["needs_review"] is True
    else:
        assert any(
            flag["type"] == "ocr_extraction_failed"
            for flag in result["safety_flags"]
        )

def test_strength_conflict_is_not_reported_as_generic_ambiguity():
    result = process_prescription(
        "Warfarin 10 mg\nTake 1 tablet once daily."
    )

    medicine = result["medicines"][0]

    assert medicine["name"] == "Warfarin"
    assert medicine["needs_review"] is True
    assert medicine["strength_verification"] == (
        "strength_conflict:10mg_vs_5mg"
    )

    flag_types = [
        flag["type"]
        for flag in result["safety_flags"]
    ]

    assert "strength_conflict" in flag_types
    assert "ambiguous_medicine" not in flag_types


def test_genuine_medicine_review_still_reports_ambiguity():
    result = process_prescription(
        "UnknownDrug 5 mg\nTake 1 tablet once daily."
    )

    flag_types = [
        flag["type"]
        for flag in result["safety_flags"]
    ]

    assert (
        "ambiguous_medicine" in flag_types
        or "ocr_extraction_failed" in flag_types
    )

# ---------------------------------------------------------------------------
# Prescription review workflow tests
# ---------------------------------------------------------------------------


def _get_pharmacist_token(client, email: str, password: str) -> str:
    response = client.post(
        "/auth/token",
        data={
            "username": email,
            "password": password,
        },
    )

    assert response.status_code == 200
    return response.json()["access_token"]

@pytest.fixture
def review_prescription(auth_db_session, token_test_user):
    prescription_id = "RX-REVIEW-TEST-001"

    prescription = (
        auth_db_session.query(PrescriptionDB)
        .filter(
            PrescriptionDB.prescription_id == prescription_id
        )
        .first()
    )

    if prescription is None:
        prescription = PrescriptionDB(
            prescription_id=prescription_id,
            organization_id=token_test_user.organization_id,
            uploaded_by_id=token_test_user.id,
            status="analyzed",
        )
        auth_db_session.add(prescription)
        auth_db_session.flush()

    # Remove review history from previous tests so every
    # review test starts with a clean audit trail.
    auth_db_session.query(ReviewAuditDB).filter(
        ReviewAuditDB.prescription_id == prescription.id
    ).delete(synchronize_session=False)

    # Reset the review state before every test.
    prescription.organization_id = token_test_user.organization_id
    prescription.uploaded_by_id = token_test_user.id
    prescription.status = "analyzed"
    prescription.review_status = "pending"
    prescription.reviewed_by_id = None
    prescription.reviewed_at = None
    prescription.review_notes = None
    prescription.safety_flags = [
        {
            "type": "strength_conflict",
            "severity": "high",
            "message": (
                "Prescription strength conflicts with "
                "the resolved medicine reference."
            ),
            "prescription_strength": 10.0,
            "reference_strength": 5.0,
        },
        {
            "type": "drug_interaction",
            "severity": "high",
            "message": "Potential drug interaction detected.",
        },
        {
            "type": "dose_check",
            "severity": "low",
            "message": "Dose should be verified.",
        },
    ]

    auth_db_session.commit()
    auth_db_session.refresh(prescription)

    return prescription

def test_get_review_status(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.get(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["prescription_id"] == "RX-REVIEW-TEST-001"
    assert data["review_status"] == "pending"
    assert data["high_priority_findings"] == 2
    assert data["total_findings"] == 3
    assert data["reviewed_by_id"] is None
    assert data["reviewed_at"] is None


def test_start_review_changes_status(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "start_review",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["review_status"] == "under_review"
    assert data["reviewed_by_id"] is None
    assert data["reviewed_at"] is None


def test_confirm_creates_review_audit(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {
                    "prescription_strength": 10.0,
                    "reference_strength": 5.0,
                },
            },
            "note": "Confirmed against the original prescription.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["review_status"] == "under_review"
    assert data["reviewed_by_id"] is not None
    assert data["reviewed_at"] is not None
    assert data["review_notes"] == (
        "Confirmed against the original prescription."
    )

    history_response = client.get(
        f"/prescriptions/{review_prescription.prescription_id}/review/history",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert history_response.status_code == 200

    history = history_response.json()

    assert history["current_status"] == "under_review"
    assert len(history["audits"]) == 1

    audit = history["audits"][0]

    assert audit["action"] == "confirm"
    assert audit["previous_status"] == "pending"
    assert audit["new_status"] == "under_review"
    assert audit["finding_type"] == "strength_conflict"
    assert audit["finding_data"]["finding_index"] == 0
    assert audit["finding_data"]["prescription_strength"] == 10.0
    assert audit["finding_data"]["reference_strength"] == 5.0
    assert audit["note"] == (
        "Confirmed against the original prescription."
    )


def test_clarify_changes_status(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "clarify",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {},
            },
            "note": "Please clarify the prescribed strength.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["review_status"] == "needs_clarification"
    assert data["reviewed_by_id"] is not None
    assert data["reviewed_at"] is not None
    assert data["review_notes"] == (
        "Please clarify the prescribed strength."
    )


def test_invalid_review_action_is_rejected(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "approve_everything",
        },
    )

    assert response.status_code == 400

    data = response.json()

    assert "Invalid review action" in data["detail"]


def test_missing_review_prescription_returns_404(test_app):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.get(
        "/prescriptions/RX-DOES-NOT-EXIST/review",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Prescription not found"

def test_review_requires_authentication(
    test_app,
    review_prescription,
):
    client = test_app

    response = client.get(
        f"/prescriptions/{review_prescription.prescription_id}/review",
    )

    assert response.status_code == 401


def test_confirm_resolves_only_selected_finding(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {
                    "prescription_strength": 10.0,
                    "reference_strength": 5.0,
                },
            },
            "note": "Confirmed against the original prescription.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    # One high-priority finding remains unresolved:
    # the drug interaction.
    assert data["review_status"] == "under_review"
    assert data["high_priority_findings"] == 1
    assert data["total_findings"] == 3


def test_confirm_all_high_priority_findings_verifies_prescription(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    first_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {
                    "prescription_strength": 10.0,
                    "reference_strength": 5.0,
                },
            },
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["review_status"] == "under_review"
    assert first_response.json()["high_priority_findings"] == 1

    second_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "drug_interaction",
                "finding_index": 1,
                "finding_data": {},
            },
            "note": "Interaction reviewed and clinically accepted.",
        },
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["review_status"] == "verified"
    assert data["high_priority_findings"] == 0
    assert data["total_findings"] == 3

def test_dismiss_low_priority_finding_keeps_prescription_verified(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    # Resolve both high-priority findings first.
    first_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {},
            },
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["review_status"] == "under_review"

    second_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "drug_interaction",
                "finding_index": 1,
                "finding_data": {},
            },
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["review_status"] == "verified"
    assert second_response.json()["high_priority_findings"] == 0

    # Dismissing a LOW-priority finding must not change a
    # verified prescription to rejected.
    third_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "dismiss",
            "finding": {
                "finding_type": "dose_check",
                "finding_index": 2,
                "finding_data": {},
            },
            "note": "Low-priority dose finding reviewed and dismissed.",
        },
    )

    assert third_response.status_code == 200

    data = third_response.json()

    assert data["review_status"] == "verified"
    assert data["high_priority_findings"] == 0
    assert data["total_findings"] == 3

def test_dismiss_last_high_priority_finding_rejects_prescription(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    # Confirm the first high-priority finding.
    first_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {},
            },
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["review_status"] == "under_review"
    assert first_response.json()["high_priority_findings"] == 1

    # Dismiss the LAST remaining high-priority finding.
    second_response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "dismiss",
            "finding": {
                "finding_type": "drug_interaction",
                "finding_index": 1,
                "finding_data": {},
            },
            "note": "High-priority interaction reviewed and dismissed.",
        },
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert data["review_status"] == "rejected"
    assert data["high_priority_findings"] == 0
    assert data["total_findings"] == 3

def test_clarification_does_not_resolve_finding(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "clarify",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 0,
                "finding_data": {},
            },
            "note": "Please clarify the prescribed strength.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["review_status"] == "needs_clarification"
    assert data["high_priority_findings"] == 2


def test_review_rejects_mismatched_finding_type(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "drug_interaction",
                "finding_index": 0,
                "finding_data": {},
            },
        },
    )

    assert response.status_code == 400
    assert "does not match" in response.json()["detail"].lower()


def test_review_rejects_invalid_finding_index(
    test_app,
    review_prescription,
):
    client = test_app

    token = _get_pharmacist_token(
        client,
        "token@example.com",
        "token-password-99",
    )

    response = client.post(
        f"/prescriptions/{review_prescription.prescription_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "confirm",
            "finding": {
                "finding_type": "strength_conflict",
                "finding_index": 99,
                "finding_data": {},
            },
        },
    )

    assert response.status_code == 400
    assert "finding index" in response.json()["detail"].lower()

# =========================================================
# Prescription authorization / tenant isolation tests
# =========================================================

@pytest.fixture(scope="module")
def prescription_access_scenario(auth_db_session):
    """
    Build an isolated multi-tenant prescription scenario.

    Organization A:
        - Pharmacist A
        - Customer A
        - Prescription A

    Organization B:
        - Pharmacist B
        - Customer B
        - Prescription B

    Admin:
        - Global access
    """

    # -----------------------------------------------------
    # Organizations
    # -----------------------------------------------------

    org_a = OrganizationDB(
        name="Access Test Pharmacy A",
        slug="access-test-pharmacy-a",
    )

    org_b = OrganizationDB(
        name="Access Test Pharmacy B",
        slug="access-test-pharmacy-b",
    )

    auth_db_session.add_all([org_a, org_b])
    auth_db_session.flush()

    # -----------------------------------------------------
    # Pharmacists
    # -----------------------------------------------------

    pharmacist_a = UserDB(
        organization_id=org_a.id,
        name="Access Pharmacist A",
        email="access-pharmacist-a@example.com",
        password_hash=hash_password("password-a"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )

    pharmacist_b = UserDB(
        organization_id=org_b.id,
        name="Access Pharmacist B",
        email="access-pharmacist-b@example.com",
        password_hash=hash_password("password-b"),
        role="pharmacist",
        is_active=True,
        email_verified=True,
    )

    # -----------------------------------------------------
    # Admin
    # -----------------------------------------------------

    admin = UserDB(
        organization_id=None,
        name="Access Admin",
        email="access-admin@example.com",
        password_hash=hash_password("password-admin"),
        role="admin",
        is_active=True,
        email_verified=True,
    )

    # -----------------------------------------------------
    # Customer accounts
    # -----------------------------------------------------

    customer_user_a = UserDB(
        organization_id=None,
        name="Access Customer A",
        email="access-customer-a@example.com",
        password_hash=hash_password("password-customer-a"),
        role="customer",
        is_active=True,
        email_verified=True,
    )

    customer_user_b = UserDB(
        organization_id=None,
        name="Access Customer B",
        email="access-customer-b@example.com",
        password_hash=hash_password("password-customer-b"),
        role="customer",
        is_active=True,
        email_verified=True,
    )

    auth_db_session.add_all(
        [
            pharmacist_a,
            pharmacist_b,
            admin,
            customer_user_a,
            customer_user_b,
        ]
    )
    auth_db_session.flush()

    # -----------------------------------------------------
    # Customer profiles
    # -----------------------------------------------------

    customer_a = CustomerDB(
        user_id=customer_user_a.id,
        organization_id=org_a.id,
        customer_code="ACCESS-CUSTOMER-A",
        name="Access Customer A",
    )

    customer_b = CustomerDB(
        user_id=customer_user_b.id,
        organization_id=org_b.id,
        customer_code="ACCESS-CUSTOMER-B",
        name="Access Customer B",
    )

    auth_db_session.add_all([customer_a, customer_b])
    auth_db_session.flush()

    # -----------------------------------------------------
    # Prescriptions
    # -----------------------------------------------------

    prescription_a = PrescriptionDB(
        prescription_id="RX-ACCESS-ORG-A",
        organization_id=org_a.id,
        uploaded_by_id=pharmacist_a.id,
        customer_id=customer_a.id,
        raw_text="Paracetamol 500 mg",
        status="analyzed",
        review_status="pending",
        safety_flags=[],
        file_name="access-a.txt",
        file_type="text/plain",
    )

    prescription_b = PrescriptionDB(
        prescription_id="RX-ACCESS-ORG-B",
        organization_id=org_b.id,
        uploaded_by_id=pharmacist_b.id,
        customer_id=customer_b.id,
        raw_text="Amoxicillin 500 mg",
        status="analyzed",
        review_status="pending",
        safety_flags=[],
        file_name="access-b.txt",
        file_type="text/plain",
    )

    auth_db_session.add_all(
        [prescription_a, prescription_b]
    )
    auth_db_session.commit()

    auth_db_session.refresh(pharmacist_a)
    auth_db_session.refresh(pharmacist_b)
    auth_db_session.refresh(admin)
    auth_db_session.refresh(customer_user_a)
    auth_db_session.refresh(customer_user_b)
    auth_db_session.refresh(prescription_a)
    auth_db_session.refresh(prescription_b)

    return {
        "pharmacist_a": pharmacist_a,
        "pharmacist_b": pharmacist_b,
        "admin": admin,
        "customer_user_a": customer_user_a,
        "customer_user_b": customer_user_b,
        "prescription_a": prescription_a,
        "prescription_b": prescription_b,
    }


def _login_for_access_test(client, email, password):
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


class TestPrescriptionAuthorization:

    def test_pharmacist_can_access_same_organization_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-pharmacist-a@example.com",
            "password-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_a'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200
        assert (
            response.json()["prescription_id"]
            == "RX-ACCESS-ORG-A"
        )

    def test_pharmacist_cannot_access_different_organization_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-pharmacist-a@example.com",
            "password-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Prescription not found"

    def test_customer_can_access_own_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-customer-a@example.com",
            "password-customer-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_a'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200
        assert (
            response.json()["prescription_id"]
            == "RX-ACCESS-ORG-A"
        )

    def test_customer_cannot_access_another_customers_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-customer-a@example.com",
            "password-customer-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Prescription not found"

    def test_admin_can_access_any_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-admin@example.com",
            "password-admin",
        )

        response_a = test_app.get(
            f"/prescriptions/{scenario['prescription_a'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        response_b = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response_a.status_code == 200
        assert response_b.status_code == 200

    def test_pharmacist_cannot_review_different_organization_prescription(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-pharmacist-a@example.com",
            "password-a",
        )

        response = test_app.post(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}/review",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "action": "start_review",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "You do not have access to this prescription."
        )

    def test_pharmacist_cannot_read_different_organization_review_history(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-pharmacist-a@example.com",
            "password-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}/review/history",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "You do not have access to this prescription."
        )

    def test_pharmacist_cannot_download_different_organization_report(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-pharmacist-a@example.com",
            "password-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}/report",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Prescription not found"

    def test_customer_cannot_download_another_customers_report(
        self,
        test_app,
        prescription_access_scenario,
    ):
        scenario = prescription_access_scenario

        token = _login_for_access_test(
            test_app,
            "access-customer-a@example.com",
            "password-customer-a",
        )

        response = test_app.get(
            f"/prescriptions/{scenario['prescription_b'].prescription_id}/report",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Prescription not found"

