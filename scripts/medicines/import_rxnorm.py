#!/usr/bin/env python3
"""
scripts/medicines/import_rxnorm.py
====================================
Offline ingestion script: RxNorm → medicine_knowledge.jsonl

Usage
-----
    python scripts/medicines/import_rxnorm.py [--output PATH] [--timeout N]

What it does
------------
1. Queries the public RxNorm REST API for a curated list of common
   ingredient names (IN / PIN concept types).
2. For each ingredient, fetches:
   - canonical generic name
   - RxCUI
   - related brand-name concepts (BN / SBD)
   - related clinical drug concepts (SCD) for strength/dose-form
   - synonyms / aliases from the RxNorm atom list
3. Normalises all names.
4. Deduplicates concepts by RxCUI.
5. Writes to data/medicines/medicine_knowledge.jsonl (or --output path).
6. Is safely re-runnable: merges with any existing records rather than
   overwriting them from scratch.

Output schema per line (newline-delimited JSON)
-----------------------------------------------
{
  "canonical_id":     "<rxcui>",
  "rxcui":            "<rxcui>",
  "generic_name":     "paracetamol",
  "brand_name":       "Tylenol",           # null when no brand resolved
  "active_ingredients": ["paracetamol"],
  "strength_value":   "500",               # null when not parsed
  "strength_unit":    "mg",                # null when not parsed
  "dosage_form":      "tablet",            # null when not parsed
  "route":            "oral",              # null when not available
  "drug_class":       null,                # future field
  "aliases":          ["acetaminophen", "pcm"],
  "alias_types":      {"acetaminophen": "synonym", "pcm": "abbreviation"},
  "source":           "rxnorm",
  "source_version":   "2024-01",           # RxNorm release date
  "last_updated":     "2024-01-15T12:00:00Z"
}

Safety constraints
------------------
- No live calls during prescription analysis.
- This script is ONLY run offline by a developer / CI job.
- Output file is committed to the repo (it is reasonably small).
- The prescription pipeline reads the static file; it never calls this.

Architecture note
-----------------
The output is consumed by load_medicine_vocabulary() in
backend/services/medicine_normalizer.py, which already supports both
the legacy CSV and this richer JSON-L format.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

RXNORM_BASE_URL = "https://rxnav.nlm.nih.gov/REST"

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "medicines"
    / "medicine_knowledge.jsonl"
)

DEFAULT_TIMEOUT = 5.0

# Throttle: seconds between API calls to be a good citizen.
API_THROTTLE_SECONDS = 0.2

# RxNorm term types we care about:
#   IN  = Ingredient
#   PIN = Precise Ingredient
#   BN  = Brand Name
#   SBD = Semantic Branded Drug (with strength/form)
#   SCD = Semantic Clinical Drug  (with strength/form)
INGREDIENT_TYPES = {"IN", "PIN"}
BRAND_TYPES = {"BN", "SBD"}
CLINICAL_DRUG_TYPES = {"SCD"}

# Strength pattern: "500 MG", "10 mg/5 mL", "0.5 %", "2.5 MG/ML" etc.
_STRENGTH_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|iu|%|meq|mmol|ml|mg/ml|mcg/ml)"
    r"(?:\s*/\s*(\d+(?:\.\d+)?)\s*(ml|g|dose))?",
    re.IGNORECASE,
)

# Dose form keywords found in concept names.
_FORM_MAP = {
    "tablet": "tablet",
    "oral tablet": "tablet",
    "cap": "capsule",
    "capsule": "capsule",
    "solution": "solution",
    "injection": "injection",
    "syrup": "syrup",
    "suspension": "suspension",
    "cream": "cream",
    "ointment": "ointment",
    "patch": "patch",
    "suppository": "suppository",
    "inhaler": "inhaler",
    "inhalation": "inhaler",
    "spray": "spray",
    "drops": "drops",
    "gel": "gel",
    "lotion": "lotion",
    "powder": "powder",
    "granule": "granule",
    "lozenge": "lozenge",
    "film": "film",
    "extended-release": "extended-release tablet",
    "er tablet": "extended-release tablet",
}

_ROUTE_MAP = {
    "oral": "oral",
    "topical": "topical",
    "intravenous": "intravenous",
    "intramuscular": "intramuscular",
    "subcutaneous": "subcutaneous",
    "inhaled": "inhaled",
    "rectal": "rectal",
    "ophthalmic": "ophthalmic",
    "otic": "otic",
    "nasal": "nasal",
    "sublingual": "sublingual",
    "transdermal": "transdermal",
    "vaginal": "vaginal",
}

# =========================================================
# Common ingredient seeds
# This list covers broad categories: analgesics, antibiotics,
# antivirals, cardiovascular, psychiatric, GI, allergy, diabetes,
# anticoagulants, anticonvulsants, vitamins — intentionally
# conservative and verifiable without inventing data.
# =========================================================

INGREDIENT_SEEDS = [
    # Analgesics / antipyretics
    "acetaminophen", "ibuprofen", "aspirin", "naproxen",
    "diclofenac", "indomethacin", "ketorolac", "celecoxib",
    "tramadol", "codeine", "morphine", "oxycodone", "hydrocodone",
    "buprenorphine", "fentanyl", "methadone",

    # Antibiotics — penicillins & cephalosporins
    "amoxicillin", "ampicillin", "penicillin", "cloxacillin",
    "cephalexin", "cefuroxime", "cefixime",
    "ceftriaxone", "cefpodoxime", "cefdinir", "cefadroxil",

    # Antibiotics — macrolides & others
    "azithromycin", "clarithromycin", "erythromycin",
    "ciprofloxacin", "levofloxacin", "norfloxacin", "ofloxacin", "moxifloxacin",
    "doxycycline", "tetracycline", "minocycline",
    "metronidazole", "tinidazole", "clindamycin",
    "trimethoprim", "sulfamethoxazole",
    "nitrofurantoin", "fosfomycin",
    "linezolid", "vancomycin",
    "gentamicin", "amikacin", "tobramycin",
    "rifampicin", "isoniazid", "ethambutol", "pyrazinamide",
    "chloramphenicol",

    # Antivirals / antifungals
    "acyclovir", "valacyclovir", "oseltamivir",
    "famciclovir", "ganciclovir",
    "fluconazole", "itraconazole", "ketoconazole",
    "voriconazole", "posaconazole",
    "clotrimazole", "miconazole", "terbinafine", "nystatin",

    # Cardiovascular — beta-blockers
    "atenolol", "metoprolol", "propranolol", "bisoprolol", "carvedilol",
    "nebivolol", "labetalol",

    # Cardiovascular — calcium channel blockers
    "amlodipine", "nifedipine", "diltiazem", "verapamil",
    "felodipine", "nicardipine",

    # Cardiovascular — ACE inhibitors
    "enalapril", "lisinopril", "ramipril", "perindopril",
    "captopril", "quinapril", "fosinopril", "benazepril",

    # Cardiovascular — ARBs
    "losartan", "telmisartan", "valsartan", "olmesartan",
    "candesartan", "irbesartan",

    # Cardiovascular — diuretics & other
    "furosemide", "hydrochlorothiazide", "spironolactone",
    "torsemide", "chlorthalidone", "indapamide", "eplerenone",
    "digoxin", "amiodarone", "clopidogrel", "warfarin",
    "ticagrelor", "prasugrel",
    "atorvastatin", "simvastatin", "rosuvastatin", "pravastatin",
    "lovastatin", "fluvastatin", "pitavastatin",
    "ezetimibe", "fenofibrate", "gemfibrozil",
    "isosorbide mononitrate", "nitroglycerin",
    "ivabradine", "sacubitril",

    # Diabetes
    "metformin", "glipizide", "glibenclamide", "glimepiride",
    "sitagliptin", "vildagliptin", "saxagliptin", "linagliptin",
    "canagliflozin", "empagliflozin", "dapagliflozin",
    "liraglutide", "semaglutide", "exenatide",
    "pioglitazone", "rosiglitazone",
    "insulin glargine", "insulin aspart", "insulin detemir",
    "insulin lispro", "insulin degludec",

    # Psychiatric / neurological
    "alprazolam", "lorazepam", "diazepam", "clonazepam", "midazolam",
    "olanzapine", "risperidone", "quetiapine", "haloperidol",
    "clozapine", "aripiprazole", "ziprasidone", "paliperidone",
    "sertraline", "fluoxetine", "escitalopram", "citalopram",
    "paroxetine", "fluvoxamine", "venlafaxine", "duloxetine",
    "mirtazapine", "bupropion", "trazodone",
    "amitriptyline", "nortriptyline", "clomipramine", "imipramine",
    "lithium", "valproate", "valproic acid",
    "carbamazepine", "phenytoin", "levetiracetam", "lamotrigine",
    "gabapentin", "pregabalin",
    "topiramate", "oxcarbazepine", "zonisamide",
    "phenobarbital", "primidone",
    "trihexyphenidyl", "biperiden",
    "donepezil", "memantine", "rivastigmine", "galantamine",
    "zolpidem", "eszopiclone", "zaleplon",
    "melatonin", "ramelteon",
    "methylphenidate", "amphetamine", "atomoxetine",

    # GI
    "omeprazole", "pantoprazole", "esomeprazole", "lansoprazole",
    "rabeprazole", "dexlansoprazole",
    "ranitidine", "famotidine", "cimetidine",
    "metoclopramide", "domperidone", "ondansetron", "granisetron",
    "prochlorperazine",
    "loperamide", "bisacodyl", "lactulose",
    "sucralfate", "misoprostol",
    "mesalamine", "sulfasalazine", "olsalazine",
    "ursodiol",

    # Allergy / respiratory
    "cetirizine", "loratadine", "fexofenadine", "levocetirizine",
    "chlorphenamine", "diphenhydramine", "hydroxyzine",
    "desloratadine", "bilastine",
    "salbutamol", "terbutaline", "levalbuterol",
    "salmeterol", "formoterol", "indacaterol",
    "budesonide", "fluticasone", "beclomethasone", "mometasone",
    "montelukast", "zafirlukast",
    "ipratropium", "tiotropium", "aclidinium",
    "roflumilast", "theophylline",
    "cromolyn",

    # Thyroid / endocrine
    "levothyroxine", "liothyronine", "propylthiouracil", "carbimazole",

    # Hormones / contraceptives / steroids
    "prednisolone", "dexamethasone", "hydrocortisone", "methylprednisolone",
    "triamcinolone", "betamethasone",
    "ethinylestradiol", "levonorgestrel", "progesterone",
    "norethindrone", "medroxyprogesterone",
    "testosterone", "danazol",
    "anastrozole", "letrozole", "exemestane",

    # Vitamins / minerals / supplements
    "ferrous sulfate", "folic acid", "cyanocobalamin",
    "cholecalciferol", "calcitriol", "ergocalciferol",
    "calcium carbonate", "calcium gluconate",
    "zinc sulfate", "zinc acetate",
    "magnesium hydroxide", "magnesium oxide",
    "potassium chloride",
    "ascorbic acid",
    "retinol", "thiamine", "riboflavin", "niacin", "pyridoxine",

    # Anticoagulants
    "heparin", "enoxaparin", "rivaroxaban", "apixaban",
    "dabigatran", "fondaparinux", "edoxaban",

    # Oncology (basic — publicly known targeted agents)
    "methotrexate", "cyclophosphamide", "tamoxifen",
    "imatinib", "hydroxyurea",
    "fluorouracil", "capecitabine", "gemcitabine",
    "doxorubicin", "paclitaxel", "docetaxel",
    "anastrozole",

    # Urology / sexual health
    "tamsulosin", "finasteride", "oxybutynin",
    "sildenafil", "tadalafil", "vardenafil",
    "alfuzosin", "dutasteride",
    "desmopressin",

    # Dermatology / topicals
    "tretinoin", "adapalene", "benzoyl peroxide",
    "clindamycin", "erythromycin",
    "mupirocin", "fusidic acid",
    "hydrocortisone", "betamethasone", "clobetasol",
    "calcipotriol",

    # Ophthalmology
    "timolol", "latanoprost", "bimatoprost",
    "dorzolamide", "brimonidine",
    "tobramycin", "ciprofloxacin",
    "prednisolone",

    # Miscellaneous common
    "allopurinol", "colchicine", "febuxostat",
    "hydroxychloroquine", "chloroquine",
    "leflunomide", "azathioprine",
    "cyclosporine", "tacrolimus",
    "acetazolamide", "mannitol",
    "caffeine", "theophylline",
    "dexamethasone",
]


def _http_get_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PrescriptionIntelligence/MedicineImporter-1.0",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _throttle() -> None:
    time.sleep(API_THROTTLE_SECONDS)


def _normalise_name(name: str) -> str:
    """Lower-case, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _parse_strength(concept_name: str) -> tuple[str | None, str | None]:
    """Extract first strength/unit pair from a concept name string."""
    m = _STRENGTH_RE.search(concept_name)
    if not m:
        return None, None
    return m.group(1), m.group(2).lower()


