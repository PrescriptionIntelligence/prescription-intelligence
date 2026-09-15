"""
Focused tests for the canonical prescription plan and
structural prescription safety layers.

These tests verify structural interpretation and review
behavior. They do not make clinical treatment decisions.
"""

import pytest

from backend.services.prescription_plan_builder import (
    build_medicine_plan,
)
from backend.services.prescription_safety import (
    analyze_medicine_plan,
    analyze_prescription_safety,
)


# ============================================================
# Plan-builder fixtures
# ============================================================


def _medicine(
    *,
    raw_name="Paracetamol",
    normalized_name="Paracetamol",
    generic_name="Paracetamol",
    strength_value=500.0,
    strength_unit="mg",
    dose_value=1.0,
    dose_unit="tablet",
    frequency_value=2.0,
    frequency_unit="daily",
    duration_value=5.0,
    duration_unit="days",
    route="oral",
    raw_text=None,
):
    if raw_text is None:
        raw_text = (
            f"{raw_name} {strength_value:g} {strength_unit} "
            f"{dose_value:g} {dose_unit} "
            "twice daily for "
            f"{duration_value:g} {duration_unit}"
        )

    return {
        "raw_name": raw_name,
        "normalized_name": normalized_name,
        "generic_name": generic_name,
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "dose_value": dose_value,
        "dose_unit": dose_unit,
        "frequency_value": frequency_value,
        "frequency_unit": frequency_unit,
        "duration_value": duration_value,
        "duration_unit": duration_unit,
        "route": route,
        "raw_text": raw_text,
        "resolution_status": "resolved",
        "resolution": {
            "status": "resolved",
            "top_hypothesis": {
                "brand_name": normalized_name,
                "generic_name": generic_name,
                "strength_value": strength_value,
                "strength_unit": strength_unit,
                "dosage_form": dose_unit,
            },
            "top_score": 0.98,
            "reason": "Exact curated medicine match.",
        },
    }


# ============================================================
# Structural-safety fixtures
# ============================================================


def _safety_plan(
    *,
    name="Paracetamol",
    strength_value=500.0,
    strength_unit="mg",
    quantity=1.0,
    frequency="twice_daily",
    duration={"value": 5.0, "unit": "days"},
    route="oral",
    resolution_status="resolved",
    confidence=0.95,
    instruction_needs_review=False,
    instruction_text="Take 1 tablet twice daily for 5 days by mouth",
):
    """
    Minimal medicine-plan shape for prescription_safety.py.
    """

    return {
        "medicine": {
            "raw_name": name,
            "normalized_name": name,
            "generic_name": name,
            "strength_value": strength_value,
            "strength_unit": strength_unit,

            "status": resolution_status,

            "resolution": {
                "status": resolution_status,
                "top_hypothesis": {
                    "generic_name": name,
                    "strength_value": strength_value,
                    "strength_unit": strength_unit,
                },
                "reason": "Test resolution.",
            },

            "resolution_status": resolution_status,
        },

        "instructions": {
            "text": instruction_text,
            "quantity": quantity,
            "frequency": frequency,
            "duration": duration,
            "route": route,
            "needs_review": instruction_needs_review,
        },

        "confidence": confidence,
        "needs_review": instruction_needs_review,
        "review_reasons": [],
    }


def _prescription_plan(*medicines):
    return {
        "medicines": list(medicines),
    }


# ============================================================
# Plan Builder
# ============================================================


class TestPrescriptionPlanBuilder:
    def test_explicit_prescription_strength_takes_precedence(self):
        medicine = _medicine(
            strength_value=500.0,
            strength_unit="mg",
        )

        medicine["resolution"]["top_hypothesis"][
            "strength_value"
        ] = 650.0

        plan = build_medicine_plan(medicine)

        assert plan["medicine"]["strength_value"] == 500.0
        assert plan["medicine"]["strength_unit"] == "mg"

    def test_quantity_from_structured_medicine_data(self):
        medicine = _medicine(
            dose_value=2.0,
            dose_unit="tablet",
        )

        plan = build_medicine_plan(medicine)

        assert plan["instructions"]["quantity"] == 2.0

    def test_quantity_falls_back_to_instruction_text(self):
        medicine = _medicine(
            dose_value=None,
            dose_unit=None,
            raw_text=(
                "Paracetamol 500 mg. "
                "Take 2 tablets twice daily for 5 days."
            ),
        )

        plan = build_medicine_plan(medicine)

        assert plan["instructions"]["quantity"] == 2.0

    def test_dosage_form_is_inferred_from_structured_dose_unit(self):
        medicine = _medicine(
            dose_value=1.0,
            dose_unit="capsule",
        )

        plan = build_medicine_plan(medicine)

        assert plan["medicine"]["dosage_form"].lower() == "capsule"

    def test_route_frequency_duration_are_carried_into_plan(self):
        medicine = _medicine(
            frequency_value=3.0,
            frequency_unit="daily",
            duration_value=7.0,
            duration_unit="days",
            route="oral",
        )

        plan = build_medicine_plan(medicine)

        assert plan["instructions"]["frequency"] == "three_times_daily"
        assert plan["instructions"]["duration"]["value"] == 7.0
        assert plan["instructions"]["duration"]["unit"] == "days"
        assert plan["instructions"]["route"] == "oral"


