"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { authFetch, isAuthenticated } from "@/lib/auth";

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
  review_note?: string;
  [key: string]: unknown;
};

type PrescriptionResult = {
  message?: string;
  prescription_id?: string;
  file_name?: string;
  file_type?: string;
  status?: string;
  raw_text?: string | null;
  medicines?: Medicine[];
  safety_flags?: SafetyFlag[];
};

type ReviewStatus = {
  prescription_id: string;
  review_status: string;
  reviewed_by_id?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  reviewer?: {
    id?: string;
    name?: string;
    email?: string;
    role?: string;
  } | null;
  high_priority_findings: number;
  total_findings: number;
};

type ReviewAudit = {
  id: string;
  prescription_id: string;
  reviewer_id: string;
  action: string;
  previous_status: string;
  new_status: string;
  finding_type?: string | null;
  finding_data?: {
    finding_index?: number;
    finding_key?: string;
    [key: string]: unknown;
  } | null;
  note?: string | null;
  created_at: string;
};

type ReviewHistory = {
  prescription_id: string;
  current_status: string;
  audits: ReviewAudit[];
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

function formatReviewStatus(status?: string) {
  if (!status) return "Pending";

  return status
    .split("_")
    .map(
      (part) =>
        part.charAt(0).toUpperCase() + part.slice(1)
    )
    .join(" ");
}

function formatAction(action: string) {
  return action
    .split("_")
    .map(
      (part) =>
        part.charAt(0).toUpperCase() + part.slice(1)
    )
    .join(" ");
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getSeverityClass(severity?: string) {
  const normalized = String(
    severity || ""
  ).toLowerCase();

  if (
    normalized === "high" ||
    normalized === "critical" ||
    normalized === "error"
  ) {
    return "bg-[#fff0f0] text-[#a74646] border-[#efcece]";
  }

  if (normalized === "medium") {
    return "bg-[#fff7df] text-[#a47b2c] border-[#eadcae]";
  }

  return "bg-[#f1f5f2] text-[#65746c] border-[#dce5df]";
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

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          [
            "Strength",
            medicine.strength_value !== null &&
            medicine.strength_value !== undefined
              ? `${medicine.strength_value} ${
                  medicine.strength_unit || ""
                }`
              : "—",
          ],
          [
            "Dose",
            medicine.dose_value !== null &&
            medicine.dose_value !== undefined
              ? `${medicine.dose_value} ${
                  medicine.dose_unit || ""
                }`
              : "—",
          ],
          [
            "Frequency",
            medicine.frequency_value !== null &&
            medicine.frequency_value !== undefined
              ? `${medicine.frequency_value} ${
                  medicine.frequency_unit || ""
                }`
              : "—",
          ],
          [
            "Duration",
            medicine.duration_value !== null &&
            medicine.duration_value !== undefined
              ? `${medicine.duration_value} ${
                  medicine.duration_unit || ""
                }`
              : "—",
          ],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="rounded-2xl bg-white p-4"
          >
            <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[#9aa49f]">
              {label}
            </div>

            <div className="mt-2 text-sm font-semibold text-[#35423c]">
              {value}
            </div>
          </div>
        ))}
      </div>

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

      <button
        onClick={() =>
          setEvidenceOpen((open) => !open)
        }
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
                {medicine.evidence?.candidate_variant ||
                  "—"}
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
   FINDING CARD
   ========================================================= */

function FindingCard({
  flag,
  index,
  resolvedAction,
  busy,
  onAction,
}: {
  flag: SafetyFlag;
  index: number;
  resolvedAction?: string | null;
  busy: boolean;
  onAction: (
    action: "confirm" | "correct" | "dismiss" | "clarify",
    index: number,
    flag: SafetyFlag
  ) => void;
}) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");

  const resolved =
    resolvedAction === "confirm" ||
    resolvedAction === "correct" ||
    resolvedAction === "dismiss";

  const severity = String(
    flag.severity || "review"
  ).toLowerCase();

  const actionLabel =
    resolvedAction === "confirm"
      ? "Confirmed"
      : resolvedAction === "correct"
      ? "Corrected"
      : resolvedAction === "dismiss"
      ? "Dismissed"
      : null;

  function submitAction(
    action: "confirm" | "correct" | "dismiss" | "clarify"
  ) {
    onAction(action, index, {
      ...flag,
      review_note: note,
    });

    setNoteOpen(false);
    setNote("");
  }

  return (
    <article
      className={`rounded-[24px] border p-5 ${
        resolved
          ? "border-[#cbe0d3] bg-[#f8fcf9]"
          : severity === "high" ||
            severity === "critical" ||
            severity === "error"
          ? "border-[#efd7d7] bg-[#fff9f9]"
          : "border-[#eaded9] bg-[#fbf7f4]"
      }`}
    >
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-[10px] font-semibold text-[#6a7770] shadow-sm">
              {String(index + 1).padStart(2, "0")}
            </span>

            {flag.severity && (
              <span
                className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase ${getSeverityClass(
                  flag.severity
                )}`}
              >
                {flag.severity}
              </span>
            )}

            {flag.type && (
              <span className="rounded-full border border-[#e0e7e2] bg-white px-2.5 py-1 text-[10px] font-medium text-[#68756e]">
                {flag.type}
              </span>
            )}

            {flag.medicine && (
              <span className="text-xs font-medium text-[#695c57]">
                {flag.medicine}
              </span>
            )}
          </div>

          <p className="mt-4 max-w-3xl text-sm leading-6 text-[#665b57]">
            {flag.message ||
              "Safety finding requires professional review."}
          </p>

          {resolved && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[#cbe0d3] bg-[#edf8f1] px-3 py-1.5 text-[10px] font-semibold text-[#35664d]">
              <span>✓</span>
              {actionLabel}
            </div>
          )}

          {resolvedAction && !resolved && (
            <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-[#eadcae] bg-[#fff7df] px-3 py-1.5 text-[10px] font-semibold text-[#8b6b2b]">
              Clarification requested
            </div>
          )}
        </div>

        <div className="w-full lg:w-auto">
          {!resolved && (
            <div className="flex flex-col gap-2 lg:min-w-[290px]">
              {noteOpen && (
                <textarea
                  value={note}
                  onChange={(event) =>
                    setNote(event.target.value)
                  }
                  placeholder="Optional review note..."
                  rows={3}
                  className="w-full resize-none rounded-2xl border border-[#d9e3dc] bg-white px-3 py-3 text-xs text-[#39473f] outline-none transition placeholder:text-[#a0aaa4] focus:border-[#8da798] focus:ring-2 focus:ring-[#eaf2ec]"
                />
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  disabled={busy}
                  onClick={() => submitAction("confirm")}
                  className="rounded-full bg-[#35664d] px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-[#294f3d] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Confirm
                </button>

                <button
                  disabled={busy}
                  onClick={() => submitAction("correct")}
                  className="rounded-full border border-[#cbd9d0] bg-white px-4 py-2.5 text-xs font-semibold text-[#496056] transition hover:bg-[#f5f8f5] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Correct
                </button>

                <button
                  disabled={busy}
                  onClick={() => submitAction("dismiss")}
                  className="rounded-full border border-[#ead0d0] bg-white px-4 py-2.5 text-xs font-semibold text-[#9a5555] transition hover:bg-[#fff6f6] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Dismiss
                </button>

                <button
                  disabled={busy}
                  onClick={() => submitAction("clarify")}
                  className="rounded-full border border-[#eadcae] bg-white px-4 py-2.5 text-xs font-semibold text-[#8b6b2b] transition hover:bg-[#fffaf0] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Clarify
                </button>

                <button
                  disabled={busy}
                  onClick={() =>
                    setNoteOpen((open) => !open)
                  }
                  className="rounded-full border border-[#dce5df] bg-white px-4 py-2.5 text-xs font-medium text-[#69776f] transition hover:bg-[#f7f9f7] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {noteOpen ? "Hide note" : "Add note"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
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

  const [review, setReview] =
    useState<ReviewStatus | null>(null);

  const [history, setHistory] =
    useState<ReviewHistory | null>(null);

  const [loadingReview, setLoadingReview] =
    useState(false);

  const [actionLoading, setActionLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    const storedResult =
      sessionStorage.getItem("prescription_review");

    const storedFileName =
      sessionStorage.getItem("prescription_file_name");

    if (storedResult) {
      try {
        const parsed = JSON.parse(storedResult);
        setResult(parsed);
      } catch {
        setResult(null);
      }
    }

    if (storedFileName) {
      setFileName(storedFileName);
    }
  }, []);

  const prescriptionId =
    result?.prescription_id || "";

  async function loadReviewState() {
    if (!prescriptionId) return;

    if (!isAuthenticated()) {
      setError(
        "Your pharmacist session is no longer active. Please sign in again."
      );
      return;
    }

    setLoadingReview(true);
    setError(null);

    try {
      const [statusResponse, historyResponse] =
        await Promise.all([
          authFetch(
            `/prescriptions/${encodeURIComponent(
              prescriptionId
            )}/review`
          ),
          authFetch(
            `/prescriptions/${encodeURIComponent(
              prescriptionId
            )}/review/history`
          ),
        ]);

      if (!statusResponse.ok) {
        const body = await statusResponse
          .json()
          .catch(() => null);

        throw new Error(
          body?.detail ||
            "Unable to load prescription review status."
        );
      }

      if (!historyResponse.ok) {
        const body = await historyResponse
          .json()
          .catch(() => null);

        throw new Error(
          body?.detail ||
            "Unable to load review history."
        );
      }

      const statusData =
        (await statusResponse.json()) as ReviewStatus;

      const historyData =
        (await historyResponse.json()) as ReviewHistory;

      setReview(statusData);
      setHistory(historyData);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load review information."
      );
    } finally {
      setLoadingReview(false);
    }
  }

  useEffect(() => {
    if (prescriptionId) {
      void loadReviewState();
    }
  }, [prescriptionId]);

  function startNewReview() {
    sessionStorage.removeItem(
      "prescription_review"
    );

    sessionStorage.removeItem(
      "prescription_file_name"
    );

    window.location.href = "/";
  }

  async function startReview() {
    if (!prescriptionId) return;

    setActionLoading(true);
    setError(null);

    try {
      const response = await authFetch(
        `/prescriptions/${encodeURIComponent(
          prescriptionId
        )}/review`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            action: "start_review",
          }),
        }
      );

      const body = await response
        .json()
        .catch(() => null);

      if (!response.ok) {
        throw new Error(
          body?.detail ||
            "Unable to start the prescription review."
        );
      }

      setReview(body as ReviewStatus);

      await loadReviewState();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to start review."
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function completeReview() {
    if (!prescriptionId) return;

    setActionLoading(true);
    setError(null);

    try {
      const response = await authFetch(
        `/prescriptions/${prescriptionId}/review`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            action: "complete_review",
            note: null,
          }),
        }
      );

      const data = await response.json();

      if (response.status === 401 || response.status === 403) {
        throw new Error(
          data?.detail || "You are not authorized to complete this review."
        );
      }

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to complete pharmacist review."
        );
      }

      setReview(data);

      await loadReviewState();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to complete pharmacist review."
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function performFindingAction(
    action:
      | "confirm"
      | "correct"
      | "dismiss"
      | "clarify",
    index: number,
    flag: SafetyFlag
  ) {
    if (!prescriptionId) return;

    setActionLoading(true);
    setError(null);

    try {
      const findingData = {
        ...flag,
      };

      delete findingData.review_note;

      const note =
        typeof flag.review_note === "string"
          ? flag.review_note
          : undefined;

      const response = await authFetch(
        `/prescriptions/${encodeURIComponent(
          prescriptionId
        )}/review`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            action,
            finding: {
              finding_type: flag.type || "unknown",
              finding_index: index,
              finding_data: findingData,
            },
            note,
          }),
        }
      );

      const body = await response
        .json()
        .catch(() => null);

      if (!response.ok) {
        throw new Error(
          body?.detail ||
            `Unable to ${formatAction(
              action
            ).toLowerCase()} this finding.`
        );
      }

      setReview(body as ReviewStatus);

      await loadReviewState();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save review action."
      );
    } finally {
      setActionLoading(false);
    }
  }

  function getLatestFindingAction(
    index: number
  ): string | null {
    const audits = history?.audits || [];

    const relevant = audits
      .filter(
        (audit) =>
          audit.finding_data?.finding_index ===
          index
      )
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() -
          new Date(b.created_at).getTime()
      );

    if (relevant.length === 0) {
      return null;
    }

    return relevant[relevant.length - 1].action;
  }

  const medicines = Array.isArray(result?.medicines)
    ? result.medicines
    : [];

  const safetyFlags = Array.isArray(
    result?.safety_flags
  )
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

  const unresolvedFindingCount =
    useMemo(() => {
      return safetyFlags.reduce(
        (count, _, index) => {
          const action =
            getLatestFindingAction(index);

          const resolved =
            action === "confirm" ||
            action === "correct" ||
            action === "dismiss";

          return resolved ? count : count + 1;
        },
        0
      );
    }, [safetyFlags, history]);

  const isFinalized =
    review?.review_status === "verified" ||
    review?.review_status === "rejected";

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
                  Upload a prescription from the pharmacy
                  workspace to begin a structured review of
                  the extracted medicine information.
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
                    Prescription Intelligence is designed to
                    support pharmacy and healthcare workflows.
                    AI-generated information should always remain
                    subject to professional review.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <footer className="relative z-10 border-t border-[#dce5df]/80 bg-white/60 px-6 py-7 backdrop-blur-xl lg:px-10">
          <div className="mx-auto flex max-w-7xl flex-col gap-2 text-xs text-[#8a948f] sm:flex-row sm:items-center sm:justify-between">
            <span>
              Prescription Intelligence · Medication
              intelligence platform
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

  return (
    <main className="min-h-screen bg-[#f2f6f3] text-[#17211d]">
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

      {/* HEADER */}
      <section className="mx-auto max-w-7xl px-6 pb-7 pt-10 lg:px-10">
        <div className="flex flex-col gap-7 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium text-[#718079]">
              <span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-[10px] text-[#60766a] shadow-sm">
                Rx
              </span>

              Prescription review

              <span className="text-[#b5bdb8]">·</span>

              {prescriptionId || "Unknown ID"}
            </div>

            <h1 className="mt-5 max-w-3xl text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
              Review the prescription.
            </h1>

            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#737d78]">
              Verify the extracted medicine information and
              resolve safety findings before completing the
              pharmacist review.
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

      {/* ERROR */}
      {error && (
        <section className="mx-auto max-w-7xl px-6 lg:px-10">
          <div className="rounded-2xl border border-[#efcece] bg-[#fff5f5] px-5 py-4 text-sm text-[#944949]">
            <div className="font-semibold">
              Review action could not be completed
            </div>

            <div className="mt-1 text-xs leading-5">
              {error}
            </div>
          </div>
        </section>
      )}

      {/* REVIEW STATUS */}
      <section className="mx-auto max-w-7xl px-6 pt-5 lg:px-10">
        <div className="rounded-[28px] border border-[#dce6df] bg-white p-5 shadow-[0_12px_40px_rgba(30,45,38,0.05)]">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-4">
              <div
                className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                  review?.review_status === "verified"
                    ? "bg-[#edf8f1] text-[#35664d]"
                    : review?.review_status === "rejected"
                    ? "bg-[#fff0f0] text-[#a74646]"
                    : "bg-[#fff7df] text-[#a47b2c]"
                }`}
              >
                {review?.review_status === "verified"
                  ? "✓"
                  : review?.review_status === "rejected"
                  ? "!"
                  : "•"}
              </div>

              <div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                  Prescription review status
                </div>

                <div className="mt-1 flex flex-wrap items-center gap-3">
                  <h2 className="text-xl font-semibold tracking-[-0.02em]">
                    {loadingReview
                      ? "Loading..."
                      : formatReviewStatus(
                          review?.review_status
                        )}
                  </h2>

                  {review && (
                    <span className="rounded-full border border-[#dce5df] bg-[#f7f9f7] px-3 py-1 text-[10px] font-medium text-[#68766f]">
                      {review.high_priority_findings}{" "}
                      high-priority unresolved
                    </span>
                  )}
                </div>

                <p className="mt-1 text-xs text-[#7d8983]">
                  {review?.review_status === "verified"
                    ? "Pharmacist review has been completed."
                    : review?.review_status ===
                      "needs_clarification"
                    ? "Additional clarification is required before this review can be completed."
                    : review?.review_status ===
                      "rejected"
                    ? "The prescription review was rejected."
                    : "AI findings remain subject to pharmacist verification."}
                </p>
              </div>
            </div>

            {!isFinalized && (
              <div className="shrink-0">
                {review?.review_status === "pending" && (
                  <button
                    disabled={actionLoading}
                    onClick={startReview}
                    className="rounded-full bg-[#17211d] px-5 py-3 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {actionLoading
                      ? "Starting..."
                      : "Start pharmacist review"}
                  </button>
                )}

                {review?.review_status === "under_review" &&
                  unresolvedFindingCount === 0 && (
                    <button
                      disabled={actionLoading}
                      onClick={completeReview}
                      className="rounded-full bg-[#35664d] px-5 py-3 text-sm font-medium text-white transition hover:bg-[#2d5942] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {actionLoading
                        ? "Completing..."
                        : "Complete pharmacist review"}
                    </button>
                  )}
              </div>
            )}

          {review?.reviewer && (
            <div className="mt-5 border-t border-[#e4eae6] pt-5">
              <div className="flex flex-col gap-2 text-xs text-[#7d8983] sm:flex-row sm:items-center sm:justify-between">
                <span>
                  Last action by{" "}
                  <strong className="font-semibold text-[#526158]">
                    {review.reviewer.name ||
                      review.reviewer.email ||
                      "Pharmacist"}
                  </strong>
                </span>

                {review.reviewed_at && (
                  <span>
                    {new Date(review.reviewed_at).toLocaleString()}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
        </div>
      </section>

      {/* SUMMARY */}
      <section className="mx-auto max-w-7xl px-6 pt-5 lg:px-10">
        <div className="grid gap-4 md:grid-cols-4">
          {[
            [
              "Medicines detected",
              medicines.length.toString(),
              "Normalized medicine candidates",
            ],
            [
              "Confidence",
              formatConfidence(
                overallConfidence
              ),
              "Average medicine confidence",
            ],
            [
              "Safety findings",
              safetyFlags.length.toString(),
              "Original AI findings preserved",
            ],
            [
              "Unresolved",
              unresolvedFindingCount.toString(),
              "Findings requiring pharmacist attention",
            ],
          ].map(([label, value, description]) => (
            <div
              key={label}
              className="rounded-3xl border border-[#dce6df] bg-white p-5 shadow-[0_10px_35px_rgba(30,45,38,0.04)]"
            >
              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                {label}
              </div>

              <div className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
                {value}
              </div>

              <div className="mt-1 text-xs text-[#7e8983]">
                {description}
              </div>
            </div>
          ))}
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
                {prescriptionId || "—"}
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
          {/* OCR */}
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

          {/* MEDICINES */}
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
                {medicines.map(
                  (medicine, index) => (
                    <MedicineCard
                      key={`${medicine.name}-${index}`}
                      medicine={medicine}
                      index={index}
                    />
                  )
                )}
              </div>
            )}
          </div>
        </div>

        {/* SAFETY REVIEW */}
        <div className="mt-6 rounded-3xl border border-[#dce6df] bg-white p-6 shadow-[0_12px_40px_rgba(30,45,38,0.05)]">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
                Pharmacist review
              </div>

              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                Safety findings
              </h2>

              <p className="mt-2 max-w-2xl text-xs leading-5 text-[#7c8881]">
                Each finding is reviewed independently. Original
                AI findings remain preserved for auditability.
              </p>
            </div>

            <span className="rounded-full bg-[#fff7df] px-3 py-1.5 text-[10px] font-semibold text-[#8b6b2b]">
              {unresolvedFindingCount} unresolved
            </span>
          </div>

          {safetyFlags.length === 0 ? (
            <div className="mt-5 rounded-2xl bg-[#f3f7f4] p-5">
              <div className="text-sm font-semibold text-[#52635a]">
                No safety flags were returned.
              </div>

              <p className="mt-1 text-xs leading-5 text-[#7d8983]">
                This does not mean the prescription is clinically
                cleared. Professional review remains required.
              </p>
            </div>
          ) : (
            <div className="mt-5 space-y-3">
              {safetyFlags.map(
                (flag, index) => (
                  <FindingCard
                    key={`${flag.type}-${index}`}
                    flag={flag}
                    index={index}
                    resolvedAction={getLatestFindingAction(
                      index
                    )}
                    busy={actionLoading}
                    onAction={performFindingAction}
                  />
                )
              )}
            </div>
          )}
        </div>

        {/* AUDIT HISTORY */}
        <div className="mt-6 rounded-3xl border border-[#dce6df] bg-white p-6 shadow-[0_12px_40px_rgba(30,45,38,0.05)]">
          <div>
            <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[#929c97]">
              Audit trail
            </div>

            <h2 className="mt-2 text-xl font-semibold">
              Review history
            </h2>
          </div>

          {history?.audits &&
          history.audits.length > 0 ? (
            <div className="mt-5 space-y-3">
              {[...history.audits]
                .reverse()
                .map((audit) => (
                  <div
                    key={audit.id}
                    className="rounded-2xl border border-[#e3e9e5] bg-[#f9fbf9] p-4"
                  >
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-semibold text-[#526158]">
                          {formatAction(
                            audit.action
                          )}
                        </span>

                        {audit.finding_type && (
                          <span className="rounded-full border border-[#dce5df] bg-white px-2.5 py-1 text-[10px] text-[#718079]">
                            {audit.finding_type}
                          </span>
                        )}

                        {typeof audit.finding_data
                          ?.finding_index ===
                          "number" && (
                          <span className="text-[10px] text-[#8a948f]">
                            Finding #
                            {audit.finding_data
                              .finding_index + 1}
                          </span>
                        )}
                      </div>

                      <span className="text-[10px] text-[#8a948f]">
                        {formatTimestamp(
                          audit.created_at
                        )}
                      </span>
                    </div>

                    <div className="mt-3 text-xs text-[#7b8780]">
                      {formatReviewStatus(
                        audit.previous_status
                      )}{" "}
                      →{" "}
                      {formatReviewStatus(
                        audit.new_status
                      )}
                    </div>

                    {audit.note && (
                      <div className="mt-3 rounded-xl bg-white p-3 text-xs leading-5 text-[#69766f]">
                        {audit.note}
                      </div>
                    )}
                  </div>
                ))}
            </div>
          ) : (
            <div className="mt-5 rounded-2xl border border-dashed border-[#d4dfd8] bg-[#fafcfb] p-6 text-center text-xs text-[#87928c]">
              No pharmacist review actions have been recorded
              yet.
            </div>
          )}
        </div>

        {/* HUMAN REVIEW BANNER */}
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
                  AI-generated medicine and safety information is
                  supporting evidence. A qualified pharmacist
                  remains responsible for reviewing the original
                  prescription and recorded findings.
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