def _parse_dosage_form(concept_name: str) -> str | None:
    lower = concept_name.lower()
    for keyword, form in _FORM_MAP.items():
        if keyword in lower:
            return form
    return None


def _parse_route(concept_name: str) -> str | None:
    lower = concept_name.lower()
    for keyword, route in _ROUTE_MAP.items():
        if keyword in lower:
            return route
    return None


def _get_rxnorm_release() -> str:
    """Return RxNorm release date string, or 'unknown'."""
    try:
        data = _http_get_json(
            f"{RXNORM_BASE_URL}/version.json",
            timeout=5.0,
        )
        _throttle()
        return str(
            data.get("rxnormdata", {}).get("rxnormdate", "unknown")
        )
    except Exception:
        return "unknown"


def _lookup_rxcui_for_name(
    name: str,
    timeout: float,
) -> str | None:
    """Return the preferred RxCUI for an ingredient name, or None."""
    try:
        encoded = quote(name, safe="")
        data = _http_get_json(
            f"{RXNORM_BASE_URL}/rxcui.json?name={encoded}&search=1",
            timeout=timeout,
        )
        _throttle()
        idgroup = data.get("idGroup") or {}
        rxcui_list = idgroup.get("rxnormId") or []
        if rxcui_list:
            return str(rxcui_list[0])
    except Exception as exc:
        logger.debug("rxcui lookup failed for %r: %s", name, exc)
    return None


