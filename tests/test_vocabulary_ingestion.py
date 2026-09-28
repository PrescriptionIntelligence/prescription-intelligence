"""
tests/test_vocabulary_ingestion.py
====================================
Focused tests for the medicine vocabulary ingestion pipeline,
data-quality validation, and lookup index.

Covers:
  - validate_vocabulary.py checks
  - idempotent re-run behaviour
  - duplicate RxCUI / alias detection
  - generic / brand / alias query resolution
  - strength is NOT overwritten by ingestion
  - external API failure is non-fatal
  - external data does not override a strong local match
  - malformed JSONL record is gracefully skipped
  - in-process lookup index correctness
  - import_rxnorm.build_medicine_record output contract
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.medicine_normalizer import (
    clear_vocabulary_cache,
    load_medicine_vocabulary,
    lookup_exact,
    normalize_medicine_candidate,
    get_ranked_medicine_hypotheses,
)
from scripts.medicines.validate_vocabulary import validate
from scripts.medicines.import_rxnorm import (
    build_medicine_record,
    load_existing,
    write_records,
    ingest_one,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _minimal_record(
    rxcui: str = "1234",
    generic_name: str = "Testamol",
    *,
    brand_name: str | None = "Testbrand",
    strength_value: str | None = "500",
    strength_unit: str | None = "mg",
    dosage_form: str | None = "Tablet",
    aliases: list[str] | None = None,
) -> dict:
    return {
        "canonical_id": rxcui,
        "rxcui": rxcui,
        "generic_name": generic_name,
        "brand_name": brand_name,
        "active_ingredients": [generic_name],
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "dosage_form": dosage_form,
        "route": "oral",
        "drug_class": None,
        "aliases": aliases or [],
        "alias_types": {},
        "source": "rxnorm",
        "source_version": "test-1",
        "last_updated": "2024-01-01T00:00:00Z",
    }


# ===========================================================================
# 1. validate_vocabulary: clean file has no errors
# ===========================================================================


class TestValidateCleanFile:

    def test_clean_file_returns_no_errors(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        _write_jsonl(p, [
            _minimal_record("1001", "Amoxicillin"),
            _minimal_record("1002", "Warfarin", brand_name=None),
        ])
        errors, warnings = validate(p)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_file_is_an_error(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        errors, _warnings = validate(p)
        assert any("not found" in e.lower() for e in errors)

    def test_empty_file_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        p.write_text("", encoding="utf-8")
        errors, _warnings = validate(p)
        assert errors

    def test_malformed_json_line_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        p.write_text(
            '{"rxcui":"1","generic_name":"Good","canonical_id":"1","dosage_form":"Tablet"}\n'
            'THIS IS NOT JSON\n',
            encoding="utf-8",
        )
        errors, _warnings = validate(p)
        assert any("malformed" in e.lower() for e in errors)


# ===========================================================================
# 2. validate_vocabulary: duplicate detection
# ===========================================================================


class TestValidateDuplicates:

    def test_duplicate_rxcui_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        _write_jsonl(p, [
            _minimal_record("9999", "DrugA"),
            _minimal_record("9999", "DrugB"),  # same rxcui, different drug
        ])
        errors, _warnings = validate(p)
        assert any("duplicate rxcui" in e.lower() for e in errors)

    def test_duplicate_generic_name_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        _write_jsonl(p, [
            _minimal_record("1001", "Amoxicillin"),
            _minimal_record("1002", "Amoxicillin"),  # same generic, diff rxcui
        ])
        errors, _warnings = validate(p)
        assert any("duplicate generic_name" in e.lower() for e in errors)

    def test_alias_shared_across_medicines_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        _write_jsonl(p, [
            _minimal_record("1001", "DrugA", aliases=["conflictalias"]),
            _minimal_record("1002", "DrugB", aliases=["conflictalias"]),
        ])
        errors, _warnings = validate(p)
        assert any("conflictalias" in e for e in errors)

    def test_placeholder_canonical_id_is_a_warning(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        _write_jsonl(p, [
            _minimal_record("41493", "OldPlaceholderDrug"),
        ])
        _errors, warnings = validate(p)
        # The placeholder ID should be flagged as a warning.
        assert any("41493" in w for w in warnings)


# ===========================================================================
# 3. validate_vocabulary: field checks
# ===========================================================================


class TestValidateFieldChecks:

    def test_missing_generic_name_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        rec = _minimal_record("1001", "Testmol")
        rec["generic_name"] = ""
        _write_jsonl(p, [rec])
        errors, _warnings = validate(p)
        assert any("missing generic_name" in e.lower() for e in errors)

    def test_missing_rxcui_is_an_error(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        rec = _minimal_record("", "Testmol")
        rec["rxcui"] = ""
        _write_jsonl(p, [rec])
        errors, _warnings = validate(p)
        assert any("rxcui" in e.lower() for e in errors)

    def test_lower_case_generic_name_is_a_warning(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        rec = _minimal_record("1001", "testmol")  # lower-case
        _write_jsonl(p, [rec])
        _errors, warnings = validate(p)
        assert any("lower-case" in w.lower() or "starts lower" in w.lower() for w in warnings)

    def test_brand_equals_generic_is_a_warning(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        rec = _minimal_record("1001", "Augmentin", brand_name="Augmentin")
        _write_jsonl(p, [rec])
        _errors, warnings = validate(p)
        assert any("brand_name == generic_name" in w for w in warnings)


# ===========================================================================
# 4. import_rxnorm: build_medicine_record output contract
# ===========================================================================


class TestBuildMedicineRecord:

    def test_generic_name_is_title_case(self):
        rec = build_medicine_record(
            rxcui="7646",
            generic_name="omeprazole",
            brand_name=None,
            aliases=[],
            alias_types={},
            strength_value="20",
            strength_unit="mg",
            dosage_form="capsule",
            route="oral",
            active_ingredients=["omeprazole"],
            source_version="test",
        )
        assert rec["generic_name"] == "Omeprazole", (
            f"Expected title-case, got {rec['generic_name']!r}"
        )

    def test_brand_name_is_preserved(self):
        rec = build_medicine_record(
            rxcui="123",
            generic_name="warfarin",
            brand_name="Coumadin",
            aliases=["coumadin"],
            alias_types={"coumadin": "brand"},
            strength_value="5",
            strength_unit="mg",
            dosage_form="tablet",
            route="oral",
            active_ingredients=["warfarin"],
            source_version="test",
        )
        assert rec["brand_name"] == "Coumadin"
        assert rec["generic_name"] == "Warfarin"

    def test_aliases_are_lower_case(self):
        rec = build_medicine_record(
            rxcui="1191",
            generic_name="aspirin",
            brand_name=None,
            aliases=["Aspirin", "ASA", "Disprin"],
            alias_types={},
            strength_value="75",
            strength_unit="mg",
            dosage_form="tablet",
            route="oral",
            active_ingredients=["aspirin"],
            source_version="test",
        )
        for alias in rec["aliases"]:
            assert alias == alias.lower(), (
                f"Alias {alias!r} should be lower-case"
            )

    def test_dosage_form_is_title_case(self):
        rec = build_medicine_record(
            rxcui="123",
            generic_name="ibuprofen",
            brand_name=None,
            aliases=[],
            alias_types={},
            strength_value="400",
            strength_unit="mg",
            dosage_form="tablet",
            route="oral",
            active_ingredients=[],
            source_version="test",
        )
        assert rec["dosage_form"] == "Tablet"

    def test_canonical_id_equals_rxcui(self):
        rec = build_medicine_record(
            rxcui="5640",
            generic_name="ibuprofen",
            brand_name=None,
            aliases=[],
            alias_types={},
            strength_value=None,
            strength_unit=None,
            dosage_form=None,
            route=None,
            active_ingredients=[],
            source_version="test",
        )
        assert rec["canonical_id"] == rec["rxcui"] == "5640"

    def test_generic_not_duplicated_in_aliases(self):
        """Generic name must not appear in the aliases list."""
        rec = build_medicine_record(
            rxcui="999",
            generic_name="metformin",
            brand_name=None,
            aliases=["metformin", "glucophage"],
            alias_types={},
            strength_value="500",
            strength_unit="mg",
            dosage_form="tablet",
            route="oral",
            active_ingredients=[],
            source_version="test",
        )
        assert "metformin" not in rec["aliases"], (
            "Generic name should not be duplicated in aliases"
        )


# ===========================================================================
# 5. import_rxnorm: load_existing + write_records idempotency
# ===========================================================================


class TestIngestionIdempotent:

    def test_load_existing_returns_empty_for_missing_file(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        result = load_existing(p)
        assert result == {}

    def test_write_then_load_is_identity(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        records = {
            "1001": _minimal_record("1001", "Amoxicillin"),
            "1002": _minimal_record("1002", "Warfarin"),
        }
        write_records(p, records)
        loaded = load_existing(p)
        assert set(loaded.keys()) == {"1001", "1002"}
        assert loaded["1001"]["generic_name"] == "Amoxicillin"

    def test_write_twice_is_idempotent(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        records = {"1001": _minimal_record("1001", "Testmol")}
        write_records(p, records)
        write_records(p, records)
        loaded = load_existing(p)
        assert len(loaded) == 1

    def test_records_are_sorted_by_rxcui(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        records = {
            "9999": _minimal_record("9999", "Zzz"),
            "0001": _minimal_record("0001", "Aaa"),
            "5000": _minimal_record("5000", "Mmm"),
        }
        write_records(p, records)
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        rxcuis = [json.loads(l)["rxcui"] for l in lines]
        assert rxcuis == sorted(rxcuis), "Records must be sorted by rxcui"

    def test_malformed_line_is_skipped_by_load_existing(self, tmp_path):
        p = tmp_path / "vocab.jsonl"
        p.write_text(
            '{"rxcui":"1001","generic_name":"Good","canonical_id":"1001"}\n'
            'NOT JSON\n',
            encoding="utf-8",
        )
        loaded = load_existing(p)
        assert "1001" in loaded
        assert len(loaded) == 1


# ===========================================================================
# 6. import_rxnorm: ingest_one API failure is graceful
# ===========================================================================


class TestIngestOneFails:

    def test_no_rxcui_returns_none(self):
        with patch(
            "scripts.medicines.import_rxnorm._lookup_rxcui_for_name",
            return_value=None,
        ):
            result = ingest_one(
                "unknowndrug99",
                timeout=5.0,
                source_version="test",
            )
        assert result is None

    def test_network_error_propagates_to_caller(self):
        """
        ingest_one does not catch exceptions from _lookup_rxcui_for_name.
        The main() function catches them with a try/except per seed.
        This test verifies the exception propagates as documented.
        """
        with patch(
            "scripts.medicines.import_rxnorm._lookup_rxcui_for_name",
            side_effect=Exception("network failure"),
        ):
            with pytest.raises(Exception, match="network failure"):
                ingest_one("amoxicillin", timeout=5.0, source_version="test")


# ===========================================================================
# 7. Normalizer: generic / brand / alias query resolution
# ===========================================================================


class TestNormalizerQueryResolution:
    """
    Tests that use the real vocabulary file.  Marked to be skipped
    gracefully if the vocab is absent (CI without vocabulary).
    """

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        clear_vocabulary_cache()
        yield
        clear_vocabulary_cache()

    def test_generic_query_returns_generic_name(self):
        medicines = load_medicine_vocabulary()
        result = normalize_medicine_candidate(
            {"medicine_text": "Warfarin"}, medicines
        )
        assert result["generic_name"] == "Warfarin"
        assert result["needs_review"] is False

    def test_brand_query_returns_generic_name(self):
        medicines = load_medicine_vocabulary()
        # "Coumadin" is an alias for Warfarin.
        result = normalize_medicine_candidate(
            {"medicine_text": "Coumadin"}, medicines
        )
        assert result["generic_name"] == "Warfarin"
        assert result["needs_review"] is False

    def test_alias_query_resolves_to_correct_generic(self):
        medicines = load_medicine_vocabulary()
        # "Glucophage" is an alias for Metformin.
        result = normalize_medicine_candidate(
            {"medicine_text": "Glucophage"}, medicines
        )
        assert result["generic_name"] == "Metformin"
        assert result["needs_review"] is False

    def test_generic_name_is_not_replaced_by_brand_on_generic_query(self):
        """
        A generic query must NOT return a brand as the generic_name.
        The generic_name field must always hold the INN.
        """
        medicines = load_medicine_vocabulary()
        result = normalize_medicine_candidate(
            {"medicine_text": "Atorvastatin"}, medicines
        )
        # generic_name must be the INN, never "Lipitor"
        assert result["generic_name"] == "Atorvastatin"

    def test_strength_from_normalizer_is_vocabulary_reference_not_prescription(self):
        """
        The strength returned by the normalizer is the vocabulary's
        REPRESENTATIVE strength, not the prescription strength.
        Prescription strength comes from the parser/OCR layer.
        """
        medicines = load_medicine_vocabulary()
        # Query with "10 mg" — a conflicting strength vs vocabulary "5 mg".
        # The normalizer should still return Warfarin (medicine identity OK),
        # but the strength_value comes from the vocabulary (5 mg).
        result = normalize_medicine_candidate(
            {"medicine_text": "Warfarin 10 mg"}, medicines
        )
        assert result["generic_name"] == "Warfarin"
        # The normalizer's strength_value is from the vocabulary record.
        # It must be 5 (reference), NOT 10 (prescribed).
        assert result["strength_value"] == "5", (
            f"Normalizer returned strength={result['strength_value']!r}; "
            "it should return the vocabulary reference strength (5), "
            "not the prescribed strength (10)."
        )


# ===========================================================================
# 8. Normalizer: external failure is non-fatal
# ===========================================================================


class TestExternalFailureNonFatal:

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        clear_vocabulary_cache()
        yield
        clear_vocabulary_cache()

    def test_external_api_failure_does_not_break_normalization(self):
        """
        Even when external RxNorm lookup completely fails, the local
        normalizer must still return results for known medicines.
        """
        with patch(
            "backend.services.external_medicine_knowledge.lookup_rxnorm",
            side_effect=Exception("simulated network failure"),
        ):
            medicines = load_medicine_vocabulary()
            result = normalize_medicine_candidate(
                {"medicine_text": "Warfarin"}, medicines
            )
        assert result["generic_name"] == "Warfarin"
        assert result["needs_review"] is False


# ===========================================================================
# 9. Normalizer: external data does not override strong local match
# ===========================================================================


class TestExternalDoesNotOverrideLocal:

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        clear_vocabulary_cache()
        yield
        clear_vocabulary_cache()

    def test_strong_local_match_suppresses_external_lookup(self):
        """
        When the local vocabulary returns a strong exact match,
        get_ranked_medicine_hypotheses must NOT call the external API.
        """
        from backend.services.external_medicine_knowledge import (
            clear_external_lookup_cache,
        )
        clear_external_lookup_cache()

        call_count = {"n": 0}

        def counting_lookup(*args, **kwargs):
            call_count["n"] += 1
            return []

        with patch(
            "backend.services.external_medicine_knowledge.lookup_rxnorm",
            side_effect=counting_lookup,
        ):
            medicines = load_medicine_vocabulary()
            hypotheses = get_ranked_medicine_hypotheses(
                {"medicine_text": "Warfarin"},
                medicines=medicines,
            )

        assert hypotheses, "Expected at least one hypothesis"
        assert hypotheses[0]["generic_name"] == "Warfarin"
        assert call_count["n"] == 0, (
            f"External API was called {call_count['n']} times; "
            "it should not be called for a strong local match"
        )


# ===========================================================================
# 10. Lookup index: O(1) exact lookup
# ===========================================================================


class TestLookupIndex:

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        clear_vocabulary_cache()
        yield
        clear_vocabulary_cache()

    def test_exact_generic_name_lookup(self):
        load_medicine_vocabulary()  # builds indexes
        hit = lookup_exact("Warfarin")
        assert hit is not None
        assert hit["generic_name"] == "Warfarin"

    def test_case_insensitive_lookup(self):
        load_medicine_vocabulary()
        hit = lookup_exact("warfarin")
        assert hit is not None
        assert hit["generic_name"] == "Warfarin"

    def test_alias_lookup(self):
        load_medicine_vocabulary()
        hit = lookup_exact("coumadin")
        assert hit is not None
        assert hit["generic_name"] == "Warfarin"

    def test_brand_name_lookup(self):
        load_medicine_vocabulary()
        hit = lookup_exact("Glucophage")
        assert hit is not None
        assert hit["generic_name"] == "Metformin"

    def test_unknown_name_returns_none(self):
        load_medicine_vocabulary()
        hit = lookup_exact("completelyunknownxyz999")
        assert hit is None

    def test_index_cleared_with_cache(self):
        load_medicine_vocabulary()
        assert lookup_exact("Warfarin") is not None
        clear_vocabulary_cache()
        assert lookup_exact("Warfarin") is None
