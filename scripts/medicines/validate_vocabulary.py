#!/usr/bin/env python3
"""
scripts/medicines/validate_vocabulary.py
=========================================
Offline data-quality validator for data/medicines/medicine_knowledge.jsonl.

Detects:
  - malformed / non-JSON lines
  - missing generic_name
  - missing canonical_id or rxcui
  - duplicate canonical_ids mapping to different medicines
  - duplicate RxCUIs mapping to different generic names
  - duplicate generic names
  - duplicate aliases (same alias in two or more records)
  - alias mapped to multiple unrelated generic names
  - invalid / non-numeric strength values
  - invalid dosage forms (not in expected set)
  - brand name that is identical to generic name and looks like a brand
  - accidental placeholder canonical IDs
  - records whose generic_name is lower-case (violates display contract)
  - deterministic sort order violations

Usage
-----
    python scripts/medicines/validate_vocabulary.py [--path PATH] [--strict]

Exit codes
----------
    0  no errors detected
    1  at least one ERROR
    2  only WARNINGs (use --strict to treat warnings as errors)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "medicines"
    / "medicine_knowledge.jsonl"
)

# Placeholder IDs detected in the Sprint 1 audit.
# New records must not reuse these without a real concept match.
KNOWN_PLACEHOLDER_IDS: set[str] = {"41493"}

# Accepted dosage form values (lower-case for comparison).
EXPECTED_FORMS: set[str] = {
    "tablet", "capsule", "solution", "injection", "syrup", "suspension",
    "cream", "ointment", "patch", "suppository", "inhaler", "spray",
    "drops", "gel", "lotion", "powder", "film",
    "extended-release tablet", "granule", "lozenge",
}

_STRENGTH_NUM_RE = re.compile(r"^\d+(\.\d+)?$")


def _severity(is_error: bool) -> str:
    return "ERROR" if is_error else "WARN"


def validate(path: Path, strict: bool = False) -> tuple[list[str], list[str]]:
    """
    Validate a medicine_knowledge.jsonl file.

    Returns:
        (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    def err(msg: str) -> None:
        errors.append(msg)

    def warn(msg: str) -> None:
        warnings.append(msg)

    if not path.exists():
        err(f"File not found: {path}")
        return errors, warnings

    records: list[dict] = []

    # ------------------------------------------------------------------
    # Pass 1: parse lines
    # ------------------------------------------------------------------
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                err(f"Line {lineno}: malformed JSON — {exc}")
                continue
            if not isinstance(record, dict):
                err(f"Line {lineno}: expected JSON object, got {type(record).__name__}")
                continue
            records.append(record)

    if not records:
        err("File is empty or contains no valid records.")
        return errors, warnings

    # ------------------------------------------------------------------
    # Pass 2: per-record field checks
    # ------------------------------------------------------------------

    seen_generic: dict[str, int] = {}            # lower → first line index
    seen_rxcui: dict[str, list[str]] = {}        # rxcui → [generic_names]
    seen_canonical: dict[str, list[str]] = {}    # canonical_id → [generic_names]
    seen_aliases: dict[str, list[str]] = {}      # alias → [generic_names]
    last_rxcui: str | None = None                # for sort-order check

    for idx, record in enumerate(records, start=1):
        generic = str(record.get("generic_name") or "").strip()
        rxcui = str(record.get("rxcui") or "").strip()
        canonical_id = str(record.get("canonical_id") or "").strip()

        # Required fields
        if not generic:
            err(f"Record {idx}: missing generic_name")
            generic = f"<record_{idx}>"

        if not rxcui:
            err(f"Record {idx} ({generic}): missing rxcui")

        if not canonical_id:
            err(f"Record {idx} ({generic}): missing canonical_id")

        # Display contract: generic_name must be title-case (first char upper)
        if generic and generic[0].islower():
            warn(
                f"Record {idx} ({generic!r}): generic_name starts lower-case "
                "— expected title-case display form"
            )

        # Placeholder IDs
        if canonical_id in KNOWN_PLACEHOLDER_IDS:
            warn(
                f"Record {idx} ({generic}): canonical_id={canonical_id!r} is "
                "a known placeholder. Update to a real RxCUI."
            )
        if rxcui in KNOWN_PLACEHOLDER_IDS:
            warn(
                f"Record {idx} ({generic}): rxcui={rxcui!r} is a known "
                "placeholder. Update to a real RxCUI."
            )

        # Duplicate generic name
        gkey = generic.lower()
        if gkey in seen_generic:
            err(
                f"Record {idx}: duplicate generic_name {generic!r} "
                f"(first at record {seen_generic[gkey]})"
            )
        else:
            seen_generic[gkey] = idx

        # Duplicate / collision RxCUI
        if rxcui:
            seen_rxcui.setdefault(rxcui, []).append(generic)

        # Duplicate / collision canonical_id
        if canonical_id:
            seen_canonical.setdefault(canonical_id, []).append(generic)

        # Strength value
        sv = str(record.get("strength_value") or "").strip()
        if sv:
            # Allow values like "3 + 2" for combination drugs, but flag
            # clearly non-numeric single-ingredient strengths.
            if not _STRENGTH_NUM_RE.match(sv) and "+" not in sv:
                warn(
                    f"Record {idx} ({generic}): unusual strength_value={sv!r}"
                )

        # Dosage form
        df = str(record.get("dosage_form") or "").strip()
        if df and df.lower() not in EXPECTED_FORMS:
            warn(
                f"Record {idx} ({generic}): unexpected dosage_form={df!r}"
            )

        # Brand name replacing generic name
        brand = str(record.get("brand_name") or "").strip()
        if brand and brand.lower() == generic.lower():
            # Acceptable for combination drugs like "Sizodon Plus".
            # Flag as warning rather than error.
            warn(
                f"Record {idx} ({generic}): brand_name == generic_name — "
                "may be a combination drug or accidental copy-paste"
            )

        # Aliases
        aliases = record.get("aliases") or []
        if not isinstance(aliases, list):
            err(f"Record {idx} ({generic}): aliases must be a list")
        else:
            for alias in aliases:
                alias_str = str(alias).strip()
                if not alias_str:
                    continue
                if alias_str != alias_str.lower():
                    warn(
                        f"Record {idx} ({generic}): alias {alias_str!r} is not "
                        "lower-case — aliases should be lower-case"
                    )
                seen_aliases.setdefault(alias_str.lower(), []).append(generic)

    # ------------------------------------------------------------------
    # Pass 3: cross-record checks
    # ------------------------------------------------------------------

    # Duplicate RxCUIs across different generic names
    for rxcui, names in seen_rxcui.items():
        if len(names) > 1:
            unique = list(dict.fromkeys(names))
            if len(unique) > 1:
                err(
                    f"Duplicate rxcui={rxcui!r} used by multiple medicines: "
                    + ", ".join(unique)
                )
            # Same rxcui for same medicine is OK (shouldn't happen but benign).

    # Duplicate canonical_ids across different generic names
    for cid, names in seen_canonical.items():
        unique = list(dict.fromkeys(names))
        if len(unique) > 1:
            if cid in KNOWN_PLACEHOLDER_IDS:
                # Already warned per-record above.
                pass
            else:
                err(
                    f"Duplicate canonical_id={cid!r} used by multiple medicines: "
                    + ", ".join(unique)
                )

    # Aliases mapped to multiple different medicines
    for alias, names in seen_aliases.items():
        unique = list(dict.fromkeys(names))
        if len(unique) > 1:
            err(
                f"Alias {alias!r} mapped to multiple medicines: "
                + ", ".join(unique)
            )

    # Sort order: records must be sorted by rxcui for deterministic output
    rxcuis_in_order = [
        str(r.get("rxcui") or "") for r in records
    ]
    sorted_rxcuis = sorted(rxcuis_in_order)
    if rxcuis_in_order != sorted_rxcuis:
        warn("Records are not sorted by rxcui — run the importer to re-sort")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate medicine_knowledge.jsonl quality."
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_PATH),
        help="Path to medicine_knowledge.jsonl",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit code 1 on any finding)",
    )
    args = parser.parse_args(argv)

    errors, warnings = validate(Path(args.path), strict=args.strict)

    for w in warnings:
        print(f"WARN  {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)

    print(
        f"\nValidation complete: {len(errors)} error(s), "
        f"{len(warnings)} warning(s).",
        file=sys.stderr,
    )

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    if warnings and not errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