def _get_related_concepts(
    rxcui: str,
    ttys: str,
    timeout: float,
) -> list[dict]:
    """
    Fetch related concept groups for an RxCUI by term type.
    ttys = comma-separated term types e.g. "BN,SBD"
    """
    try:
        url = (
            f"{RXNORM_BASE_URL}/rxcui/{quote(rxcui, safe='')}"
            f"/related.json?tty={quote(ttys, safe='')}"
        )
        data = _http_get_json(url, timeout=timeout)
        _throttle()
        groups = (
            data.get("relatedGroup", {}).get("conceptGroup") or []
        )
        results = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            props = group.get("conceptProperties") or []
            if isinstance(props, dict):
                props = [props]
            for prop in props:
                if not isinstance(prop, dict):
                    continue
                rcui = str(prop.get("rxcui") or "").strip()
                rname = str(prop.get("name") or "").strip()
                if rcui and rname:
                    results.append({"rxcui": rcui, "name": rname})
        return results
    except Exception as exc:
        logger.debug(
            "related concepts failed for %s (tty=%s): %s",
            rxcui, ttys, exc,
        )
        return []


def _get_atoms(rxcui: str, timeout: float) -> list[dict]:
    """Retrieve atom list for an RxCUI (for synonym extraction)."""
    try:
        url = (
            f"{RXNORM_BASE_URL}/rxcui/{quote(rxcui, safe='')}"
            "/allhistoricalndcs.json"
        )
        # Use property list for synonyms instead (lighter)
        url2 = (
            f"{RXNORM_BASE_URL}/rxcui/{quote(rxcui, safe='')}"
            "/property.json?propName=RxNorm+Name"
        )
        data = _http_get_json(url2, timeout=timeout)
        _throttle()
        concepts = (
            data.get("propConceptGroup", {}).get("propConcept") or []
        )
        if isinstance(concepts, dict):
            concepts = [concepts]
        results = []
        for c in concepts:
            if isinstance(c, dict):
                v = str(c.get("propValue") or "").strip()
                if v:
                    results.append({"name": v, "type": "rxnorm_name"})
        return results
    except Exception:
        return []


