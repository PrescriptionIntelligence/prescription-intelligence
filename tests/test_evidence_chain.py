"""
Regression tests for the evidence chain builder.

Covers:
  - OCR evidence step
  - Normalization evidence step
  - Resolution evidence step (local vs external)
  - Safety evidence step
  - Full per-medicine evidence chain
  - Pipeline evidence_chains output
"""

from backend.services.evidence_chain import (
    build_ocr_evidence,
    build_normalization_evidence,
    build_resolution_evidence,
    build_safety_evidence,
    build_medicine_evidence_chain,
    EVIDENCE_SOURCE_LOCAL,
    EVIDENCE_SOURCE_EXTERNAL,
)
from backend.services.prescription_pipeline import process_prescription


# =========================================================
# OCR EVIDENCE
# =========================================================


def test_ocr_evidence_high_confidence():
    step = build_ocr_evidence(
        raw_text="Paracetamol 500mg",
        ocr_confidence=0.90,
    )

    assert step["step"] == "ocr_extraction"
    assert step["detected_text"] == "Paracetamol 500mg"
    assert step["ocr_confidence"] == 0.90
    assert step["ocr_confidence_label"] == "90%"
    assert "high" in step["note"].lower()


def test_ocr_evidence_low_confidence():
    step = build_ocr_evidence(
        raw_text="Paracetmol",
        ocr_confidence=0.35,
    )

    assert step["ocr_confidence_label"] == "35%"
    assert "low" in step["note"].lower()


def test_ocr_evidence_missing_confidence():
    step = build_ocr_evidence(
        raw_text="Some text",
        ocr_confidence=None,
    )

    assert step["ocr_confidence"] is None
    assert step["ocr_confidence_label"] == "unavailable"


def test_ocr_evidence_poor_quality_flag():
    ocr_quality = {
        "level": "poor",
        "score": 30,
        "issues": ["Very short OCR output"],
    }

    step = build_ocr_evidence(
        raw_text="rx",
        ocr_confidence=0.50,
        ocr_quality=ocr_quality,
    )

    assert step["quality_level"] == "poor"
    assert "poor" in step["note"].lower()


# =========================================================
# NORMALIZATION EVIDENCE
# =========================================================


def test_normalization_evidence_exact_match():
    step = build_normalization_evidence(
        original_text="Paracetamol",
        normalized_name="Paracetamol",
        normalization_confidence=1.00,
        matched_term="Paracetamol",
        evidence={"exact_match": True},
    )

    assert step["step"] == "normalization"
    assert step["exact_match"] is True
    assert "exact" in step["note"].lower()
    assert step["normalization_confidence_label"] == "100%"


def test_normalization_evidence_fuzzy_match():
    step = build_normalization_evidence(
        original_text="Paracetmol",
        normalized_name="Paracetamol",
        normalization_confidence=0.88,
        matched_term="Paracetamol",
        evidence={"full_text_similarity": 0.88, "ocr_corrected": True},
    )

    assert step["normalized_name"] == "Paracetamol"
    assert step["ocr_corrected"] is True
    assert "correction" in step["note"].lower()


def test_normalization_evidence_low_confidence():
    step = build_normalization_evidence(
        original_text="xyz123",
        normalized_name="Unknown",
        normalization_confidence=0.30,
        matched_term=None,
        evidence=None,
    )

    assert "low" in step["note"].lower()
    assert "uncertain" in step["note"].lower()


# =========================================================
# RESOLUTION EVIDENCE
# =========================================================


def test_resolution_evidence_accepted_local():
    resolution = {
        "status": "accepted",
        "reason": "sufficient_evidence",
        "evidence": {
            "top_score": 0.92,
            "second_score": 0.70,
            "margin": 0.22,
            "strength_compatible": True,
            "strength_reason": "strength_match",
            "external_hypothesis": False,
        },
    }

    step = build_resolution_evidence(resolution)

    assert step["step"] == "resolution"
    assert step["status"] == "accepted"
    assert step["source"] == EVIDENCE_SOURCE_LOCAL
    assert step["is_external_hypothesis"] is False
    assert "accepted" in step["note"].lower()


