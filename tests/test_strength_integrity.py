"""
tests/test_strength_integrity.py
=================================
Regression tests for prescription-strength integrity.

Verifies that throughout the complete pipeline:

1. The prescribed strength (from the prescription text) is preserved
   and never silently replaced by the vocabulary reference strength.
2. The vocabulary reference strength is stored separately.
3. A matching strength produces no conflict and no review flag.
4. A conflicting strength produces strength_conflict and review_required.

These tests complement the Warfarin-specific tests already present in
tests/test_backend.py and the plan-override test in
tests/test_prescription_plan_integration.py.

No new infrastructure is introduced.
No existing tests are modified.
"""

from __future__ import annotations

import pytest

from backend.services.prescription_pipeline import process_prescription
from backend.services.medicine_resolver import (
    resolve_medicine_candidate,
    _strength_compatibility,
)


# =========================================================
# Helpers
# =========================================================


def _extract_strength_fields(medicine: dict) -> dict:
    """
    Return the key strength-related fields from a pipeline medicine record.
    """
    resolution = medicine.get("resolution") or {}
    evidence = resolution.get("evidence") or {}
    top_hyp = resolution.get("top_hypothesis") or {}

    return {
        "prescribed_value": medicine.get("strength_value"),
        "prescribed_unit": medicine.get("strength_unit"),
        "reference_value": top_hyp.get("strength_value"),
        "reference_unit": top_hyp.get("strength_unit"),
        "strength_compatible": evidence.get("strength_compatible"),
        "strength_reason": evidence.get("strength_reason"),
        "raw_strength_verified": medicine.get("raw_strength_verified"),
        "strength_verification": medicine.get("strength_verification"),
        "needs_review": medicine.get("needs_review"),
    }


# =========================================================
# 1. Prescribed strength is preserved — not overwritten
# =========================================================