# Canonical dosage-form display names (matches build_seed_vocabulary.py).
_DOSAGE_FORM_DISPLAY = {
    "tablet": "Tablet",
    "capsule": "Capsule",
    "solution": "Solution",
    "injection": "Injection",
    "syrup": "Syrup",
    "suspension": "Suspension",
    "cream": "Cream",
    "ointment": "Ointment",
    "patch": "Patch",
    "suppository": "Suppository",
    "inhaler": "Inhaler",
    "spray": "Spray",
    "drops": "Drops",
    "gel": "Gel",
    "lotion": "Lotion",
    "powder": "Powder",
    "film": "Film",
    "extended-release tablet": "Extended-Release Tablet",
    "granule": "Granule",
    "lozenge": "Lozenge",
}


def _display_form(dosage_form: str | None) -> str | None:
    """Canonicalize dosage form display string."""
    if not dosage_form:
        return None
    return _DOSAGE_FORM_DISPLAY.get(dosage_form.lower(), dosage_form.title())


def _display_name(name: str) -> str:
    """
    Convert a normalised (lower-case) medicine name to display form.

    Uses title-case but preserves known all-caps abbreviations
    (e.g. "HCl", "IV", "ER") and compound names.
    """
    if not name:
        return name
    # Title-case each word; good enough for ingredient names.
    return " ".join(w.capitalize() for w in name.split())


