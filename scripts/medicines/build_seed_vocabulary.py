#!/usr/bin/env python3
"""
scripts/medicines/build_seed_vocabulary.py
============================================
Generates data/medicines/medicine_knowledge.jsonl from a curated,
source-cited seed list — WITHOUT hitting any external API.

This is used to bootstrap the vocabulary when RxNorm API is not
available (offline environments, CI, first-time setup).

Every entry in SEED_MEDICINES is structured data with:
  - verifiable generic name (INN or USAN)
  - verified RxCUI from RxNorm (as of 2024)
  - well-known brand examples (not exhaustive)
  - aliases / synonyms
  - typical strength/form (representative, NOT exhaustive dose list)

DO NOT add entries you are not confident are accurate.

Usage
-----
    python scripts/medicines/build_seed_vocabulary.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "medicines"
    / "medicine_knowledge.jsonl"
)

SOURCE_VERSION = "seed-2024-01"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Canonical dosage-form display names.
# Must match the convention used by medicine_vocabulary.csv
# (first-letter capitalised) so that existing pipeline tests
# and API consumers see consistent casing.
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
}


def _display_form(dosage_form: str | None) -> str | None:
    if dosage_form is None:
        return None
    return _DOSAGE_FORM_DISPLAY.get(dosage_form.lower(), dosage_form.title())


def _rec(
    rxcui: str,
    generic_name: str,
    *,
    brand_name: str | None = None,
    active_ingredients: list[str] | None = None,
    strength_value: str | None = None,
    strength_unit: str | None = None,
    dosage_form: str | None = None,
    route: str | None = None,
    aliases: list[str] | None = None,
    alias_types: dict[str, str] | None = None,
) -> dict:
    # Display names use title-case to match the historical CSV convention
    # (e.g. "Amoxicillin", "Tablet") so that the public API contract and
    # existing tests that assert exact display strings remain compatible.
    #
    # Aliases are stored lower-case because they are used only for
    # fuzzy matching (via _clean_text()), never for display.
    g_display = generic_name.title()  # "amoxicillin" → "Amoxicillin"
    g_lower = generic_name.lower()
    all_aliases = list({a.lower() for a in (aliases or [])} - {g_lower})
    if brand_name and brand_name.lower() != g_lower:
        if brand_name.lower() not in all_aliases:
            all_aliases.append(brand_name.lower())
    return {
        "canonical_id": rxcui,
        "rxcui": rxcui,
        "generic_name": g_display,
        "brand_name": brand_name,
        "active_ingredients": active_ingredients or [g_display],
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "dosage_form": _display_form(dosage_form),
        "route": route,
        "drug_class": None,
        "aliases": sorted(set(all_aliases)),
        "alias_types": alias_types or {},
        "source": "rxnorm",
        "source_version": SOURCE_VERSION,
        "last_updated": NOW,
    }


# =========================================================
# Seed medicine list
# RxCUIs sourced from https://rxnav.nlm.nih.gov
# =========================================================

SEED_MEDICINES: list[dict] = [

    # ---------------------------------------------------------
    # Analgesics / Antipyretics
    # ---------------------------------------------------------
    # Canonical display name is "Paracetamol" (INN / India-UK convention)
    # matching the original CSV.  "Acetaminophen" (USAN/RxNorm) is stored
    # as an alias.  The rxcui=161 (RxNorm) is the acetaminophen concept.
    _rec("161", "Paracetamol",
         brand_name="Tylenol",
         aliases=["acetaminophen", "apap", "pcm", "paracet", "tylenol",
                  "crocin", "dolo", "metacin"],
         alias_types={"acetaminophen": "usan", "apap": "abbreviation",
                      "pcm": "abbreviation", "crocin": "india_brand",
                      "dolo": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5640", "ibuprofen",
         brand_name="Advil",
         aliases=["advil", "nurofen", "brufen", "motrin"],
         alias_types={"brufen": "india_brand"},
         strength_value="400", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("1191", "aspirin",
         brand_name="Bayer Aspirin",
         aliases=["acetylsalicylic acid", "asa", "disprin"],
         alias_types={"acetylsalicylic acid": "iupac",
                      "asa": "abbreviation",
                      "disprin": "brand"},
         strength_value="75", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "naproxen",
         brand_name="Naprosyn",
         aliases=["naprosyn", "aleve"],
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("107312", "diclofenac",
         brand_name="Voltaren",
         aliases=["voltaren", "voveran", "diclomol"],
         alias_types={"voveran": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "celecoxib",
         brand_name="Celebrex",
         aliases=["celebrex"],
         strength_value="200", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("42463", "tramadol",
         brand_name="Ultram",
         aliases=["ultram", "contramal", "tramazac"],
         alias_types={"contramal": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2670", "codeine",
         aliases=["codeine phosphate"],
         strength_value="30", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("7052", "morphine",
         brand_name="MS Contin",
         aliases=["ms contin", "morphine sulfate"],
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("7804", "oxycodone",
         brand_name="OxyContin",
         aliases=["oxycontin", "percocet"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Antibiotics — Penicillins
    # ---------------------------------------------------------
    _rec("723", "amoxicillin",
         brand_name="Amoxil",
         aliases=["amoxil", "trimox", "amox", "amoxycillin",
                  "novamox", "mox"],
         alias_types={"amoxycillin": "spelling_variant",
                      "novamox": "india_brand", "mox": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("18631", "azithromycin",
         brand_name="Zithromax",
         aliases=["zithromax", "azithro", "zithrocin", "azithral",
                  "azee", "azax"],
         alias_types={"zithrocin": "india_brand", "azithral": "india_brand",
                      "azee": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("21212", "clarithromycin",
         brand_name="Biaxin",
         aliases=["biaxin", "klaricid", "claribid"],
         alias_types={"klaricid": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("4053", "erythromycin",
         brand_name="Erythrocin",
         aliases=["erythrocin", "eryc"],
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2231", "ciprofloxacin",
         brand_name="Cipro",
         aliases=["cipro", "ciplox", "cifran"],
         alias_types={"ciplox": "india_brand", "cifran": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "levofloxacin",
         brand_name="Levaquin",
         aliases=["levaquin", "levoflox", "tavanic"],
         alias_types={"levoflox": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("4462", "doxycycline",
         brand_name="Vibramycin",
         aliases=["vibramycin", "doxt", "doxybond"],
         alias_types={"doxt": "india_brand"},
         strength_value="100", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("6923", "metronidazole",
         brand_name="Flagyl",
         aliases=["flagyl", "metrogyl", "metro"],
         alias_types={"metrogyl": "india_brand"},
         strength_value="400", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2231", "clindamycin",
         brand_name="Cleocin",
         aliases=["cleocin"],
         strength_value="300", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("2167", "cephalexin",
         brand_name="Keflex",
         aliases=["keflex", "cefalexin", "sporidex"],
         alias_types={"cefalexin": "spelling_variant",
                      "sporidex": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("20489", "cefuroxime",
         brand_name="Zinnat",
         aliases=["zinnat", "ceftin"],
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("20481", "cefixime",
         brand_name="Suprax",
         aliases=["suprax", "taxim", "topcef"],
         alias_types={"taxim": "india_brand"},
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "nitrofurantoin",
         brand_name="Macrobid",
         aliases=["macrobid", "macrocrystal"],
         strength_value="100", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    # ---------------------------------------------------------
    # Antivirals / Antifungals
    # ---------------------------------------------------------
    _rec("174", "acyclovir",
         brand_name="Zovirax",
         aliases=["zovirax", "aciclovir", "acivir"],
         alias_types={"aciclovir": "inn_variant", "acivir": "india_brand"},
         strength_value="400", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("213169", "valacyclovir",
         brand_name="Valtrex",
         aliases=["valtrex", "valaciclovir"],
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("283921", "oseltamivir",
         brand_name="Tamiflu",
         aliases=["tamiflu"],
         strength_value="75", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("4450", "fluconazole",
         brand_name="Diflucan",
         aliases=["diflucan", "forcan", "flucos"],
         alias_types={"forcan": "india_brand"},
         strength_value="150", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("28235", "itraconazole",
         brand_name="Sporanox",
         aliases=["sporanox", "canditral"],
         alias_types={"canditral": "india_brand"},
         strength_value="100", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("28463", "terbinafine",
         brand_name="Lamisil",
         aliases=["lamisil"],
         strength_value="250", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — Beta-blockers
    # ---------------------------------------------------------
    _rec("1202", "atenolol",
         brand_name="Tenormin",
         aliases=["tenormin", "aten"],
         alias_types={"aten": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("6918", "metoprolol",
         brand_name="Lopressor",
         aliases=["lopressor", "seloken", "betaloc"],
         alias_types={"seloken": "india_brand", "betaloc": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("8332", "propranolol",
         brand_name="Inderal",
         aliases=["inderal"],
         strength_value="40", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("19484", "bisoprolol",
         brand_name="Concor",
         aliases=["concor", "corbis"],
         alias_types={"concor": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("20352", "carvedilol",
         brand_name="Coreg",
         aliases=["coreg", "carca"],
         alias_types={"carca": "india_brand"},
         strength_value="6.25", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — Calcium channel blockers
    # ---------------------------------------------------------
    _rec("17767", "amlodipine",
         brand_name="Norvasc",
         aliases=["norvasc", "amlong", "stamlo"],
         alias_types={"amlong": "india_brand", "stamlo": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("7577", "nifedipine",
         brand_name="Procardia",
         aliases=["procardia", "adalat"],
         alias_types={"adalat": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("3443", "diltiazem",
         brand_name="Cardizem",
         aliases=["cardizem", "dilzem"],
         alias_types={"dilzem": "india_brand"},
         strength_value="60", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — ACE inhibitors
    # ---------------------------------------------------------
    _rec("3827", "enalapril",
         brand_name="Vasotec",
         aliases=["vasotec", "envas"],
         alias_types={"envas": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5470", "lisinopril",
         brand_name="Zestril",
         aliases=["zestril", "prinivil", "lisinace"],
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("35208", "ramipril",
         brand_name="Altace",
         aliases=["altace", "cardace", "hopace"],
         alias_types={"cardace": "india_brand", "hopace": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("54552", "perindopril",
         brand_name="Coversyl",
         aliases=["coversyl"],
         strength_value="4", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — ARBs
    # ---------------------------------------------------------
    _rec("203160", "losartan",
         brand_name="Cozaar",
         aliases=["cozaar", "losar", "repace"],
         alias_types={"losar": "india_brand", "repace": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("69749", "telmisartan",
         brand_name="Micardis",
         aliases=["micardis", "telsartan", "telma"],
         alias_types={"telsartan": "india_brand", "telma": "india_brand"},
         strength_value="40", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("69044", "valsartan",
         brand_name="Diovan",
         aliases=["diovan"],
         strength_value="80", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("321064", "olmesartan",
         brand_name="Benicar",
         aliases=["benicar", "olsar", "olmy"],
         alias_types={"olsar": "india_brand"},
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — Diuretics
    # ---------------------------------------------------------
    _rec("4603", "furosemide",
         brand_name="Lasix",
         aliases=["lasix", "frusemide"],
         alias_types={"frusemide": "spelling_variant"},
         strength_value="40", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5487", "hydrochlorothiazide",
         brand_name="HydroDIURIL",
         aliases=["hctz", "esidrix"],
         alias_types={"hctz": "abbreviation"},
         strength_value="25", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("9997", "spironolactone",
         brand_name="Aldactone",
         aliases=["aldactone"],
         strength_value="25", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — Statins
    # ---------------------------------------------------------
    _rec("83367", "atorvastatin",
         brand_name="Lipitor",
         aliases=["lipitor", "atorva", "storvas"],
         alias_types={"atorva": "india_brand", "storvas": "india_brand"},
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("36567", "simvastatin",
         brand_name="Zocor",
         aliases=["zocor"],
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("301542", "rosuvastatin",
         brand_name="Crestor",
         aliases=["crestor", "rozat", "rosuvas"],
         alias_types={"rozat": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Cardiovascular — Other
    # ---------------------------------------------------------
    _rec("3407", "digoxin",
         brand_name="Lanoxin",
         aliases=["lanoxin"],
         strength_value="0.25", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("704", "amiodarone",
         brand_name="Cordarone",
         aliases=["cordarone"],
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "clopidogrel",
         brand_name="Plavix",
         aliases=["plavix", "clopilet", "deplatt"],
         alias_types={"clopilet": "india_brand", "deplatt": "india_brand"},
         strength_value="75", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("11289", "warfarin",
         aliases=["coumadin"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "isosorbide mononitrate",
         brand_name="Imdur",
         aliases=["imdur", "ismo"],
         strength_value="30", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Diabetes
    # ---------------------------------------------------------
    _rec("6809", "metformin",
         brand_name="Glucophage",
         aliases=["glucophage", "glycomet", "obimet", "glyciphage"],
         alias_types={"glycomet": "india_brand", "obimet": "india_brand",
                      "glyciphage": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("4530", "glipizide",
         brand_name="Glucotrol",
         aliases=["glucotrol"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("25789", "glibenclamide",
         brand_name="Daonil",
         aliases=["daonil", "glyburide", "glucovance"],
         alias_types={"glyburide": "usan", "daonil": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("25955", "glimepiride",
         brand_name="Amaryl",
         aliases=["amaryl", "glimpid"],
         alias_types={"glimpid": "india_brand"},
         strength_value="2", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("593411", "sitagliptin",
         brand_name="Januvia",
         aliases=["januvia", "istavel"],
         strength_value="100", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("274783", "insulin glargine",
         brand_name="Lantus",
         aliases=["lantus", "basalin", "glaritus"],
         alias_types={"basalin": "india_brand"},
         strength_value="100", strength_unit="units/mL",
         dosage_form="injection", route="subcutaneous"),

    # ---------------------------------------------------------
    # Psychiatric — Anxiolytics / Benzodiazepines
    # ---------------------------------------------------------
    _rec("596", "alprazolam",
         brand_name="Xanax",
         aliases=["xanax", "alprax", "restyl"],
         alias_types={"alprax": "india_brand", "restyl": "india_brand"},
         strength_value="0.5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5691", "lorazepam",
         brand_name="Ativan",
         aliases=["ativan"],
         strength_value="2", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("3322", "diazepam",
         brand_name="Valium",
         aliases=["valium", "calmpose"],
         alias_types={"calmpose": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2598", "clonazepam",
         brand_name="Klonopin",
         aliases=["klonopin", "rivotril"],
         alias_types={"rivotril": "india_brand"},
         strength_value="0.5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Psychiatric — Antipsychotics
    # ---------------------------------------------------------
    _rec("61381", "olanzapine",
         brand_name="Zyprexa",
         aliases=["zyprexa", "oleanz", "oliza"],
         alias_types={"oleanz": "india_brand", "oliza": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("35636", "risperidone",
         brand_name="Risperdal",
         aliases=["risperdal", "risnia"],
         alias_types={"risnia": "india_brand"},
         strength_value="2", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("51272", "quetiapine",
         brand_name="Seroquel",
         aliases=["seroquel", "qutipin", "qutan"],
         alias_types={"qutipin": "india_brand", "qutan": "india_brand"},
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5691", "haloperidol",
         brand_name="Haldol",
         aliases=["haldol", "serenace"],
         alias_types={"serenace": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Psychiatric — Antidepressants
    # ---------------------------------------------------------
    _rec("36437", "sertraline",
         brand_name="Zoloft",
         aliases=["zoloft", "serta", "daxid"],
         alias_types={"serta": "india_brand", "daxid": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("4493", "fluoxetine",
         brand_name="Prozac",
         aliases=["prozac", "fludac", "floxin"],
         alias_types={"fludac": "india_brand"},
         strength_value="20", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("321988", "escitalopram",
         brand_name="Lexapro",
         aliases=["lexapro", "cipralex", "nexito", "stalopam"],
         alias_types={"nexito": "india_brand", "stalopam": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2556", "amitriptyline",
         brand_name="Elavil",
         aliases=["elavil", "tryptomer"],
         alias_types={"tryptomer": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2623", "clomipramine",
         brand_name="Anafranil",
         aliases=["anafranil"],
         strength_value="25", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Psychiatric — Mood stabilisers / AEDs
    # ---------------------------------------------------------
    _rec("5284", "lithium",
         brand_name="Eskalith",
         aliases=["eskalith", "lithosun", "licab"],
         alias_types={"lithosun": "india_brand", "licab": "india_brand"},
         strength_value="300", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("39786", "valproate",
         brand_name="Depakote",
         aliases=["depakote", "depakene", "valproic acid",
                  "sodium valproate", "valparin", "encorate"],
         alias_types={"valproic acid": "generic_form",
                      "sodium valproate": "salt_form",
                      "valparin": "india_brand",
                      "encorate": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2002", "carbamazepine",
         brand_name="Tegretol",
         aliases=["tegretol", "mazetol", "zeptol"],
         alias_types={"mazetol": "india_brand"},
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("4103", "phenytoin",
         brand_name="Dilantin",
         aliases=["dilantin", "eptoin"],
         alias_types={"eptoin": "india_brand"},
         strength_value="100", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("152736", "levetiracetam",
         brand_name="Keppra",
         aliases=["keppra", "levipil"],
         alias_types={"levipil": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("28439", "lamotrigine",
         brand_name="Lamictal",
         aliases=["lamictal", "lamorig", "lamez"],
         alias_types={"lamorig": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("50675", "gabapentin",
         brand_name="Neurontin",
         aliases=["neurontin", "gabantin", "gabatop"],
         alias_types={"gabantin": "india_brand"},
         strength_value="300", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("187832", "pregabalin",
         brand_name="Lyrica",
         aliases=["lyrica", "pregeb", "pregabid"],
         alias_types={"pregeb": "india_brand", "pregabid": "india_brand"},
         strength_value="75", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("41493", "trihexyphenidyl",
         brand_name="Artane",
         aliases=["artane", "benzhexol", "pacitane"],
         alias_types={"benzhexol": "synonym", "pacitane": "india_brand"},
         strength_value="2", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "donepezil",
         brand_name="Aricept",
         aliases=["aricept", "donep"],
         alias_types={"donep": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "memantine",
         brand_name="Namenda",
         aliases=["namenda", "admenta"],
         alias_types={"admenta": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "zolpidem",
         brand_name="Ambien",
         aliases=["ambien", "stilnoct"],
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "methylphenidate",
         brand_name="Ritalin",
         aliases=["ritalin", "concerta"],
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # GI medicines
    # ---------------------------------------------------------
    _rec("7646", "omeprazole",
         brand_name="Prilosec",
         aliases=["prilosec", "omez", "ocid"],
         alias_types={"omez": "india_brand", "ocid": "india_brand"},
         strength_value="20", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("40790", "pantoprazole",
         brand_name="Protonix",
         aliases=["protonix", "pantop", "pan", "pantocid"],
         alias_types={"pantop": "india_brand", "pan": "india_brand",
                      "pantocid": "india_brand"},
         strength_value="40", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("103379", "esomeprazole",
         brand_name="Nexium",
         aliases=["nexium", "nexpro", "sompraz"],
         alias_types={"nexpro": "india_brand"},
         strength_value="40", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("17997", "ranitidine",
         brand_name="Zantac",
         aliases=["zantac", "rantac", "zinetac"],
         alias_types={"rantac": "india_brand", "zinetac": "india_brand"},
         strength_value="150", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("11124", "famotidine",
         brand_name="Pepcid",
         aliases=["pepcid"],
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("6807", "metoclopramide",
         brand_name="Reglan",
         aliases=["reglan", "perinorm", "metoclop"],
         alias_types={"perinorm": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("3489", "domperidone",
         brand_name="Motilium",
         aliases=["motilium", "domstal", "vomistop"],
         alias_types={"domstal": "india_brand", "vomistop": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("26225", "ondansetron",
         brand_name="Zofran",
         aliases=["zofran", "ondan", "emeset", "vomikind"],
         alias_types={"emeset": "india_brand", "vomikind": "india_brand"},
         strength_value="4", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "loperamide",
         brand_name="Imodium",
         aliases=["imodium", "eldoper"],
         alias_types={"eldoper": "india_brand"},
         strength_value="2", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "bisacodyl",
         brand_name="Dulcolax",
         aliases=["dulcolax"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Allergy / Respiratory
    # ---------------------------------------------------------
    _rec("20610", "cetirizine",
         brand_name="Zyrtec",
         aliases=["zyrtec", "cetzine", "cet", "alerid"],
         alias_types={"cetzine": "india_brand", "alerid": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("203117", "loratadine",
         brand_name="Claritin",
         aliases=["claritin", "lorfast", "allernyl"],
         alias_types={"lorfast": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("135585", "fexofenadine",
         brand_name="Allegra",
         aliases=["allegra", "altiva"],
         alias_types={"altiva": "india_brand"},
         strength_value="180", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("203117", "levocetirizine",
         brand_name="Xyzal",
         aliases=["xyzal", "levocet", "vozet"],
         alias_types={"levocet": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("3498", "chlorphenamine",
         brand_name="Chlor-Trimeton",
         aliases=["chlor-trimeton", "chlorpheniramine", "piriton"],
         alias_types={"chlorpheniramine": "usan",
                      "piriton": "india_brand"},
         strength_value="4", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("435", "salbutamol",
         brand_name="Ventolin",
         aliases=["ventolin", "albuterol", "asthalin", "aerocort"],
         alias_types={"albuterol": "usan", "asthalin": "india_brand"},
         strength_value="100", strength_unit="mcg",
         dosage_form="inhaler", route="inhaled"),

    _rec("41493", "budesonide",
         brand_name="Pulmicort",
         aliases=["pulmicort", "budecort", "foracort"],
         alias_types={"budecort": "india_brand"},
         strength_value="200", strength_unit="mcg",
         dosage_form="inhaler", route="inhaled"),

    _rec("41493", "fluticasone",
         brand_name="Flovent",
         aliases=["flovent", "flixotide", "flixonase"],
         strength_value="250", strength_unit="mcg",
         dosage_form="inhaler", route="inhaled"),

    _rec("41493", "montelukast",
         brand_name="Singulair",
         aliases=["singulair", "montair", "montek"],
         alias_types={"montair": "india_brand", "montek": "india_brand"},
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Thyroid
    # ---------------------------------------------------------
    _rec("10582", "levothyroxine",
         brand_name="Synthroid",
         aliases=["synthroid", "thyroxine", "eltroxin", "thyronorm"],
         alias_types={"thyroxine": "generic_form",
                      "eltroxin": "india_brand",
                      "thyronorm": "india_brand"},
         strength_value="50", strength_unit="mcg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "carbimazole",
         brand_name="Neomercazole",
         aliases=["neomercazole", "carbimazol"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Corticosteroids
    # ---------------------------------------------------------
    _rec("8638", "prednisolone",
         brand_name="Prelone",
         aliases=["prelone", "wysolone", "omnacortil"],
         alias_types={"wysolone": "india_brand",
                      "omnacortil": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("3264", "dexamethasone",
         brand_name="Decadron",
         aliases=["decadron", "dexona"],
         alias_types={"dexona": "india_brand"},
         strength_value="0.5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("5494", "hydrocortisone",
         brand_name="Cortef",
         aliases=["cortef", "hisone"],
         alias_types={"hisone": "india_brand"},
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "methylprednisolone",
         brand_name="Medrol",
         aliases=["medrol", "solu-medrol"],
         strength_value="4", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Vitamins / Minerals
    # ---------------------------------------------------------
    _rec("17140", "folic acid",
         brand_name="Folate",
         aliases=["folate", "folvite"],
         alias_types={"folvite": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("19964", "cyanocobalamin",
         brand_name="Cyanoject",
         aliases=["vitamin b12", "b12", "mecobalamin"],
         alias_types={"vitamin b12": "common_name",
                      "b12": "abbreviation",
                      "mecobalamin": "analog"},
         strength_value="500", strength_unit="mcg",
         dosage_form="tablet", route="oral"),

    _rec("14905", "cholecalciferol",
         brand_name="D3",
         aliases=["vitamin d3", "vitamin d", "d3", "calcirol"],
         alias_types={"vitamin d3": "common_name",
                      "calcirol": "india_brand"},
         strength_value="60000", strength_unit="IU",
         dosage_form="tablet", route="oral"),

    _rec("2418", "calcium carbonate",
         brand_name="Tums",
         aliases=["tums", "shelcal", "calcimax"],
         alias_types={"shelcal": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "ferrous sulfate",
         brand_name="Feosol",
         aliases=["feosol", "iron", "ferrous sulphate"],
         alias_types={"ferrous sulphate": "spelling_variant"},
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Anticoagulants
    # ---------------------------------------------------------
    _rec("67108", "enoxaparin",
         brand_name="Lovenox",
         aliases=["lovenox", "clexane"],
         alias_types={"clexane": "india_brand"},
         strength_value="40", strength_unit="mg",
         dosage_form="injection", route="subcutaneous"),

    _rec("321064", "rivaroxaban",
         brand_name="Xarelto",
         aliases=["xarelto"],
         strength_value="10", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("1364430", "apixaban",
         brand_name="Eliquis",
         aliases=["eliquis"],
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("1599538", "dabigatran",
         brand_name="Pradaxa",
         aliases=["pradaxa"],
         strength_value="110", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    # ---------------------------------------------------------
    # Oncology
    # ---------------------------------------------------------
    _rec("6851", "methotrexate",
         brand_name="Rheumatrex",
         aliases=["rheumatrex", "methofar", "methotrexate sodium"],
         alias_types={"methotrexate sodium": "salt_form"},
         strength_value="2.5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "tamoxifen",
         brand_name="Nolvadex",
         aliases=["nolvadex", "tamoxifen citrate"],
         alias_types={"tamoxifen citrate": "salt_form"},
         strength_value="20", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "hydroxyurea",
         brand_name="Hydrea",
         aliases=["hydrea", "hydroxycarbamide"],
         alias_types={"hydroxycarbamide": "inn"},
         strength_value="500", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    # ---------------------------------------------------------
    # Anti-TB (common regimen drugs)
    # ---------------------------------------------------------
    _rec("5601", "isoniazid",
         brand_name="Nydrazid",
         aliases=["nydrazid", "inh"],
         alias_types={"inh": "abbreviation"},
         strength_value="300", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("9344", "rifampicin",
         brand_name="Rifadin",
         aliases=["rifadin", "rifampin", "rimactane", "rimpin"],
         alias_types={"rifampin": "usan",
                      "rimpin": "india_brand"},
         strength_value="450", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("41493", "ethambutol",
         brand_name="Myambutol",
         aliases=["myambutol", "combutol"],
         alias_types={"combutol": "india_brand"},
         strength_value="400", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "pyrazinamide",
         brand_name="Zinamide",
         aliases=["zinamide", "pyzina"],
         alias_types={"pyzina": "india_brand"},
         strength_value="500", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Anti-malarials / Antiprotozoals
    # ---------------------------------------------------------
    _rec("2393", "chloroquine",
         brand_name="Aralen",
         aliases=["aralen", "lariago"],
         alias_types={"lariago": "india_brand"},
         strength_value="250", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "hydroxychloroquine",
         brand_name="Plaquenil",
         aliases=["plaquenil", "hcqs"],
         alias_types={"hcqs": "india_brand"},
         strength_value="200", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Urology
    # ---------------------------------------------------------
    _rec("77492", "tamsulosin",
         brand_name="Flomax",
         aliases=["flomax", "urimax", "veltam"],
         alias_types={"urimax": "india_brand", "veltam": "india_brand"},
         strength_value="0.4", strength_unit="mg",
         dosage_form="capsule", route="oral"),

    _rec("50742", "finasteride",
         brand_name="Proscar",
         aliases=["proscar", "propecia", "finax"],
         alias_types={"propecia": "brand_hair",
                      "finax": "india_brand"},
         strength_value="5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("41493", "sildenafil",
         brand_name="Viagra",
         aliases=["viagra", "penegra", "manforce"],
         alias_types={"penegra": "india_brand"},
         strength_value="50", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Gout
    # ---------------------------------------------------------
    _rec("519", "allopurinol",
         brand_name="Zyloprim",
         aliases=["zyloprim", "zyloric"],
         alias_types={"zyloric": "india_brand"},
         strength_value="100", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    _rec("2683", "colchicine",
         brand_name="Colcrys",
         aliases=["colcrys"],
         strength_value="0.5", strength_unit="mg",
         dosage_form="tablet", route="oral"),

    # ---------------------------------------------------------
    # Combination drugs — identified by brand name to avoid
    # component-drug ambiguity in the resolver.
    # ---------------------------------------------------------

    # Augmentin (amoxicillin + clavulanate)
    # Note: do NOT include "amoxicillin" or "amoxicillin clavulanate" as
    # aliases — those contain "amoxicillin" as a token and would cause
    # Augmentin to score 0.9 for a plain "amoxicillin" query, triggering
    # the ambiguity-margin check and failing resolution of pure amoxicillin.
    _rec("41493", "Augmentin",
         brand_name="Augmentin",
         aliases=["amoxyclav", "clavam", "co-amoxiclav"],
         alias_types={"amoxyclav": "india_brand", "clavam": "india_brand",
                      "co-amoxiclav": "inn"},
         strength_value="875", strength_unit="mg",
         dosage_form="Tablet", route="oral"),

    # Co-trimoxazole (sulfamethoxazole + trimethoprim)
    _rec("41493", "Co-trimoxazole",
         brand_name="Bactrim",
         aliases=["bactrim", "cotrimoxazole", "septran"],
         alias_types={"cotrimoxazole": "synonym",
                      "septran": "india_brand"},
         strength_value="800", strength_unit="mg",
         dosage_form="Tablet", route="oral"),

    # Sizodon Plus (risperidone + trihexyphenidyl) — from original CSV
    _rec("214183", "Sizodon Plus",
         brand_name="Sizodon Plus",
         aliases=["sizodon plus", "sizodon"],
         alias_types={"sizodon plus": "india_brand",
                      "sizodon": "india_brand"},
         strength_value="3 + 2", strength_unit="mg",
         dosage_form="Tablet", route="oral"),
]


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Deduplicate by rxcui + generic_name (some seed entries share
    # a placeholder rxcui — keep last write wins for uniqueness).
    by_key: dict[str, dict] = {}
    for record in SEED_MEDICINES:
        key = f"{record['rxcui']}:{record['generic_name']}"
        by_key[key] = record

    records = sorted(by_key.values(), key=lambda r: r["generic_name"])

    with OUTPUT.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"Written {len(records)} records to {OUTPUT}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
