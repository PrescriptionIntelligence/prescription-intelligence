"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/* =========================================================
   API TYPES
   ========================================================= */

type DoseComponent = {
  value: number;
  unit: string;
};

type RankedResult = {
  brand_name?: string;
  matched_term?: string;
  score?: number;
};

type MedicineEvidence = {
  accepted?: boolean;
  full_text_similarity?: number;
  token_similarity?: number;
  token_coverage?: number;
  exact_match?: boolean;
  prefix_match?: boolean;
  ocr_corrected?: boolean;
  candidate_variant?: string;
  second_best_score?: number;
  ranked_results?: RankedResult[];
};

type Medicine = {
  name?: string | null;
  generic_name?: string | null;
  brand_name?: string | null;

  strength_value?: string | number | null;
  strength_unit?: string | null;
  strength_components?: DoseComponent[];

  dose_value?: number | null;
  dose_unit?: string | null;

  daily_dose_value?: number | null;
  daily_dose_unit?: string | null;
  daily_dose_components?: DoseComponent[];

  route?: string | null;

  frequency_value?: number | null;
  frequency_unit?: string | null;

  duration_value?: number | null;
  duration_unit?: string | null;

  instructions?: string | null;

  extraction_confidence?: number | null;
  normalization_confidence?: number | null;

  confidence?: number | null;
  needs_review?: boolean;

  matched_term?: string | null;
  evidence?: MedicineEvidence;

  raw_text?: string | null;
};

type SafetyFlag = {
  type?: string;
  severity?: string;
  medicine?: string | null;
  message?: string;
};

type PrescriptionResult = {
  message?: string;
  prescription_id?: string;
  file_name?: string;
  file_type?: string;
  file_path?: string;
  status?: string;
  raw_text?: string | null;
  medicines?: Medicine[];
  safety_flags?: SafetyFlag[];
};

/* =========================================================
   HELPERS
   ========================================================= */

function formatConfidence(value?: number | null) {
  if (typeof value !== "number") return "—";
  return `${Math.round(value * 100)}%`;
}

function confidenceTone(value?: number | null) {
  if (typeof value !== "number") {
    return "bg-[#f0f3f1] text-[#6f7b75]";
  }

  if (value >= 0.85) {
    return "bg-[#e8f2eb] text-[#567060]";
  }

  if (value >= 0.7) {
    return "bg-[#f4f0e5] text-[#776b4f]";
  }

  return "bg-[#f8ece8] text-[#8a6258]";
}

function getOverallConfidence(medicine: Medicine) {
  if (typeof medicine.confidence === "number") {
    return medicine.confidence;
  }

  if (
    typeof medicine.extraction_confidence === "number" &&
    typeof medicine.normalization_confidence === "number"
  ) {
    return (
      (medicine.extraction_confidence +
        medicine.normalization_confidence) /
      2
    );
  }

  return (
    medicine.normalization_confidence ??
    medicine.extraction_confidence ??
    0
  );
}

function getReviewRequired(medicine: Medicine) {
  return (
    medicine.needs_review === true ||
    getOverallConfidence(medicine) < 0.85
  );
}

/* =========================================================
   MEDICINE CARD
   ========================================================= */