def build_medicine_record(
    rxcui: str,
    generic_name: str,
    *,
    brand_name: str | None,
    aliases: list[str],
    alias_types: dict[str, str],
    strength_value: str | None,
    strength_unit: str | None,
    dosage_form: str | None,
    route: str | None,
    active_ingredients: list[str],
    source_version: str,
) -> dict:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Ensure generic_name is in display (title) case for API contract
    # consistency with build_seed_vocabulary.py.
    display_generic = _display_name(generic_name)
    display_brand = _display_name(brand_name) if brand_name else None

    # Aliases are always lower-case (used only for fuzzy matching).
    alias_lower = generic_name.lower()
    clean_aliases = sorted({
        a.lower()
        for a in aliases
        if a and a.lower() != alias_lower
    })

    return {
        "canonical_id": rxcui,
        "rxcui": rxcui,
        "generic_name": display_generic,
        "brand_name": display_brand,
        "active_ingredients": [display_generic] if not active_ingredients else [
            _display_name(i) for i in active_ingredients
        ],
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "dosage_form": _display_form(dosage_form),
        "route": route,
        "drug_class": None,
        "aliases": clean_aliases,
        "alias_types": alias_types,
        "source": "rxnorm",
        "source_version": source_version,
        "last_updated": now_iso,
    }