def test_resolution_evidence_external_hypothesis_requires_review():
    resolution = {
        "status": "needs_review",
        "reason": "external_hypothesis_requires_review",
        "evidence": {
            "top_score": 0.98,
            "second_score": None,
            "margin": None,
            "strength_compatible": None,
            "strength_reason": "hypothesis_strength_unavailable",
            "external_hypothesis": True,
        },
    }

    step = build_resolution_evidence(resolution)

    assert step["status"] == "needs_review"
    assert step["source"] == EVIDENCE_SOURCE_EXTERNAL
    assert step["is_external_hypothesis"] is True
    assert "external" in step["note"].lower()
    assert "review" in step["note"].lower()


def test_resolution_evidence_strength_conflict():
    resolution = {
        "status": "needs_review",
        "reason": "strength_conflict",
        "evidence": {
            "top_score": 0.95,
            "second_score": 0.60,
            "margin": 0.35,
            "strength_compatible": False,
            "strength_reason": "strength_conflict:500mg_vs_250mg",
            "external_hypothesis": False,
        },
    }

    step = build_resolution_evidence(resolution)

    assert step["status"] == "needs_review"
    assert step["strength_compatible"] is False
    assert "strength" in step["note"].lower()


def test_resolution_evidence_ambiguous_match():
    resolution = {
        "status": "needs_review",
        "reason": "ambiguous_match",
        "evidence": {
            "top_score": 0.82,
            "second_score": 0.76,
            "margin": 0.06,
            "strength_compatible": None,
            "strength_reason": "candidate_strength_unavailable",
            "external_hypothesis": False,
        },
    }

    step = build_resolution_evidence(resolution)

    assert step["status"] == "needs_review"
    assert step["margin"] == 0.06
    assert "ambiguous" in step["note"].lower() or "similar" in step["note"].lower()


def test_resolution_evidence_no_data():
    step = build_resolution_evidence(None)

    assert step["status"] == "unavailable"
    assert step["is_external_hypothesis"] is False


# =========================================================
# SAFETY EVIDENCE
# =========================================================


def test_safety_evidence_no_findings():
    step = build_safety_evidence([], "Paracetamol")

    assert step["step"] == "safety_evaluation"
    assert step["level"] == "clear"
    assert step["finding_count"] == 0


def test_safety_evidence_high_severity():
    flags = [
        {
            "type": "dose_limit_exceeded",
            "severity": "high",
            "medicine": "Paracetamol",
            "message": "Daily dose exceeds recommended maximum.",
        }
    ]

    step = build_safety_evidence(flags, "Paracetamol")

    assert step["level"] == "review_required"
    assert step["high_severity_count"] == 1
    assert "review" in step["note"].lower()


def test_safety_evidence_medium_severity():
    flags = [
        {
            "type": "drug_interaction",
            "severity": "medium",
            "medicine": "Warfarin",
            "message": "Potential interaction.",
        }
    ]

    step = build_safety_evidence(flags, "Warfarin")

    assert step["level"] == "caution"
    assert step["medium_severity_count"] == 1


def test_safety_evidence_prescription_level_finding():
    # Prescription-level findings (medicine=None) should be
    # included in the safety evidence for every medicine.
    flags = [
        {
            "type": "duplicate_medicine",
            "severity": "high",
            "medicine": None,
            "message": "Duplicate medicine detected.",
        }
    ]

    step = build_safety_evidence(flags, "Paracetamol")

    # medicine=None findings are prescription-level and included
    assert step["finding_count"] == 1


# =========================================================
# FULL EVIDENCE CHAIN
# =========================================================