function MedicineCard({
  medicine,
  index,
}: {
  medicine: Medicine;
  index: number;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const confidence = getOverallConfidence(medicine);
  const percentage = Math.round(confidence * 100);
  const reviewRequired = getReviewRequired(medicine);

  return (
    <article className="rounded-[24px] border border-[#e0e8e3] bg-[#fbfcfb] p-5 transition hover:border-[#cfdcd4] hover:shadow-[0_12px_35px_rgba(30,45,38,0.05)] sm:p-6">

      {/* MEDICINE HEADER */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">

        <div className="flex items-start gap-4">

          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#edf3ee] text-xs font-semibold text-[#60766a]">
            {String(index + 1).padStart(2, "0")}
          </div>

          <div>
            <h3 className="text-lg font-semibold tracking-[-0.02em]">
              {medicine.name || "Unresolved medicine"}
            </h3>

            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#7d8983]">
              {medicine.generic_name && (
                <span>{medicine.generic_name}</span>
              )}

              {medicine.brand_name &&
                medicine.brand_name !== medicine.generic_name && (
                  <>
                    <span className="text-[#b0b8b3]">·</span>
                    <span>{medicine.brand_name}</span>
                  </>
                )}
            </div>
          </div>

        </div>

        <div
          className={`w-fit rounded-full px-3 py-1.5 text-[10px] font-semibold ${confidenceTone(
            confidence
          )}`}
        >
          {reviewRequired
            ? `Review required · ${percentage}%`
            : `High confidence · ${percentage}%`}
        </div>

      </div>

      {/* CORE MEDICINE DATA */}
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">

        <div className="rounded-2xl bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Strength
          </div>

          <div className="mt-2 text-sm font-semibold text-[#35423c]">
            {medicine.strength_value !== null &&
            medicine.strength_value !== undefined
              ? `${medicine.strength_value} ${
                  medicine.strength_unit || ""
                }`
              : "—"}
          </div>
        </div>

        <div className="rounded-2xl bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Dose
          </div>

          <div className="mt-2 text-sm font-semibold text-[#35423c]">
            {medicine.dose_value !== null &&
            medicine.dose_value !== undefined
              ? `${medicine.dose_value} ${
                  medicine.dose_unit || ""
                }`
              : "—"}
          </div>
        </div>

        <div className="rounded-2xl bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Frequency
          </div>

          <div className="mt-2 text-sm font-semibold text-[#35423c]">
            {medicine.frequency_value !== null &&
            medicine.frequency_value !== undefined
              ? `${medicine.frequency_value} ${
                  medicine.frequency_unit || ""
                }`
              : "—"}
          </div>
        </div>

        <div className="rounded-2xl bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Duration
          </div>

          <div className="mt-2 text-sm font-semibold text-[#35423c]">
            {medicine.duration_value !== null &&
            medicine.duration_value !== undefined
              ? `${medicine.duration_value} ${
                  medicine.duration_unit || ""
                }`
              : "—"}
          </div>
        </div>

      </div>

      {/* SECONDARY DATA */}
      <div className="mt-3 grid gap-3 sm:grid-cols-3">

        <div className="rounded-2xl border border-[#e8ece9] bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Daily dose
          </div>

          <div className="mt-2 text-sm font-medium text-[#4b5952]">
            {medicine.daily_dose_value !== null &&
            medicine.daily_dose_value !== undefined
              ? `${medicine.daily_dose_value} ${
                  medicine.daily_dose_unit || ""
                } / day`
              : "—"}
          </div>
        </div>

        <div className="rounded-2xl border border-[#e8ece9] bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Route
          </div>

          <div className="mt-2 text-sm font-medium capitalize text-[#4b5952]">
            {medicine.route || "—"}
          </div>
        </div>

        <div className="rounded-2xl border border-[#e8ece9] bg-white p-4">
          <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
            Instructions
          </div>

          <div className="mt-2 text-sm font-medium text-[#4b5952]">
            {medicine.instructions || "—"}
          </div>
        </div>

      </div>

      {/* CONFIDENCE */}
      <div className="mt-5 rounded-2xl border border-[#e4eae6] bg-white p-4">

        <div className="flex items-center justify-between">

          <div>
            <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
              Intelligence confidence
            </div>

            <div className="mt-1 text-sm font-semibold text-[#435149]">
              {percentage}%
            </div>
          </div>

          <div className="text-right text-[10px] text-[#8b9690]">
            <div>
              Extraction{" "}
              <span className="font-semibold text-[#65746c]">
                {formatConfidence(
                  medicine.extraction_confidence
                )}
              </span>
            </div>

            <div className="mt-1">
              Normalization{" "}
              <span className="font-semibold text-[#65746c]">
                {formatConfidence(
                  medicine.normalization_confidence
                )}
              </span>
            </div>
          </div>

        </div>

        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-[#e9eeeb]">
          <div
            className="h-full rounded-full bg-[#6d8979] transition-all"
            style={{
              width: `${Math.min(percentage, 100)}%`,
            }}
          />
        </div>

      </div>

      {/* EVIDENCE TOGGLE */}
      <button
        onClick={() => setEvidenceOpen(!evidenceOpen)}
        className="mt-4 flex w-full items-center justify-between rounded-2xl border border-[#e2e9e4] bg-white px-4 py-3 text-left transition hover:bg-[#f8faf8]"
      >
        <div>
          <div className="text-xs font-semibold text-[#52625a]">
            Matching evidence
          </div>

          <div className="mt-1 text-[10px] text-[#929c97]">
            Inspect how the medicine was identified
          </div>
        </div>

        <span className="text-sm text-[#74827a]">
          {evidenceOpen ? "↑" : "↓"}
        </span>
      </button>

      {/* EVIDENCE */}
      {evidenceOpen && (
        <div className="mt-3 rounded-2xl border border-[#e1e8e3] bg-[#f6f9f6] p-5">

          <div className="grid gap-3 sm:grid-cols-2">

            <div>
              <div className="text-[9px] uppercase tracking-[0.14em] text-[#9aa49f]">
                Matched term
              </div>

              <div className="mt-1 text-sm font-medium">
                {medicine.matched_term || "—"}
              </div>
            </div>

            <div>
              <div className="text-[9px] uppercase tracking-[0.14em] text-[#9aa49f]">
                Candidate variant
              </div>

              <div className="mt-1 text-sm font-medium">
                {medicine.evidence?.candidate_variant || "—"}
              </div>
            </div>

            <div>
              <div className="text-[9px] uppercase tracking-[0.14em] text-[#9aa49f]">
                Exact match
              </div>

              <div className="mt-1 text-sm font-medium">
                {medicine.evidence?.exact_match
                  ? "Yes"
                  : "No"}
              </div>
            </div>

            <div>
              <div className="text-[9px] uppercase tracking-[0.14em] text-[#9aa49f]">
                OCR corrected
              </div>

              <div className="mt-1 text-sm font-medium">
                {medicine.evidence?.ocr_corrected
                  ? "Yes"
                  : "No"}
              </div>
            </div>

          </div>

          <div className="mt-5 border-t border-[#e0e7e2] pt-5">

            <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
              Similarity signals
            </div>

            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">

              {[
                [
                  "Full text",
                  medicine.evidence?.full_text_similarity,
                ],
                [
                  "Token similarity",
                  medicine.evidence?.token_similarity,
                ],
                [
                  "Token coverage",
                  medicine.evidence?.token_coverage,
                ],
                [
                  "2nd best",
                  medicine.evidence?.second_best_score,
                ],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl bg-white p-3"
                >
                  <div className="text-[9px] text-[#9aa49f]">
                    {label}
                  </div>

                  <div className="mt-1 text-sm font-semibold text-[#4e5c55]">
                    {typeof value === "number"
                      ? `${Math.round(value * 100)}%`
                      : "—"}
                  </div>
                </div>
              ))}

            </div>

          </div>

          {medicine.evidence?.ranked_results &&
            medicine.evidence.ranked_results.length > 0 && (
              <div className="mt-5 border-t border-[#e0e7e2] pt-5">

                <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
                  Ranked candidates
                </div>

                <div className="mt-3 space-y-2">

                  {medicine.evidence.ranked_results.map(
                    (candidate, candidateIndex) => (
                      <div
                        key={`${candidate.matched_term}-${candidateIndex}`}
                        className="flex items-center justify-between rounded-xl bg-white px-3 py-2.5"
                      >
                        <div className="text-xs text-[#596760]">
                          {candidate.matched_term ||
                            candidate.brand_name ||
                            "Candidate"}
                        </div>

                        <div className="font-mono text-[10px] text-[#7a8880]">
                          {typeof candidate.score === "number"
                            ? `${Math.round(
                                candidate.score * 100
                              )}%`
                            : "—"}
                        </div>
                      </div>
                    )
                  )}

                </div>

              </div>
            )}

          {medicine.raw_text && (
            <div className="mt-5 border-t border-[#e0e7e2] pt-5">

              <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
                Source prescription segment
              </div>

              <div className="mt-3 whitespace-pre-wrap rounded-xl bg-white p-4 text-xs leading-6 text-[#68756e]">
                {medicine.raw_text}
              </div>

            </div>
          )}

        </div>
      )}

    </article>
  );
}

/* =========================================================
   REVIEW PAGE
   ========================================================= */

export default function ReviewPage() {
  const [result, setResult] =
    useState<PrescriptionResult | null>(null);

  const [fileName, setFileName] = useState("");

  useEffect(() => {
    const storedResult =
      sessionStorage.getItem("prescription_review");

    const storedFileName =
      sessionStorage.getItem("prescription_file_name");

    if (storedResult) {
      try {
        setResult(JSON.parse(storedResult));
      } catch {
        setResult(null);
      }
    }

    if (storedFileName) {
      setFileName(storedFileName);
    }
  }, []);

  function startNewReview() {
    sessionStorage.removeItem("prescription_review");
    sessionStorage.removeItem("prescription_file_name");

    window.location.href = "/";
  }

  /* =======================================================
     EMPTY STATE
     ======================================================= */

  if (!result) {
    return (
      <main className="relative min-h-screen overflow-hidden bg-[#f1f5f2] text-[#17211d]">

        <div className="pointer-events-none absolute inset-0">
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{
              backgroundImage:
                "url('/images/pharma-background.png')",
            }}
          />

          <div className="absolute inset-0 bg-[#f1f5f2]/80" />

          <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(255,255,255,0.8),transparent_35%),radial-gradient(circle_at_80%_70%,rgba(220,235,224,0.7),transparent_40%)]" />
        </div>

        <nav className="relative z-10 border-b border-[#dbe5df]/80 bg-white/70 backdrop-blur-xl">

          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 lg:px-10">

            <Link
              href="/"
              className="flex items-center gap-3"
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-sm font-semibold text-white shadow-sm">
                Rx
              </span>

              <div>
                <div className="text-[15px] font-semibold tracking-[-0.02em]">
                  Prescription Intelligence
                </div>

                <div className="mt-0.5 text-[10px] uppercase tracking-[0.2em] text-[#82908a]">
                  Medication intelligence
                </div>
              </div>
            </Link>

            <div className="hidden items-center gap-2 text-xs text-[#738079] sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-[#6f8b7b]" />
              Pharmacy workspace
              <span className="text-[#b2bbb6]">·</span>
              Human review
            </div>

          </div>

        </nav>

        <section className="relative z-10 mx-auto flex min-h-[calc(100vh-81px)] max-w-7xl items-center justify-center px-6 py-20 lg:px-10">

          <div className="w-full max-w-2xl">

            <div className="rounded-[32px] border border-white/80 bg-white/85 p-3 shadow-[0_30px_100px_rgba(30,45,38,0.12)] backdrop-blur-xl">

              <div className="rounded-[26px] border border-[#e0e8e2] bg-[#f5f8f5]/90 px-7 py-12 text-center sm:px-12 sm:py-16">

                <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl border border-[#d9e5dc] bg-white text-sm font-semibold text-[#60766a] shadow-sm">
                  Rx
                </div>

                <div className="mt-7 inline-flex items-center gap-2 rounded-full border border-[#d9e3dc] bg-white px-3.5 py-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#718079]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#6d8979]" />
                  No active review
                </div>

                <h1 className="mt-6 text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
                  No prescription is ready for review.
                </h1>

                <p className="mx-auto mt-5 max-w-lg text-sm leading-7 text-[#737f78] sm:text-base">
                  Upload a prescription from the pharmacy workspace
                  to begin a structured review of the extracted
                  medicine information.
                </p>

                <div className="mt-9">
                  <button
                    onClick={startNewReview}
                    className="rounded-full bg-[#17211d] px-7 py-3.5 text-sm font-medium text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-[#26332d]"
                  >
                    Start a prescription review
                    <span className="ml-2">→</span>
                  </button>
                </div>

                <div className="mx-auto mt-12 flex max-w-md items-center justify-center gap-3 text-[10px] font-semibold uppercase tracking-[0.13em] text-[#89958e] sm:gap-5">

                  {[
                    ["01", "Upload"],
                    ["02", "Extract"],
                    ["03", "Review"],
                  ].map(([number, label], index) => (
                    <div
                      key={number}
                      className="flex items-center gap-3"
                    >
                      <span className="flex items-center gap-2">
                        <span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-[9px] text-[#65796d] shadow-sm">
                          {number}
                        </span>

                        {label}
                      </span>

                      {index < 2 && (
                        <span className="text-[#b6c0ba]">
                          →
                        </span>
                      )}
                    </div>
                  ))}

                </div>

                <div className="mx-auto mt-10 max-w-lg border-t border-[#dfe7e2] pt-6">
                  <p className="text-[11px] leading-5 text-[#8b9690]">
                    Prescription Intelligence is designed to support
                    pharmacy and healthcare workflows. AI-generated
                    information should always remain subject to
                    professional review.
                  </p>
                </div>

              </div>
            </div>

          </div>

        </section>

        <footer className="relative z-10 border-t border-[#dce5df]/80 bg-white/60 px-6 py-7 backdrop-blur-xl lg:px-10">

          <div className="mx-auto flex max-w-7xl flex-col gap-2 text-xs text-[#8a948f] sm:flex-row sm:items-center sm:justify-between">

            <span>
              Prescription Intelligence · Medication intelligence
              platform
            </span>

            <span>
              AI-assisted · Evidence-aware · Human-reviewed
            </span>

          </div>

        </footer>

      </main>
    );
  }

  /* =======================================================
     ACTIVE REVIEW
     ======================================================= */

  const medicines = Array.isArray(result.medicines)
    ? result.medicines
    : [];

  const safetyFlags = Array.isArray(result.safety_flags)
    ? result.safety_flags
    : [];

  const reviewCount = medicines.filter(
    getReviewRequired
  ).length;

  const confidenceValues = medicines
    .map(getOverallConfidence)
    .filter((value) => value > 0);

  const overallConfidence =
    confidenceValues.length > 0
      ? confidenceValues.reduce(
          (sum, value) => sum + value,
          0
        ) / confidenceValues.length
      : 0;

  return (
    <main className="min-h-screen bg-[#f2f6f3] text-[#17211d]">

      {/* NAVIGATION */}
      <nav className="sticky top-0 z-30 border-b border-[#dce5df] bg-white/90 backdrop-blur-xl">

        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-10">

          <Link
            href="/"
            className="flex items-center gap-3"
          >
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-sm font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-[15px] font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[10px] uppercase tracking-[0.2em] text-[#82908a]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <div className="hidden items-center gap-2 text-xs text-[#7c8881] sm:flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[#6d8979]" />
            Pharmacy workspace
            <span className="text-[#b2bbb6]">·</span>
            Human review
          </div>

        </div>

      </nav>

      {/* PAGE HEADER */}
      <section className="mx-auto max-w-7xl px-6 pb-8 pt-10 lg:px-10">

        <div className="flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">

          <div>

            <div className="flex items-center gap-2 text-xs font-medium text-[#718079]">

              <span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-[10px] text-[#60766a] shadow-sm">
                Rx
              </span>

              Prescription review

              <span className="text-[#b5bdb8]">·</span>

              {result.prescription_id || "Unknown ID"}

            </div>

            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
              Review the extracted information.
            </h1>

            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#737d78]">
              Review the OCR evidence, normalized medicine
              information, intelligence confidence, and safety
              findings before moving the prescription forward.
            </p>

          </div>

          <button
            onClick={startNewReview}
            className="shrink-0 rounded-full border border-[#cfdcd4] bg-white px-5 py-3 text-sm font-medium text-[#34413b] shadow-sm transition hover:border-[#b6c6bc] hover:shadow-md"
          >
            + New prescription
          </button>

        </div>

      </section>

      {/* SUMMARY */}
      <section className="mx-auto max-w-7xl px-6 lg:px-10">

        <div className="grid gap-4 md:grid-cols-3">

          <div className="rounded-3xl border border-[#dce6df] bg-white p-5 shadow-[0_10px_35px_rgba(30,45,38,0.04)]">

            <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
              Medicines detected
            </div>

            <div className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              {medicines.length}
            </div>

            <div className="mt-1 text-xs text-[#7e8983]">
              Normalized medicine candidates
            </div>

          </div>

          <div className="rounded-3xl border border-[#dce6df] bg-white p-5 shadow-[0_10px_35px_rgba(30,45,38,0.04)]">

            <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
              Intelligence confidence
            </div>

            <div className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              {formatConfidence(overallConfidence)}
            </div>

            <div className="mt-1 text-xs text-[#7e8983]">
              Average medicine confidence
            </div>

          </div>

          <div className="rounded-3xl border border-[#dce6df] bg-white p-5 shadow-[0_10px_35px_rgba(30,45,38,0.04)]">

            <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
              Review queue
            </div>

            <div className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              {reviewCount}
            </div>

            <div className="mt-1 text-xs text-[#7e8983]">
              {reviewCount === 0
                ? "No medicine requires additional review"
                : "Medicine candidates need attention"}
            </div>

          </div>

        </div>

      </section>

      {/* PRESCRIPTION META */}
      <section className="mx-auto max-w-7xl px-6 pt-5 lg:px-10">

        <div className="rounded-3xl border border-[#dce6df] bg-white p-5 shadow-[0_12px_40px_rgba(30,45,38,0.05)]">

          <div className="grid gap-5 md:grid-cols-3">

            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                File
              </div>

              <div className="mt-2 truncate text-sm font-medium text-[#435149]">
                {fileName ||
                  result.file_name ||
                  "Prescription image"}
              </div>
            </div>

            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                Prescription ID
              </div>

              <div className="mt-2 font-mono text-xs text-[#596861]">
                {result.prescription_id || "—"}
              </div>
            </div>

            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                Processing
              </div>

              <div className="mt-2 flex items-center gap-2 text-sm font-medium">

                <span className="h-2 w-2 rounded-full bg-[#668474]" />

                {result.status
                  ? result.status.charAt(0).toUpperCase() +
                    result.status.slice(1)
                  : "Processed"}

              </div>
            </div>

          </div>

        </div>

      </section>

      {/* MAIN WORKSPACE */}
      <section className="mx-auto max-w-7xl px-6 py-8 lg:px-10">

        <div className="grid gap-6 lg:grid-cols-[0.85fr_1.35fr]">

          {/* OCR EVIDENCE */}
          <div className="h-fit rounded-3xl border border-[#dce6df] bg-white p-6 shadow-[0_12px_40px_rgba(30,45,38,0.05)] lg:sticky lg:top-24">

            <div className="flex items-start justify-between gap-4">

              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                  OCR evidence
                </div>

                <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em]">
                  Extracted text
                </h2>
              </div>

              <span className="rounded-full bg-[#edf3ee] px-3 py-1.5 text-[10px] font-medium text-[#61766a]">
                Evidence
              </span>

            </div>

            <div className="mt-5 max-h-[560px] overflow-auto rounded-2xl border border-[#e1e8e3] bg-[#f7f9f7] p-5">

              <p className="whitespace-pre-wrap text-sm leading-7 text-[#58655e]">
                {result.raw_text ||
                  "No OCR text returned."}
              </p>

            </div>

            <div className="mt-4 rounded-2xl bg-[#f3f7f4] p-4">

              <div className="flex items-start gap-3">

                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white text-xs text-[#60766a]">
                  i
                </span>

                <p className="text-xs leading-5 text-[#78847e]">
                  OCR text is preserved as evidence. It should
                  not be treated as a final clinical
                  interpretation.
                </p>

              </div>

            </div>

          </div>

          {/* MEDICINE INTELLIGENCE */}
          <div>

            <div className="mb-5 flex items-end justify-between">

              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                  Medicine intelligence
                </div>

                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                  Normalized medicines
                </h2>
              </div>

              <span className="rounded-full bg-[#edf3ee] px-3 py-1.5 text-[10px] font-medium text-[#61766a]">
                {medicines.length}{" "}
                {medicines.length === 1
                  ? "candidate"
                  : "candidates"}
              </span>

            </div>

            {medicines.length === 0 ? (

              <div className="rounded-3xl border border-dashed border-[#ccd9d1] bg-white p-12 text-center text-sm text-[#7b8780]">
                No medicine candidates were returned.
              </div>

            ) : (

              <div className="space-y-4">

                {medicines.map((medicine, index) => (
                  <MedicineCard
                    key={`${medicine.name}-${index}`}
                    medicine={medicine}
                    index={index}
                  />
                ))}

              </div>

            )}

          </div>

        </div>

        {/* SAFETY INTELLIGENCE */}
        <div className="mt-6 rounded-3xl border border-[#dce6df] bg-white p-6 shadow-[0_12px_40px_rgba(30,45,38,0.05)]">

          <div className="flex items-start gap-4">

            <span
              className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
                safetyFlags.length === 0
                  ? "bg-[#edf3ee] text-[#60766a]"
                  : "bg-[#f8ece8] text-[#8a6258]"
              }`}
            >
              {safetyFlags.length === 0 ? "✓" : "!"}
            </span>

            <div>

              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                Safety intelligence
              </div>

              <h2 className="mt-1 text-xl font-semibold">
                Review findings
              </h2>

            </div>

          </div>

          {safetyFlags.length === 0 ? (

            <div className="mt-5 rounded-2xl bg-[#f3f7f4] p-5">

              <div className="text-sm font-semibold text-[#52635a]">
                No safety flags were returned.
              </div>

              <p className="mt-1 text-xs leading-5 text-[#7d8983]">
                This does not mean the prescription is
                clinically cleared. Professional review remains
                required.
              </p>

            </div>

          ) : (

            <div className="mt-5 space-y-3">

              {safetyFlags.map((flag, index) => (
                <div
                  key={index}
                  className="rounded-2xl border border-[#eaded9] bg-[#fbf6f3] p-5"
                >

                  <div className="flex flex-wrap items-center gap-2">

                    {flag.severity && (
                      <span className="rounded-full bg-[#f4e5df] px-2.5 py-1 text-[10px] font-semibold uppercase text-[#825f55]">
                        {flag.severity}
                      </span>
                    )}

                    {flag.type && (
                      <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-medium text-[#776a65]">
                        {flag.type}
                      </span>
                    )}

                    {flag.medicine && (
                      <span className="text-xs font-medium text-[#695c57]">
                        {flag.medicine}
                      </span>
                    )}

                  </div>

                  <p className="mt-3 text-sm leading-6 text-[#765f58]">
                    {flag.message ||
                      "Safety finding requires review."}
                  </p>

                </div>
              ))}

            </div>

          )}

        </div>

        {/* HUMAN REVIEW */}
        <div className="mt-6 rounded-3xl border border-[#d7e3db] bg-[#eaf2ec] p-6">

          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">

            <div className="flex items-start gap-3">

              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-xs text-[#60766a] shadow-sm">
                i
              </span>

              <div>

                <div className="text-sm font-semibold text-[#4f6257]">
                  Human verification remains in the loop
                </div>

                <p className="mt-1 max-w-2xl text-xs leading-5 text-[#718078]">
                  OCR and AI-generated medicine information are
                  supporting evidence. A qualified professional
                  should verify the prescription before clinical
                  use.
                </p>

              </div>

            </div>

            <button
              onClick={startNewReview}
              className="shrink-0 rounded-full bg-[#17211d] px-5 py-3 text-sm font-medium text-white transition hover:bg-[#26332d]"
            >
              New prescription
            </button>

          </div>

        </div>

      </section>

      {/* FOOTER */}
      <footer className="border-t border-[#dce5df] bg-white px-6 py-7 lg:px-10">

        <div className="mx-auto flex max-w-7xl flex-col gap-2 text-xs text-[#8a948f] sm:flex-row sm:items-center sm:justify-between">

          <span>
            Prescription Intelligence · Medication intelligence
            platform
          </span>

          <span>
            AI-assisted · Evidence-aware · Human-reviewed
          </span>

        </div>

      </footer>

    </main>
  );
}