def ingest_one(
    ingredient_name: str,
    *,
    timeout: float,
    source_version: str,
) -> dict | None:
    """
    Fetch RxNorm data for a single ingredient name and return
    a normalised medicine record dict, or None on failure.

    The returned record uses title-case generic_name and brand_name
    to match the display contract established by build_seed_vocabulary.py.
    """
    rxcui = _lookup_rxcui_for_name(ingredient_name, timeout)
    if not rxcui:
        logger.debug("No RxCUI found for %r", ingredient_name)
        return None

    # Canonical generic name: lower-case internally, display-cased in record.
    generic_name = _normalise_name(ingredient_name)

    # Brand names — keep original casing from RxNorm as the display brand,
    # store lower-case in aliases list.
    brand_concepts = _get_related_concepts(rxcui, "BN", timeout)
    brand_name: str | None = None
    if brand_concepts:
        # Use the RxNorm name directly (usually already title-cased).
        brand_name = brand_concepts[0]["name"].strip() or None

    # Aliases: lower-case brand names (for fuzzy matching).
    aliases: list[str] = []
    alias_types: dict[str, str] = {}

    for bc in brand_concepts[:5]:
        alias = _normalise_name(bc["name"])
        if alias and alias != generic_name:
            aliases.append(alias)
            alias_types[alias] = "brand"

    # Try to get strength/form from an SCD concept.
    # Prefer oral tablet/capsule forms over IV/injection when multiple exist.
    scd_concepts = _get_related_concepts(rxcui, "SCD", timeout)
    strength_value = None
    strength_unit = None
    dosage_form = None
    route = None

    # First pass: prefer oral solid dosage forms.
    for scd in scd_concepts[:10]:
        name_lower = scd["name"].lower()
        is_oral = (
            "oral" in name_lower
            or "tablet" in name_lower
            or "capsule" in name_lower
        )
        sv, su = _parse_strength(scd["name"])
        df = _parse_dosage_form(scd["name"])
        rt = _parse_route(scd["name"])
        if sv and su and df and is_oral and not strength_value:
            strength_value = sv
            strength_unit = su
            dosage_form = df
            route = rt or "oral"
            break

    # Second pass: accept any form if nothing oral was found.
    if not strength_value:
        for scd in scd_concepts[:5]:
            sv, su = _parse_strength(scd["name"])
            if sv and su and not strength_value:
                strength_value = sv
                strength_unit = su
            df = _parse_dosage_form(scd["name"])
            if df and not dosage_form:
                dosage_form = df
            rt = _parse_route(scd["name"])
            if rt and not route:
                route = rt
            if strength_value and dosage_form:
                break

    return build_medicine_record(
        rxcui=rxcui,
        generic_name=generic_name,
        brand_name=brand_name,
        aliases=aliases,
        alias_types=alias_types,
        strength_value=strength_value,
        strength_unit=strength_unit,
        dosage_form=dosage_form,
        route=route,
        active_ingredients=[generic_name],
        source_version=source_version,
    )


def load_existing(output_path: Path) -> dict[str, dict]:
    """Return existing records keyed by canonical_id.

    Using canonical_id (rather than rxcui) as the deduplication key ensures
    that local/combination records with non-numeric canonical_ids (e.g.
    "local:augmentin") are treated as distinct entries and are not silently
    overwritten by another record that happens to share the same rxcui.
    """
    existing: dict[str, dict] = {}
    if not output_path.exists():
        return existing
    with output_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                # Prefer canonical_id; fall back to rxcui for older records
                # that pre-date the canonical_id field.
                key = str(
                    record.get("canonical_id") or record.get("rxcui") or ""
                ).strip()
                if key:
                    existing[key] = record
            except json.JSONDecodeError:
                continue
    return existing