def test_full_evidence_chain_has_four_steps():
    medicine = {
        "name": "Paracetamol",
        "generic_name": "Paracetamol",
        "raw_text": "Paracetmol 500 mg",
        "extraction_confidence": 0.90,
        "normalization_confidence": 1.00,
        "matched_term": "Paracetamol",
        "evidence": {"exact_match": True},
        "resolution": {
            "status": "accepted",
            "reason": "sufficient_evidence",
            "evidence": {
                "top_score": 0.92,
                "second_score": None,
                "margin": None,
                "strength_compatible": True,
                "strength_reason": "strength_match",
                "external_hypothesis": False,
            },
        },
    }

    ocr_quality = {"level": "good", "score": 85, "issues": []}
    safety_flags: list = []

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=ocr_quality,
        safety_flags=safety_flags,
    )

    assert len(chain["chain"]) == 4
    steps = [s["step"] for s in chain["chain"]]
    assert "ocr_extraction" in steps
    assert "normalization" in steps
    assert "resolution" in steps
    assert "safety_evaluation" in steps


def test_full_evidence_chain_summary_fields():
    medicine = {
        "name": "Amoxicillin",
        "extraction_confidence": 0.85,
        "normalization_confidence": 0.95,
        "resolution": {
            "status": "accepted",
            "reason": "sufficient_evidence",
            "evidence": {
                "external_hypothesis": False,
                "top_score": 0.95,
            },
        },
    }

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=None,
        safety_flags=[],
    )

    summary = chain["summary"]
    assert summary["ocr_confidence"] == 0.85
    assert summary["normalization_confidence"] == 0.95
    assert summary["resolution_status"] == "accepted"
    assert summary["is_external_hypothesis"] is False
    assert summary["safety_level"] == "clear"


def test_evidence_chain_external_hypothesis_in_summary():
    medicine = {
        "name": "Ibuprofen",
        "extraction_confidence": 0.80,
        "normalization_confidence": 0.70,
        "resolution": {
            "status": "needs_review",
            "reason": "external_hypothesis_requires_review",
            "evidence": {
                "external_hypothesis": True,
                "top_score": 0.99,
            },
        },
    }

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=None,
        safety_flags=[],
    )

    assert chain["summary"]["is_external_hypothesis"] is True
    assert chain["summary"]["resolution_status"] == "needs_review"


# =========================================================
# PIPELINE INTEGRATION
# =========================================================


def test_pipeline_returns_evidence_chains():
    raw_text = "Paracetamol 500mg tab 1x daily for 5 days"

    result = process_prescription(raw_text)

    assert "evidence_chains" in result


def test_pipeline_evidence_chains_aligned_with_medicines():
    raw_text = "Paracetamol 500mg tab 1x daily for 5 days"

    result = process_prescription(raw_text)

    medicines = result.get("medicines", [])
    chains = result.get("evidence_chains", [])

    assert len(chains) == len(medicines)


def test_pipeline_evidence_chains_empty_for_no_medicines():
    # An almost-empty text that will produce no medicines
    result = process_prescription("")

    chains = result.get("evidence_chains", [])
    assert chains == []


def test_pipeline_each_chain_has_four_steps():
    raw_text = "Amoxicillin 500mg 1 cap 3x daily 7 days"

    result = process_prescription(raw_text)

    for chain in result.get("evidence_chains", []):
        assert len(chain["chain"]) == 4
        steps = [s["step"] for s in chain["chain"]]
        assert "ocr_extraction" in steps
        assert "normalization" in steps
        assert "resolution" in steps
        assert "safety_evaluation" in steps


def test_pipeline_evidence_chain_does_not_expose_filesystem():
    raw_text = "Paracetamol 500mg tab 1x daily for 5 days"

    result = process_prescription(raw_text)

    # Flatten all string values in evidence_chains and check
    # no filesystem paths leak through.
    def _collect_strings(obj) -> list[str]:
        if isinstance(obj, str):
            return [obj]
        if isinstance(obj, dict):
            result = []
            for v in obj.values():
                result.extend(_collect_strings(v))
            return result
        if isinstance(obj, list):
            result = []
            for item in obj:
                result.extend(_collect_strings(item))
            return result
        return []

    all_strings = _collect_strings(result.get("evidence_chains", []))

    for s in all_strings:
        # No absolute Windows/Unix paths
        assert "\\" not in s or ":" not in s, (
            f"Possible filesystem path leaked: {s!r}"
        )
        assert not s.startswith("/uploads/"), (
            f"Upload path leaked: {s!r}"
        )