class TestPrescribedStrengthPreservation:

    def test_warfarin_5mg_prescribed_strength_preserved(self):
        """Prescribed 5 mg must survive the full pipeline unchanged."""
        result = process_prescription(
            "Warfarin 5 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert med.get("generic_name") == "Warfarin"
        assert f["prescribed_value"] == 5.0
        assert f["prescribed_unit"] == "mg"

    def test_warfarin_10mg_prescribed_strength_preserved(self):
        """
        Prescribed 10 mg must survive even though the vocabulary says 5 mg.
        The pipeline must never silently overwrite 10 with 5.
        """
        result = process_prescription(
            "Warfarin 10 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert med.get("generic_name") == "Warfarin"
        # The prescribed value must be 10, NOT 5 (vocabulary reference).
        assert f["prescribed_value"] == 10.0, (
            f"Prescribed strength was overwritten. "
            f"Expected 10.0 mg but got {f['prescribed_value']} {f['prescribed_unit']}"
        )
        assert f["prescribed_unit"] == "mg"

    def test_aspirin_150mg_prescribed_strength_preserved(self):
        """Prescribed 150 mg must survive even though the vocabulary says 75 mg."""
        result = process_prescription(
            "Aspirin 150 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert med.get("generic_name") == "Aspirin"
        assert f["prescribed_value"] == 150.0, (
            f"Prescribed strength was overwritten. "
            f"Expected 150.0 mg but got {f['prescribed_value']}"
        )
        assert f["prescribed_unit"] == "mg"

    def test_amoxicillin_250mg_prescribed_strength_preserved(self):
        """Prescribed 250 mg must survive even though the vocabulary says 500 mg."""
        result = process_prescription(
            "Amoxicillin 250 mg\nTake 1 capsule twice daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert med.get("generic_name") == "Amoxicillin"
        assert f["prescribed_value"] == 250.0, (
            f"Prescribed strength was overwritten. "
            f"Expected 250.0 mg but got {f['prescribed_value']}"
        )
        assert f["prescribed_unit"] == "mg"


# =========================================================
# 2. Prescribed and reference strength are stored separately
# =========================================================


class TestPrescribedAndReferenceAreDistinct:

    def test_warfarin_10mg_prescribed_and_reference_differ(self):
        """
        The prescribed strength (10 mg) and the reference strength (5 mg)
        must both be present and must not be the same value.
        """
        result = process_prescription(
            "Warfarin 10 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        # Prescribed comes from the prescription text.
        assert f["prescribed_value"] == 10.0
        assert f["prescribed_unit"] == "mg"

        # Reference comes from the vocabulary (top_hypothesis).
        assert f["reference_value"] is not None, (
            "Reference strength must be present in top_hypothesis"
        )
        try:
            ref_numeric = float(f["reference_value"])
        except (TypeError, ValueError):
            pytest.fail(
                f"Reference value {f['reference_value']!r} is not numeric"
            )

        assert ref_numeric == 5.0, (
            f"Expected reference strength 5.0 mg but got {ref_numeric}"
        )
        assert f["reference_unit"] == "mg"

        # The two values must differ — they are not accidentally unified.
        assert f["prescribed_value"] != ref_numeric, (
            "Prescribed strength must not equal reference strength for conflict case"
        )

    def test_aspirin_150mg_prescribed_and_reference_differ(self):
        """
        Prescribed 150 mg vs reference 75 mg must be stored separately.
        """
        result = process_prescription(
            "Aspirin 150 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["prescribed_value"] == 150.0
        ref_numeric = float(f["reference_value"])
        assert ref_numeric == 75.0
        assert f["prescribed_value"] != ref_numeric

    def test_amoxicillin_250mg_prescribed_and_reference_differ(self):
        """
        Prescribed 250 mg vs reference 500 mg must be stored separately.
        """
        result = process_prescription(
            "Amoxicillin 250 mg\nTake 1 capsule twice daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["prescribed_value"] == 250.0
        ref_numeric = float(f["reference_value"])
        assert ref_numeric == 500.0
        assert f["prescribed_value"] != ref_numeric


# =========================================================
# 3. Matching strength — no conflict, no review
# =========================================================


class TestMatchingStrengthNoConflict:

    def test_warfarin_5mg_no_conflict(self):
        result = process_prescription(
            "Warfarin 5 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is True
        assert f["raw_strength_verified"] is True
        assert f["strength_reason"] == "strength_match"
        assert f["needs_review"] is False

        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags == [], (
            f"Unexpected strength_conflict flags: {conflict_flags}"
        )

    def test_aspirin_75mg_no_conflict(self):
        result = process_prescription(
            "Aspirin 75 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is True
        assert f["raw_strength_verified"] is True
        assert f["needs_review"] is False

    def test_amoxicillin_500mg_no_conflict(self):
        result = process_prescription(
            "Amoxicillin 500 mg\nTake 1 capsule twice daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is True
        assert f["raw_strength_verified"] is True
        assert f["needs_review"] is False


# =========================================================
# 4. Conflicting strength — requires review, correct flags
# =========================================================


class TestConflictingStrengthRequiresReview:

    def test_warfarin_10mg_conflict(self):
        """Warfarin 10 mg vs reference 5 mg must produce strength_conflict."""
        result = process_prescription(
            "Warfarin 10 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is False
        assert f["raw_strength_verified"] is False
        assert f["needs_review"] is True
        assert "strength_conflict" in (f["strength_reason"] or "")
        assert "strength_conflict" in (f["strength_verification"] or "")

        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags, "Expected at least one strength_conflict safety flag"

    def test_aspirin_150mg_conflict(self):
        """Aspirin 150 mg vs reference 75 mg must produce strength_conflict."""
        result = process_prescription(
            "Aspirin 150 mg\nTake 1 tablet once daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is False
        assert f["raw_strength_verified"] is False
        assert f["needs_review"] is True

        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags, "Expected at least one strength_conflict safety flag"

    def test_amoxicillin_250mg_conflict(self):
        """Amoxicillin 250 mg vs reference 500 mg must produce strength_conflict."""
        result = process_prescription(
            "Amoxicillin 250 mg\nTake 1 capsule twice daily."
        )
        assert result["medicines"]
        med = result["medicines"][0]
        f = _extract_strength_fields(med)

        assert f["strength_compatible"] is False
        assert f["raw_strength_verified"] is False
        assert f["needs_review"] is True

        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags, "Expected at least one strength_conflict safety flag"


# =========================================================
# 5. Strength conflict safety flag carries both values
# =========================================================


class TestStrengthConflictFlagContent:

    def test_warfarin_conflict_flag_has_prescription_and_reference(self):
        """
        The strength_conflict safety flag must carry both the prescription
        strength and the reference strength so a pharmacist can see both
        values without reading the raw OCR text.
        """
        result = process_prescription(
            "Warfarin 10 mg\nTake 1 tablet once daily."
        )
        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags, "Expected a strength_conflict flag"
        flag = conflict_flags[0]

        # Both sides of the conflict must be present.
        assert flag.get("prescription_strength") is not None, (
            "Flag must include prescription_strength"
        )
        assert flag.get("reference_strength") is not None, (
            "Flag must include reference_strength"
        )

        # Verify the prescription strength is the PRESCRIBED one (10 mg),
        # not the vocabulary reference (5 mg).
        pres = str(flag["prescription_strength"])
        ref = str(flag["reference_strength"])
        assert "10" in pres, (
            f"prescription_strength should contain '10', got {pres!r}"
        )
        assert "5" in ref, (
            f"reference_strength should contain '5', got {ref!r}"
        )

    def test_aspirin_conflict_flag_has_prescription_and_reference(self):
        result = process_prescription(
            "Aspirin 150 mg\nTake 1 tablet once daily."
        )
        conflict_flags = [
            fl for fl in result.get("safety_flags", [])
            if fl.get("type") == "strength_conflict"
        ]
        assert conflict_flags
        flag = conflict_flags[0]

        pres = str(flag.get("prescription_strength", ""))
        ref = str(flag.get("reference_strength", ""))
        assert "150" in pres
        assert "75" in ref


# =========================================================
# 6. Unit-level: _strength_compatibility correctness
# =========================================================


class TestStrengthCompatibilityUnit:

    def test_identical_values_and_units_are_compatible(self):
        candidate = {"strength_value": "5", "strength_unit": "mg"}
        hypothesis = {"strength_value": "5", "strength_unit": "mg"}
        compatible, reason = _strength_compatibility(candidate, hypothesis)
        assert compatible is True
        assert reason == "strength_match"

    def test_different_values_same_unit_produce_conflict(self):
        candidate = {"strength_value": "10", "strength_unit": "mg"}
        hypothesis = {"strength_value": "5", "strength_unit": "mg"}
        compatible, reason = _strength_compatibility(candidate, hypothesis)
        assert compatible is False
        assert "strength_conflict" in reason
        assert "10mg" in reason
        assert "5mg" in reason

    def test_different_units_produce_unit_conflict(self):
        candidate = {"strength_value": "5", "strength_unit": "mg"}
        hypothesis = {"strength_value": "5", "strength_unit": "mcg"}
        compatible, reason = _strength_compatibility(candidate, hypothesis)
        assert compatible is False
        assert "unit_conflict" in reason

    def test_missing_candidate_strength_returns_none(self):
        candidate = {}
        hypothesis = {"strength_value": "5", "strength_unit": "mg"}
        compatible, reason = _strength_compatibility(candidate, hypothesis)
        assert compatible is None
        assert "candidate_strength_unavailable" in reason

    def test_missing_hypothesis_strength_returns_none(self):
        candidate = {"strength_value": "5", "strength_unit": "mg"}
        hypothesis = {}
        compatible, reason = _strength_compatibility(candidate, hypothesis)
        assert compatible is None
        assert "hypothesis_strength_unavailable" in reason