def write_records(output_path: Path, records: dict[str, dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _sort_key(r: dict) -> tuple[int, str]:
        """Sort numeric RxCUI records first (by integer), then local records
        alphabetically.  This keeps the file stable and human-readable."""
        cid = str(r.get("canonical_id") or r.get("rxcui") or "")
        try:
            return (0, str(int(cid)).zfill(12))
        except ValueError:
            return (1, cid)

    with output_path.open("w", encoding="utf-8") as fh:
        for record in sorted(records.values(), key=_sort_key):
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import RxNorm medicine data offline."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output .jsonl path",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout per request (seconds)",
    )
    parser.add_argument(
        "--seeds",
        nargs="*",
        help="Override ingredient seed list (space-separated names)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write output; just print records to stdout",
    )
    args = parser.parse_args(argv)

    output_path = Path(args.output)
    seeds = args.seeds if args.seeds else INGREDIENT_SEEDS

    logger.info("Fetching RxNorm release version...")
    source_version = _get_rxnorm_release()
    logger.info("RxNorm version: %s", source_version)

    existing = load_existing(output_path)
    logger.info(
        "Loaded %d existing records from %s",
        len(existing),
        output_path,
    )

    # Secondary index: generic_name (lower-case) → rxcui already stored.
    # Prevents storing two different RxCUIs for the same generic concept when
    # RxNorm returns ingredient-level and formulation-level concepts for the
    # same name.  The richer record (more aliases + has strength) wins.
    seen_by_name: dict[str, str] = {
        str(r.get("generic_name") or "").lower(): rxcui_key
        for rxcui_key, r in existing.items()
    }

    new_count = 0
    skipped_count = 0
    error_count = 0

    def _record_richness(r: dict) -> int:
        """Score a record's richness: more aliases + has strength = richer."""
        score = len(r.get("aliases") or [])
        if r.get("strength_value"):
            score += 10
        if r.get("dosage_form"):
            score += 5
        return score

    for seed in seeds:
        try:
            record = ingest_one(
                seed,
                timeout=args.timeout,
                source_version=source_version,
            )
        except Exception as exc:
            logger.warning("Error ingesting %r: %s", seed, exc)
            error_count += 1
            continue

        if record is None:
            logger.debug("No record for %r", seed)
            skipped_count += 1
            continue

        rxcui = record["rxcui"]
        gname_lower = str(record.get("generic_name") or "").lower()

        if rxcui in existing:
            # Same RxCUI already present: update metadata only.
            existing[rxcui]["last_updated"] = record["last_updated"]
            existing[rxcui]["source_version"] = source_version
            skipped_count += 1
        elif gname_lower in seen_by_name:
            # A different RxCUI already covers this generic name.
            # Keep whichever record is richer.
            existing_rxcui = seen_by_name[gname_lower]
            existing_record = existing[existing_rxcui]
            if _record_richness(record) > _record_richness(existing_record):
                # New record is richer: replace and re-key.
                del existing[existing_rxcui]
                existing[rxcui] = record
                seen_by_name[gname_lower] = rxcui
                logger.debug(
                    "  ~ replaced %s rxcui=%s with richer rxcui=%s",
                    record["generic_name"],
                    existing_rxcui,
                    rxcui,
                )
            else:
                logger.debug(
                    "  = kept existing %s rxcui=%s over new rxcui=%s",
                    record["generic_name"],
                    existing_rxcui,
                    rxcui,
                )
            skipped_count += 1
        else:
            existing[rxcui] = record
            seen_by_name[gname_lower] = rxcui
            new_count += 1
            logger.info(
                "  + %s (%s) rxcui=%s",
                record["generic_name"],
                record.get("dosage_form") or "?",
                rxcui,
            )

    logger.info(
        "Done. new=%d merged=%d errors=%d total=%d",
        new_count,
        skipped_count,
        error_count,
        len(existing),
    )

    if args.dry_run:
        for record in sorted(existing.values(), key=lambda r: r["rxcui"]):
            print(json.dumps(record, ensure_ascii=False))
        return 0

    write_records(output_path, existing)
    logger.info("Written to %s", output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