# =========================================================
# EC-1 REGRESSION: original_text must never be the resolved name
# =========================================================


def test_evidence_chain_original_text_not_resolved_name_when_raw_text_present():
    """
    When raw_text is present it must be used as original_text —
    not the resolved medicine name.
    """
    medicine = {
        "name": "Paracetamol",
        "raw_text": "Paracetmol",          # OCR typo — distinct from resolved name
        "extraction_confidence": 0.85,
        "normalization_confidence": 0.95,
        "matched_term": "Paracetamol",
        "evidence": {"exact_match": False, "ocr_corrected": True},
        "resolution": {
            "status": "accepted",
            "reason": "sufficient_evidence",
            "evidence": {
                "top_score": 0.95,
                "external_hypothesis": False,
                "strength_compatible": True,
                "strength_reason": "strength_match",
            },
        },
    }

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=None,
        safety_flags=[],
    )

    norm_step = next(s for s in chain["chain"] if s["step"] == "normalization")

    # original_text must be the OCR fragment, not the resolved name
    assert norm_step["original_text"] == "Paracetmol"
    # normalized_name is the resolved name
    assert norm_step["normalized_name"] == "Paracetamol"
    # They must be distinct — no self-match
    assert norm_step["original_text"] != norm_step["normalized_name"]


def test_evidence_chain_original_text_empty_when_no_raw_or_medicine_text():
    """
    EC-1: When both raw_text and medicine_text are absent,
    original_text must be '' — never the post-resolution medicine name.

    This prevents a misleading 'Paracetamol → Paracetamol' normalization note.
    """
    medicine = {
        "name": "Paracetamol",    # post-resolution resolved name only
        # raw_text and medicine_text deliberately absent
        "extraction_confidence": 0.80,
        "normalization_confidence": 0.90,
        "matched_term": "Paracetamol",
        "evidence": {"exact_match": True},
        "resolution": {
            "status": "accepted",
            "reason": "sufficient_evidence",
            "evidence": {
                "top_score": 0.90,
                "external_hypothesis": False,
                "strength_compatible": True,
                "strength_reason": "strength_match",
            },
        },
    }

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=None,
        safety_flags=[],
    )

    norm_step = next(s for s in chain["chain"] if s["step"] == "normalization")

    # original_text must NOT be the resolved name "Paracetamol"
    assert norm_step["original_text"] != "Paracetamol", (
        "EC-1: original_text must not fall back to the post-resolution name"
    )
    # It should be empty string (no OCR text available)
    assert norm_step["original_text"] == ""


def test_evidence_chain_original_text_uses_medicine_text_fallback():
    """
    When raw_text is absent but medicine_text is present,
    medicine_text must be used (not the resolved name).
    """
    medicine = {
        "name": "Ibuprofen",
        "medicine_text": "Ibuprophen",      # pre-resolution text, not the resolved name
        # raw_text deliberately absent
        "extraction_confidence": 0.75,
        "normalization_confidence": 0.88,
        "matched_term": "Ibuprofen",
        "evidence": {"ocr_corrected": True},
        "resolution": {
            "status": "accepted",
            "reason": "sufficient_evidence",
            "evidence": {
                "top_score": 0.88,
                "external_hypothesis": False,
                "strength_compatible": None,
                "strength_reason": "candidate_strength_unavailable",
            },
        },
    }

    chain = build_medicine_evidence_chain(
        medicine=medicine,
        ocr_quality=None,
        safety_flags=[],
    )

    norm_step = next(s for s in chain["chain"] if s["step"] == "normalization")

    # medicine_text (not the resolved name) should be original_text
    assert norm_step["original_text"] == "Ibuprophen"
    assert norm_step["original_text"] != norm_step["normalized_name"]