# ============================================================
# Structural Safety
# ============================================================


class TestPrescriptionStructuralSafety:
    def test_unresolved_medicine_creates_high_review_finding(self):
        medicine = _safety_plan(
            resolution_status="needs_review",
            confidence=0.90,
        )

        result = analyze_medicine_plan(medicine)

        assert any(
            issue["type"] == "medicine_identification_uncertain"
            and issue["severity"] == "high"
            for issue in result["issues"]
        )

    def test_missing_strength_creates_medium_finding(self):
        medicine = _safety_plan(
            strength_value=None,
            strength_unit=None,
        )

        result = analyze_medicine_plan(medicine)

        assert any(
            issue["type"] == "strength_missing"
            and issue["severity"] == "medium"
            for issue in result["issues"]
        )

    def test_strength_conflict_creates_high_finding(self):
        medicine = _safety_plan(
            strength_value=500.0,
            strength_unit="mg",
        )

        medicine["medicine"]["resolution"]["status"] = "needs_review"
        medicine["medicine"]["resolution"]["reason"] = "strength_conflict"

        medicine["medicine"]["resolution"]["top_hypothesis"][
            "strength_value"
        ] = 650.0

        medicine["medicine"]["resolution"]["top_hypothesis"][
            "strength_unit"
        ] = "mg"

        medicine["medicine"]["resolution"]["evidence"] = {
            "strength_compatible": False,
            "strength_reason": "strength_conflict:500mg_vs_650mg",
        }

        result = analyze_medicine_plan(medicine)

        assert any(
            issue["type"] == "strength_conflict"
            and issue["severity"] == "high"
            for issue in result["issues"]
        )

    def test_missing_quantity_creates_medium_finding(self):
        medicine = _safety_plan(
            quantity=None,
        )

        result = analyze_medicine_plan(medicine)

        assert any(
            issue["type"] == "quantity_missing"
            and issue["severity"] == "medium"
            for issue in result["issues"]
        )

    def test_missing_frequency_creates_medium_finding(self):
        medicine = _safety_plan(
            frequency=None,
        )

        result = analyze_medicine_plan(medicine)

        assert any(
            issue["type"] == "frequency_missing"
            and issue["severity"] == "medium"
            for issue in result["issues"]
        )

    @pytest.mark.parametrize(
        "kwargs,expected_type",
        [
            (
                {
                    "duration": None,
                },
                "duration_missing",
            ),
            (
                {
                    "route": None,
                },
                "route_missing",
            ),
        ],
    )
    def test_missing_duration_or_route_is_low(
        self,
        kwargs,
        expected_type,
    ):
        medicine = _safety_plan(**kwargs)

        result = analyze_medicine_plan(medicine)

        matches = [
            issue
            for issue in result["issues"]
            if issue["type"] == expected_type
        ]

        assert matches
        assert matches[0]["severity"] == "low"


# ============================================================
# Prescription-level aggregation
# ============================================================


class TestPrescriptionSafetyAggregation:
    def test_clean_plan_has_no_structural_safety_issues(self):
        medicine = _safety_plan()

        result = analyze_prescription_safety(
            _prescription_plan(medicine)
        )

        assert (
            result["safety_status"]
            == "no_structural_issues_detected"
        )
        assert result["high_severity_count"] == 0
        assert result["medium_severity_count"] == 0
        assert result["low_severity_count"] == 0

    def test_high_finding_makes_prescription_review_required(self):
        medicine = _safety_plan(
            resolution_status="needs_review",
        )

        result = analyze_prescription_safety(
            _prescription_plan(medicine)
        )

        assert result["safety_status"] == "review_required"
        assert result["high_severity_count"] >= 1

    def test_medium_finding_makes_prescription_caution(self):
        medicine = _safety_plan(
            strength_value=None,
            strength_unit=None,
        )

        # Keep the medicine otherwise structurally complete so
        # the missing-strength finding is the only finding.
        result = analyze_prescription_safety(
            _prescription_plan(medicine)
        )

        assert result["safety_status"] == "caution"
        assert result["medium_severity_count"] >= 1
        assert result["high_severity_count"] == 0

    def test_low_findings_remain_informational(self):
        medicine = _safety_plan(
            duration=None,
            route=None,
        )

        result = analyze_prescription_safety(
            _prescription_plan(medicine)
        )

        assert result["safety_status"] == "informational"
        assert result["high_severity_count"] == 0
        assert result["medium_severity_count"] == 0
        assert result["low_severity_count"] >= 1