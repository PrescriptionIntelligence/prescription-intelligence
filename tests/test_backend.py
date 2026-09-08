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
        assert flags[0]["severity"] == "warning"

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
