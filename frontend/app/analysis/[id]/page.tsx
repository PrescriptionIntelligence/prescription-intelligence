"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

// =========================================================
// Types
// =========================================================

type Medicine = {
  id: string;
  name: string;
  generic_name: string | null;
  brand_name: string | null;
  strength_value: string | number | null;
  strength_unit: string | null;
  dose_value: number | null;
  dose_unit: string | null;
  daily_dose_value: number | null;
  daily_dose_unit: string | null;
  route: string | null;
  frequency_value: number | null;
  frequency_unit: string | null;
  duration_value: number | null;
  duration_unit: string | null;
  instructions: string | null;
  extraction_confidence: number | null;
  normalization_confidence: number | null;
  needs_review: boolean | null;
  raw_text: string | null;
  status: string | null;
};

type SafetyFlag = {
  type: string;
  severity: string;
  medicine: string | null;
  message: string;

  matched_drugs?: string[];
  interaction_id?: string;
  interaction_category?: string;
  review_action?: string;
  evidence_source?: string;

  daily_dose?: number;
  daily_dose_unit?: string;
  limit?: number;
};

type Prescription = {
  id: string;
  prescription_id: string;
  raw_text: string | null;
  status: string;
  safety_flags: SafetyFlag[];
  file_name: string | null;
  file_path: string | null;
  file_type: string | null;
  created_at: string;
  updated_at: string | null;
  medicines: Medicine[];
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

// =========================================================
// Helpers
// =========================================================

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function confidencePercent(
  val: number | null | undefined
): string {
  if (val === null || val === undefined) {
    return "—";
  }

  return `${Math.round(val * 100)}%`;
}

function confidenceBarColor(
  val: number | null | undefined
): string {
  if (val === null || val === undefined) {
    return "bg-[#cfd8d3]";
  }

  if (val >= 0.85) {
    return "bg-[#3f7658]";
  }

  if (val >= 0.70) {
    return "bg-[#a47b2c]";
  }

  return "bg-[#a74646]";
}

function getOverallConfidence(
  medicine: Medicine
): number | null {
  const values = [
    medicine.extraction_confidence,
    medicine.normalization_confidence,
  ].filter(
    (value) =>
      value !== null &&
      value !== undefined
  ) as number[];

  if (values.length === 0) {
    return null;
  }

  return (
    values.reduce(
      (total, value) => total + value,
      0
    ) / values.length
  );
}

function severityStyle(
  severity: string
): {
  label: string;
  accent: string;
  border: string;
  background: string;
  text: string;
  iconBackground: string;
} {
  switch (severity) {
    case "high":
    case "error":
      return {
        label: "High Priority",
        accent: "bg-[#a83f3f]",
        border: "border-[#eccaca]",
        background: "bg-[#fff8f8]",
        text: "text-[#742525]",
        iconBackground: "bg-[#f8e4e4]",
      };

    case "warning":
      return {
        label: "Caution",
        accent: "bg-[#a27a28]",
        border: "border-[#eadbb0]",
        background: "bg-[#fffdf7]",
        text: "text-[#725719]",
        iconBackground: "bg-[#f7efd9]",
      };

    default:
      return {
        label: "Information",
        accent: "bg-[#536c86]",
        border: "border-[#d3deea]",
        background: "bg-[#f8fafc]",
        text: "text-[#3c536b]",
        iconBackground: "bg-[#e8eef5]",
      };
  }
}

function medicineStatusStyle(
  medicine: Medicine
): {
  label: string;
  cls: string;
  dot: string;
} {
  const confidence =
    getOverallConfidence(medicine);

  if (
    medicine.needs_review ||
    (medicine.status || "").toUpperCase() ===
      "UNKNOWN"
  ) {
    return {
      label: "Review required",
      cls: "bg-[#fff7df] text-[#705617] border-[#ebdcae]",
      dot: "bg-[#a47b2c]",
    };
  }

  if (
    confidence !== null &&
    confidence >= 0.85
  ) {
    return {
      label: "Verified",
      cls: "bg-[#edf8f1] text-[#2d6444] border-[#cce3d4]",
      dot: "bg-[#3f7658]",
    };
  }

  if (
    confidence !== null &&
    confidence >= 0.70
  ) {
    return {
      label: "Review",
      cls: "bg-[#fff5e8] text-[#795018] border-[#ecd8b8]",
      dot: "bg-[#b27b2b]",
    };
  }

  return {
    label: "Low confidence",
    cls: "bg-[#fff0f0] text-[#7b2929] border-[#eccaca]",
    dot: "bg-[#a74646]",
  };
}

function formatInteractionCategory(
  category: string
): string {
  return category
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}

function getImageUrl(
  filePath: string | null
): string | null {
  if (!filePath) {
    return null;
  }

  const fileName = filePath
    .split(/[\\/]/)
    .pop();

  if (!fileName) {
    return null;
  }

  return `${API_URL}/uploads/${fileName}`;
}

// =========================================================
// Component
// =========================================================

export default function AnalysisDetailPage() {
  const params = useParams();

  const prescriptionId =
    params?.id as string;

  const [prescription, setPrescription] =
    useState<Prescription | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [activeTab, setActiveTab] =
    useState<
      "medicines" | "safety" | "ocr"
    >("medicines");

  const [
    downloadingReport,
    setDownloadingReport,
  ] = useState(false);

  const [reportError, setReportError] =
    useState("");

  // -------------------------------------------------------
  // Download report
  // -------------------------------------------------------

  const handleDownloadReport =
    async () => {
      setDownloadingReport(true);
      setReportError("");

      try {
        const response = await fetch(
          `${API_URL}/prescriptions/${encodeURIComponent(
            prescriptionId
          )}/report`
        );

        if (!response.ok) {
          throw new Error(
            "Unable to generate the prescription report."
          );
        }

        const blob =
          await response.blob();

        const contentDisposition =
          response.headers.get(
            "content-disposition"
          );

        let fileName =
          `${prescriptionId}-prescription-intelligence-report.pdf`;

        const fileNameMatch =
          contentDisposition?.match(
            /filename="?([^"]+)"?/i
          );

        if (fileNameMatch?.[1]) {
          fileName =
            fileNameMatch[1];
        }

        const url =
          window.URL.createObjectURL(
            blob
          );

        const link =
          document.createElement("a");

        link.href = url;
        link.download = fileName;

        document.body.appendChild(link);

        link.click();

        link.remove();

        window.URL.revokeObjectURL(
          url
        );
      } catch (downloadError) {
        console.error(
          downloadError
        );

        setReportError(
          "Could not download the prescription report. Please try again."
        );
      } finally {
        setDownloadingReport(false);
      }
    };

  // -------------------------------------------------------
  // Load prescription
  // -------------------------------------------------------

  useEffect(() => {
    if (!prescriptionId) {
      return;
    }

    const cached =
      sessionStorage.getItem(
        "prescription_review"
      );

    if (cached) {
      try {
        const data = JSON.parse(cached);

        if (
          data.prescription_id ===
          prescriptionId
        ) {
          const rx: Prescription = {
            id:
              data.prescription_id,
            prescription_id:
              data.prescription_id,
            raw_text:
              data.raw_text,
            status:
              data.status,
            safety_flags:
              data.safety_flags || [],
            file_name:
              data.file_name,
            file_path:
              data.file_path,
            file_type:
              data.file_type,
            created_at:
              new Date().toISOString(),
            updated_at:
              null,
            medicines:
              data.medicines || [],
          };

          Promise.resolve().then(
            () => {
              setPrescription(rx);
              setLoading(false);
            }
          );

          return;
        }
      } catch {
        // Fall through to API fetch.
      }
    }

    fetch(
      `${API_URL}/prescriptions/${prescriptionId}`
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            "Prescription not found"
          );
        }

        return response.json();
      })
      .then((data) => {
        setPrescription(data);
      })
      .catch((fetchError) => {
        setError(
          fetchError instanceof Error
            ? fetchError.message
            : "Failed to load prescription"
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [prescriptionId]);

  // -------------------------------------------------------
  // Loading
  // -------------------------------------------------------

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f4f7f5] px-6">
        <div className="flex flex-col items-center">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#17211d] text-sm font-semibold text-white">
            Rx
          </div>

          <div className="mt-4 flex items-center gap-2 text-sm text-[#68766f]">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
            Loading analysis…
          </div>
        </div>
      </main>
    );
  }

  // -------------------------------------------------------
  // Error
  // -------------------------------------------------------

  if (error) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f4f7f5] px-6">
        <div className="w-full max-w-md rounded-2xl border border-[#e1e7e3] bg-white p-8 text-center shadow-[0_10px_35px_rgba(25,40,32,0.05)]">
          <div className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-[#fff0f0] text-sm text-[#8b4040]">
            !
          </div>

          <h1 className="mt-4 text-base font-semibold text-[#17211d]">
            Unable to load analysis
          </h1>

          <p className="mt-2 text-sm leading-6 text-[#7c8882]">
            {error}
          </p>

          <Link
            href="/history"
            className="mt-6 inline-flex rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#293830]"
          >
            ← Back to history
          </Link>
        </div>
      </main>
    );
  }

  if (!prescription) {
    return null;
  }

  // -------------------------------------------------------
  // Categorize findings
  // -------------------------------------------------------

  const OCR_FLAG_TYPES =
    new Set([
      "ocr_extraction_failed",
      "poor_ocr_quality",
    ]);

  const ocrFlags =
    prescription.safety_flags.filter(
      (flag) =>
        OCR_FLAG_TYPES.has(flag.type)
    );

  const medicationFlags =
    prescription.safety_flags.filter(
      (flag) =>
        !OCR_FLAG_TYPES.has(flag.type)
    );

  const highPriorityFlags =
    medicationFlags.filter(
      (flag) =>
        flag.severity === "high" ||
        flag.severity === "error"
    );

  const cautionFlags =
    medicationFlags.filter(
      (flag) =>
        flag.severity === "warning"
    );

  const infoFlags =
    medicationFlags.filter(
      (flag) =>
        flag.severity === "info" ||
        flag.severity === "informational"
    );

  const medicineReviewRequired =
    prescription.medicines.filter(
      (medicine) => {
        const confidence =
          getOverallConfidence(
            medicine
          );

        return (
          medicine.needs_review ||
          (confidence !== null &&
            confidence < 0.70)
        );
      }
    );

  const prescriptionSafetyReviewRequired =
    medicationFlags.some(
      (flag) =>
        flag.severity === "high" ||
        flag.severity === "error" ||
        flag.severity === "warning"
    );

  const needsReview =
    medicineReviewRequired.length > 0 ||
    prescriptionSafetyReviewRequired;

  const imageUrl = getImageUrl(
    prescription.file_path
  );

  const verifiedMedicines =
    prescription.medicines.filter(
      (medicine) => {
        const confidence =
          getOverallConfidence(
            medicine
          );

        return (
          !medicine.needs_review &&
          confidence !== null &&
          confidence >= 0.85
        );
      }
    ).length;

  const averageConfidence =
    prescription.medicines.length > 0
      ? prescription.medicines.reduce(
          (total, medicine) =>
            total +
            (getOverallConfidence(
              medicine
            ) ?? 0),
          0
        ) /
        prescription.medicines.length
      : null;

  const interactionFlags =
    medicationFlags.filter(
      (flag) =>
        flag.type ===
          "drug_interaction" ||
        Boolean(flag.interaction_id)
    );

  const statusLabel = needsReview
    ? "Review Required"
    : "Analysis Complete";

  // -------------------------------------------------------
  // Render
  // -------------------------------------------------------

  return (
    <main className="min-h-screen bg-[#f4f7f5] text-[#17211d]">

      {/* ===================================================
          Header
      =================================================== */}

      <header className="sticky top-0 z-30 border-b border-[#e1e7e3] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-5 py-3.5 sm:px-8">

          <Link
            href="/"
            className="flex items-center gap-3"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-[11px] font-semibold text-white shadow-sm">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold tracking-[-0.01em]">
                Prescription Intelligence
              </div>

              <div className="hidden text-[10px] text-[#8a948f] sm:block">
                Medication safety decision support
              </div>
            </div>
          </Link>

          <nav className="flex items-center gap-1">
            <Link
              href="/dashboard"
              className="rounded-lg px-3 py-2 text-xs font-medium text-[#68766f] transition hover:bg-[#f2f5f3] hover:text-[#17211d]"
            >
              Dashboard
            </Link>

            <Link
              href="/history"
              className="rounded-lg px-3 py-2 text-xs font-medium text-[#68766f] transition hover:bg-[#f2f5f3] hover:text-[#17211d]"
            >
              History
            </Link>
          </nav>
        </div>
      </header>

      {/* ===================================================
          Page
      =================================================== */}

      <div className="mx-auto max-w-[1440px] px-5 py-6 sm:px-8 sm:py-8">

        {/* Breadcrumb */}

        <div className="mb-5 flex items-center gap-2 text-[11px] text-[#8b9690]">
          <Link
            href="/history"
            className="transition hover:text-[#17211d]"
          >
            History
          </Link>

          <span>/</span>

          <span className="font-mono text-[#4d5b53]">
            {prescription.prescription_id}
          </span>
        </div>

        {/* =================================================
            Hero
        ================================================= */}

        <section className="mb-6 overflow-hidden rounded-3xl border border-[#dfe6e1] bg-white shadow-[0_8px_35px_rgba(28,46,36,0.04)]">

          <div className="p-5 sm:p-7">

            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">

              <div className="min-w-0">

                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-[#f0f4f1] px-2 py-1 font-mono text-[10px] font-medium text-[#52645a]">
                    {prescription.prescription_id}
                  </span>

                  <span className="text-[11px] text-[#9aa39e]">
                    {formatDate(
                      prescription.created_at
                    )}
                  </span>
                </div>

                <h1 className="mt-3 text-2xl font-semibold tracking-[-0.035em] sm:text-[30px]">
                  Prescription analysis
                </h1>

                <p className="mt-1.5 max-w-2xl text-sm leading-6 text-[#7a8780]">
                  AI-assisted extraction and
                  medication safety review for{" "}
                  <span className="font-medium text-[#526057]">
                    {prescription.file_name ||
                      "uploaded prescription"}
                  </span>
                  .
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">

                <span
                  className={
                    needsReview
                      ? "inline-flex items-center gap-2 rounded-full border border-[#ead9aa] bg-[#fff9e8] px-3 py-2 text-[11px] font-semibold text-[#725719]"
                      : "inline-flex items-center gap-2 rounded-full border border-[#cbe0d3] bg-[#eff9f2] px-3 py-2 text-[11px] font-semibold text-[#2d6444]"
                  }
                >
                  <span
                    className={
                      needsReview
                        ? "h-1.5 w-1.5 rounded-full bg-[#a47b2c]"
                        : "h-1.5 w-1.5 rounded-full bg-[#3f7658]"
                    }
                  />

                  {statusLabel}
                </span>

                <button
                  type="button"
                  onClick={
                    handleDownloadReport
                  }
                  disabled={
                    downloadingReport
                  }
                  className="inline-flex items-center gap-2 rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-[#293830] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {downloadingReport ? (
                    <>
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      Generating…
                    </>
                  ) : (
                    <>
                      <span className="text-sm leading-none">
                        ↓
                      </span>
                      Download report
                    </>
                  )}
                </button>
              </div>
            </div>

            {reportError && (
              <div className="mt-4 rounded-xl border border-[#eccaca] bg-[#fff7f7] px-4 py-3 text-xs text-[#8b4040]">
                {reportError}
              </div>
            )}
          </div>

          {/* Review banner */}

          {needsReview && (
            <div className="border-t border-[#eadfbd] bg-[#fffaf0] px-5 py-3.5 sm:px-7">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#f5e9c8] text-xs font-bold text-[#775d1e]">
                  !
                </div>

                <div>
                  <p className="text-xs font-semibold text-[#665018]">
                    Human review recommended
                  </p>

                  <p className="mt-0.5 text-[11px] leading-5 text-[#85733e]">
                    This analysis contains one or
                    more findings that require
                    verification by a qualified
                    healthcare professional before
                    dispensing or clinical use.
                  </p>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* =================================================
            Key metrics
        ================================================= */}

        <section className="mb-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">

          <MetricCard
            label="Medicines detected"
            value={String(
              prescription.medicines.length
            )}
            detail={
              verifiedMedicines > 0
                ? `${verifiedMedicines} verified`
                : "No verified medicines"
            }
            icon="Rx"
          />

          <MetricCard
            label="Safety findings"
            value={String(
              medicationFlags.length
            )}
            detail={
              highPriorityFlags.length > 0
                ? `${highPriorityFlags.length} high priority`
                : "No high-priority findings"
            }
            icon="!"
            emphasis={
              highPriorityFlags.length > 0
                ? "danger"
                : "neutral"
            }
          />

          <MetricCard
            label="Analysis confidence"
            value={
              averageConfidence !== null
                ? `${Math.round(
                    averageConfidence * 100
                  )}%`
                : "—"
            }
            detail="Average medicine confidence"
            icon="✓"
          />

          <MetricCard
            label="Drug interactions"
            value={String(
              interactionFlags.length
            )}
            detail={
              interactionFlags.length > 0
                ? "Review recommended"
                : "None detected"
            }
            icon="↔"
            emphasis={
              interactionFlags.length > 0
                ? "danger"
                : "neutral"
            }
          />
        </section>

        {/* =================================================
            Main workspace
        ================================================= */}

        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">

          {/* =================================================
              Left rail
          ================================================= */}

          <aside className="space-y-5">

            {/* Prescription image */}

            {imageUrl && (
              <section className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

                <div className="flex items-center justify-between border-b border-[#edf0ee] px-4 py-3.5">
                  <div>
                    <p className="text-xs font-semibold text-[#344139]">
                      Source prescription
                    </p>

                    <p className="mt-0.5 text-[10px] text-[#9aa39e]">
                      Original uploaded image
                    </p>
                  </div>

                  <span className="rounded-md bg-[#f3f6f4] px-2 py-1 text-[9px] font-medium uppercase tracking-[0.1em] text-[#758078]">
                    Source
                  </span>
                </div>

                <div className="bg-[#f1f3f1] p-3">
                  <div className="flex min-h-[300px] items-center justify-center overflow-hidden rounded-xl border border-[#e2e7e3] bg-white">
                    <img
                      src={imageUrl}
                      alt="Prescription"
                      className="max-h-[520px] w-full object-contain"
                      onError={(event) => {
                        (
                          event.target as HTMLImageElement
                        ).style.display =
                          "none";
                      }}
                    />
                  </div>
                </div>
              </section>
            )}

            {/* Analysis summary */}

            <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-[#344139]">
                    Analysis summary
                  </p>

                  <p className="mt-0.5 text-[10px] text-[#9aa39e]">
                    Current prescription state
                  </p>
                </div>

                <span
                  className={
                    needsReview
                      ? "rounded-full bg-[#fff7df] px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.08em] text-[#73591b]"
                      : "rounded-full bg-[#edf8f1] px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.08em] text-[#2d6444]"
                  }
                >
                  {needsReview
                    ? "Review"
                    : "Clear"}
                </span>
              </div>

              <div className="mt-5 divide-y divide-[#edf0ee]">
                <SummaryRow
                  label="Medicines extracted"
                  value={String(
                    prescription.medicines.length
                  )}
                />

                <SummaryRow
                  label="Safety findings"
                  value={String(
                    medicationFlags.length
                  )}
                />

                {ocrFlags.length > 0 && (
                  <SummaryRow
                    label="OCR / extraction"
                    value={String(
                      ocrFlags.length
                    )}
                  />
                )}

                <SummaryRow
                  label="Needs review"
                  value={
                    needsReview
                      ? "Yes"
                      : "No"
                  }
                  valueClassName={
                    needsReview
                      ? "text-[#8a641d]"
                      : "text-[#2d6444]"
                  }
                />

                <SummaryRow
                  label="Analysis status"
                  value={
                    prescription.status
                  }
                />
              </div>
            </section>

            {/* Safety snapshot */}

            <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

              <p className="text-xs font-semibold text-[#344139]">
                Safety snapshot
              </p>

              <div className="mt-4 space-y-2.5">

                <SafetySnapshotRow
                  label="High priority"
                  value={
                    highPriorityFlags.length
                  }
                  tone={
                    highPriorityFlags.length >
                    0
                      ? "danger"
                      : "neutral"
                  }
                />

                <SafetySnapshotRow
                  label="Caution"
                  value={
                    cautionFlags.length
                  }
                  tone={
                    cautionFlags.length > 0
                      ? "warning"
                      : "neutral"
                  }
                />

                <SafetySnapshotRow
                  label="Informational"
                  value={
                    infoFlags.length
                  }
                  tone="neutral"
                />

                <SafetySnapshotRow
                  label="Interactions"
                  value={
                    interactionFlags.length
                  }
                  tone={
                    interactionFlags.length >
                    0
                      ? "danger"
                      : "neutral"
                  }
                />
              </div>

              {medicationFlags.length >
                0 && (
                <button
                  type="button"
                  onClick={() =>
                    setActiveTab("safety")
                  }
                  className="mt-4 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-3 py-2.5 text-[11px] font-medium text-[#526158] transition hover:bg-[#f2f6f3] hover:text-[#17211d]"
                >
                  View safety findings →
                </button>
              )}
            </section>
          </aside>

          {/* =================================================
              Main content
          ================================================= */}

          <section className="min-w-0">

            {/* Tabs */}

            <div className="mb-5 flex overflow-x-auto rounded-2xl border border-[#dfe6e1] bg-white p-1 shadow-[0_5px_25px_rgba(28,46,36,0.025)]">

              {(
                [
                  "medicines",
                  "safety",
                  "ocr",
                ] as const
              ).map((tab) => {

                const count =
                  tab === "medicines"
                    ? prescription
                        .medicines
                        .length
                    : tab === "safety"
                    ? medicationFlags.length
                    : null;

                const active =
                  activeTab === tab;

                return (
                  <button
                    key={tab}
                    type="button"
                    onClick={() =>
                      setActiveTab(tab)
                    }
                    className={
                      active
                        ? "flex min-w-[120px] flex-1 items-center justify-center gap-2 rounded-xl bg-[#17211d] px-4 py-3 text-[11px] font-semibold text-white shadow-sm transition"
                        : "flex min-w-[120px] flex-1 items-center justify-center gap-2 rounded-xl px-4 py-3 text-[11px] font-medium text-[#748079] transition hover:bg-[#f2f5f3] hover:text-[#26332c]"
                    }
                  >
                    <span>
                      {tab === "medicines"
                        ? "Medicines"
                        : tab === "safety"
                        ? "Safety"
                        : "OCR text"}
                    </span>

                    {count !== null && (
                      <span
                        className={
                          active
                            ? "rounded-full bg-white/15 px-1.5 py-0.5 text-[9px]"
                            : "rounded-full bg-[#edf1ee] px-1.5 py-0.5 text-[9px] text-[#69756e]"
                        }
                      >
                        {count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* =================================================
                Medicines
            ================================================= */}

            {activeTab ===
              "medicines" && (
              <div className="space-y-4">

                {prescription.medicines
                  .length === 0 ? (
                  <EmptyState
                    icon="Rx"
                    title="No medicines extracted"
                    description="The system could not identify medicines from this prescription. Verify the image and try again."
                  />
                ) : (
                  prescription.medicines.map(
                    (
                      medicine,
                      index
                    ) => (
                      <MedicineCard
                        key={`${medicine.id ?? "medicine"}-${index}`}
                        medicine={medicine}
                      />
                    )
                  )
                )}
              </div>
            )}

            {/* =================================================
                Safety
            ================================================= */}

            {activeTab === "safety" && (
              <div className="space-y-5">

                {ocrFlags.length > 0 && (
                  <section>
                    <SectionHeading
                      title="OCR & extraction"
                      description="Issues detected while reading the prescription."
                    />

                    <div className="space-y-3">
                      {ocrFlags.map(
                        (flag, index) => (
                          <OcrFlagCard
                            key={index}
                            flag={flag}
                          />
                        )
                      )}
                    </div>
                  </section>
                )}

                {medicationFlags.length ===
                0 ? (
                  <EmptySafetyState />
                ) : (
                  <>

                    {highPriorityFlags.length >
                      0 && (
                      <section>
                        <SectionHeading
                          title="High priority"
                          description="Findings that should be reviewed before proceeding."
                          tone="danger"
                        />

                        <div className="space-y-3">
                          {highPriorityFlags.map(
                            (
                              flag,
                              index
                            ) => (
                              <SafetyFlagCard
                                key={index}
                                flag={flag}
                              />
                            )
                          )}
                        </div>
                      </section>
                    )}

                    {cautionFlags.length >
                      0 && (
                      <section>
                        <SectionHeading
                          title="Caution & review"
                          description="Potential concerns requiring professional verification."
                          tone="warning"
                        />

                        <div className="space-y-3">
                          {cautionFlags.map(
                            (
                              flag,
                              index
                            ) => (
                              <SafetyFlagCard
                                key={index}
                                flag={flag}
                              />
                            )
                          )}
                        </div>
                      </section>
                    )}

                    {infoFlags.length >
                      0 && (
                      <section>
                        <SectionHeading
                          title="Informational"
                          description="Additional findings from the safety analysis."
                        />

                        <div className="space-y-3">
                          {infoFlags.map(
                            (
                              flag,
                              index
                            ) => (
                              <SafetyFlagCard
                                key={index}
                                flag={flag}
                              />
                            )
                          )}
                        </div>
                      </section>
                    )}
                  </>
                )}

                <MedicalDisclaimer />
              </div>
            )}

            {/* =================================================
                OCR
            ================================================= */}

            {activeTab === "ocr" && (
              <div className="space-y-4">

                <section className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

                  <div className="flex flex-col gap-2 border-b border-[#edf0ee] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold text-[#344139]">
                        Extracted prescription text
                      </p>

                      <p className="mt-0.5 text-[10px] text-[#9aa39e]">
                        Raw text returned by the OCR pipeline
                      </p>
                    </div>

                    <span className="rounded-md bg-[#f2f5f3] px-2 py-1 font-mono text-[9px] text-[#7c8881]">
                      OCR
                    </span>
                  </div>

                  <div className="p-5">

                    {prescription.raw_text ? (
                      <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-[#e5eae7] bg-[#fafcfb] p-5 font-mono text-[11px] leading-6 text-[#3c4942]">
                        {
                          prescription.raw_text
                        }
                      </pre>
                    ) : (
                      <EmptyState
                        icon="OCR"
                        title="No OCR text available"
                        description="The prescription did not return readable OCR text."
                      />
                    )}
                  </div>
                </section>

                <div className="rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 py-3 text-[10px] leading-5 text-[#7c8881]">
                  OCR output is provided for
                  transparency and verification.
                  Extracted text may contain
                  recognition errors and should
                  always be checked against the
                  original prescription image.
                </div>
              </div>
            )}
          </section>
        </div>

        {/* =================================================
            Footer disclaimer
        ================================================= */}

        <div className="mt-8 border-t border-[#dfe6e1] pt-5">
          <p className="text-center text-[10px] leading-5 text-[#9aa39e]">
            Prescription Intelligence provides
            AI-generated decision support only.
            It does not diagnose conditions,
            prescribe medicines, or replace
            professional clinical judgment.
          </p>
        </div>
      </div>
    </main>
  );
}

// =========================================================
// Metric card
// =========================================================

function MetricCard({
  label,
  value,
  detail,
  icon,
  emphasis = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  icon: string;
  emphasis?: "neutral" | "danger";
}) {
  return (
    <div className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.03)]">

      <div className="flex items-start justify-between gap-3">

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[#8b9690]">
            {label}
          </p>

          <p
            className={
              emphasis === "danger"
                ? "mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#842f2f]"
                : "mt-2 text-2xl font-semibold tracking-[-0.03em] text-[#17211d]"
            }
          >
            {value}
          </p>

          <p className="mt-1 text-[10px] text-[#8b9690]">
            {detail}
          </p>
        </div>

        <div
          className={
            emphasis === "danger"
              ? "grid h-8 w-8 place-items-center rounded-lg bg-[#fff0f0] text-[11px] font-semibold text-[#8a3434]"
              : "grid h-8 w-8 place-items-center rounded-lg bg-[#f0f4f1] text-[10px] font-semibold text-[#53645a]"
          }
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// =========================================================
// Summary row
// =========================================================

function SummaryRow({
  label,
  value,
  valueClassName = "text-[#27332d]",
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-[11px] text-[#89948e]">
        {label}
      </dt>

      <dd
        className={`text-right text-[11px] font-semibold ${valueClassName}`}
      >
        {value}
      </dd>
    </div>
  );
}

// =========================================================
// Safety snapshot row
// =========================================================

function SafetySnapshotRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone:
    | "danger"
    | "warning"
    | "neutral";
}) {
  const valueClass =
    tone === "danger"
      ? "bg-[#fff0f0] text-[#8a3434]"
      : tone === "warning"
      ? "bg-[#fff7df] text-[#725719]"
      : "bg-[#f1f4f2] text-[#58655e]";

  return (
    <div className="flex items-center justify-between rounded-xl border border-[#edf0ee] px-3 py-2.5">
      <span className="text-[10px] text-[#6e7b73]">
        {label}
      </span>

      <span
        className={`min-w-6 rounded-md px-1.5 py-1 text-center text-[10px] font-semibold ${valueClass}`}
      >
        {value}
      </span>
    </div>
  );
}

// =========================================================
// Section heading
// =========================================================

function SectionHeading({
  title,
  description,
  tone = "neutral",
}: {
  title: string;
  description: string;
  tone?: "neutral" | "danger" | "warning";
}) {
  const titleClass =
    tone === "danger"
      ? "text-[#812f2f]"
      : tone === "warning"
      ? "text-[#715719]"
      : "text-[#344139]";

  return (
    <div className="mb-3">
      <h2
        className={`text-[11px] font-semibold uppercase tracking-[0.14em] ${titleClass}`}
      >
        {title}
      </h2>

      <p className="mt-1 text-[11px] text-[#8b9690]">
        {description}
      </p>
    </div>
  );
}

// =========================================================
// Medicine card
// =========================================================

function MedicineCard({
  medicine,
}: {
  medicine: Medicine;
}) {
  const status =
    medicineStatusStyle(
      medicine
    );

  const confidence =
    getOverallConfidence(
      medicine
    );

  return (
    <article className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

      {/* Medicine header */}

      <div className="border-b border-[#edf0ee] px-5 py-5 sm:px-6">

        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">

          <div className="min-w-0">

            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#edf3ef] text-[10px] font-semibold text-[#3e5c4b]">
                Rx
              </span>

              <div>
                <h3 className="text-base font-semibold tracking-[-0.015em] text-[#1c2821]">
                  {medicine.generic_name ||
                    medicine.name}
                </h3>

                {medicine.brand_name &&
                  medicine.brand_name !==
                    medicine.generic_name && (
                    <p className="mt-0.5 text-[10px] text-[#8b9690]">
                      Brand:{" "}
                      {medicine.brand_name}
                    </p>
                  )}
              </div>
            </div>

            {medicine.raw_text && (
              <div className="mt-3 rounded-lg bg-[#fafcfb] px-3 py-2">
                <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[#a0aaa5]">
                  OCR
                </span>

                <p className="mt-1 font-mono text-[10px] leading-5 text-[#6e7973]">
                  “{medicine.raw_text}”
                </p>
              </div>
            )}
          </div>

          <span
            className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[9px] font-semibold ${status.cls}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${status.dot}`}
            />

            {status.label}
          </span>
        </div>
      </div>

      {/* Details */}

      <div className="px-5 py-5 sm:px-6">

        <div className="grid gap-px overflow-hidden rounded-xl border border-[#e7ece9] bg-[#e7ece9] sm:grid-cols-2 lg:grid-cols-3">

          <MedDetail
            label="Strength"
            value={
              medicine.strength_value !=
              null
                ? `${medicine.strength_value}${
                    medicine.strength_unit
                      ? ` ${medicine.strength_unit}`
                      : ""
                  }`
                : null
            }
          />

          <MedDetail
            label="Dose"
            value={
              medicine.dose_value !=
              null
                ? `${medicine.dose_value}${
                    medicine.dose_unit
                      ? ` ${medicine.dose_unit}`
                      : ""
                  }`
                : null
            }
          />

          <MedDetail
            label="Route"
            value={medicine.route}
          />

          <MedDetail
            label="Frequency"
            value={
              medicine.frequency_value !=
              null
                ? `${medicine.frequency_value}×/${
                    medicine.frequency_unit ||
                    "day"
                  }`
                : null
            }
          />

          <MedDetail
            label="Duration"
            value={
              medicine.duration_value !=
              null
                ? `${medicine.duration_value} ${
                    medicine.duration_unit ||
                    "days"
                  }`
                : null
            }
          />

          <MedDetail
            label="Daily dose"
            value={
              medicine.daily_dose_value !=
              null
                ? `${medicine.daily_dose_value} ${
                    medicine.daily_dose_unit ||
                    "mg"
                  }`
                : null
            }
          />
        </div>

        {medicine.instructions && (
          <div className="mt-4 rounded-xl border border-[#dfe9e2] bg-[#f6faf7] px-4 py-3">
            <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[#718078]">
              Instructions
            </p>

            <p className="mt-1 text-[11px] leading-5 text-[#526158]">
              {medicine.instructions}
            </p>
          </div>
        )}

        {/* Confidence */}

        <div className="mt-5">

          <div className="mb-3 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#89948e]">
              Extraction confidence
            </p>

            <span className="text-[10px] font-semibold text-[#4d5d54]">
              {confidencePercent(
                medicine.extraction_confidence
              )}
            </span>
          </div>

          <ConfidenceBar
            value={
              medicine.extraction_confidence
            }
          />

          <div className="mt-4 mb-3 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[#89948e]">
              Normalization confidence
            </p>

            <span className="text-[10px] font-semibold text-[#4d5d54]">
              {confidencePercent(
                medicine.normalization_confidence
              )}
            </span>
          </div>

          <ConfidenceBar
            value={
              medicine.normalization_confidence
            }
          />
        </div>

        {confidence !== null && (
          <div className="mt-4 flex items-center justify-between rounded-xl bg-[#fafcfb] px-3 py-2.5">
            <span className="text-[10px] text-[#8b9690]">
              Combined confidence
            </span>

            <span className="text-[11px] font-semibold text-[#33423a]">
              {Math.round(
                confidence * 100
              )}
              %
            </span>
          </div>
        )}
      </div>
    </article>
  );
}

// =========================================================
// Medicine detail
// =========================================================

function MedDetail({
  label,
  value,
}: {
  label: string;
  value:
    | string
    | null
    | undefined;
}) {
  return (
    <div className="bg-white px-3.5 py-3.5">
      <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#9aa39e]">
        {label}
      </p>

      <p className="mt-1 text-[11px] font-semibold text-[#35423b]">
        {value ?? "—"}
      </p>
    </div>
  );
}

// =========================================================
// Confidence bar
// =========================================================

function ConfidenceBar({
  value,
}: {
  value:
    | number
    | null
    | undefined;
}) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-[#e7ece9]">
      <div
        className={`h-full rounded-full transition-all ${confidenceBarColor(
          value
        )}`}
        style={{
          width:
            value !== null &&
            value !== undefined
              ? `${Math.max(
                  0,
                  Math.min(
                    value * 100,
                    100
                  )
                )}%`
              : "0%",
        }}
      />
    </div>
  );
}

// =========================================================
// OCR flag card
// =========================================================

function OcrFlagCard({
  flag,
}: {
  flag: SafetyFlag;
}) {
  return (
    <div className="rounded-2xl border border-[#d4deea] bg-[#f8fafc] p-5">
      <div className="flex items-start gap-3">

        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#e8eef5] text-[9px] font-bold text-[#4c6077]">
          OCR
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-semibold text-[#34485d]">
              {flag.message}
            </p>

            <span className="rounded-full bg-[#e7edf4] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#53677e]">
              Extraction
            </span>
          </div>

          {flag.medicine && (
            <p className="mt-2 text-[10px] text-[#748397]">
              Related text:{" "}
              <span className="font-mono">
                {flag.medicine}
              </span>
            </p>
          )}

          <p className="mt-2 text-[10px] leading-5 text-[#788696]">
            Verify this finding against the
            original prescription image and
            manually confirm the extracted
            information.
          </p>
        </div>
      </div>
    </div>
  );
}

// =========================================================
// Safety flag card
// =========================================================

function SafetyFlagCard({
  flag,
}: {
  flag: SafetyFlag;
}) {
  const style =
    severityStyle(flag.severity);

  const isInteraction =
    flag.type ===
      "drug_interaction" ||
    Boolean(flag.interaction_id);

  const matchedDrugs =
    flag.matched_drugs?.filter(
      Boolean
    ) ?? [];

  return (
    <article
      className={`relative overflow-hidden rounded-2xl border ${style.border} ${style.background} shadow-[0_4px_20px_rgba(40,35,30,0.025)]`}
    >

      <div
        className={`absolute inset-y-0 left-0 w-1 ${style.accent}`}
      />

      <div className="p-5 pl-6">

        <div className="flex items-start gap-3">

          <div
            className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${style.iconBackground} ${style.text} text-xs font-bold`}
          >
            {isInteraction
              ? "↔"
              : flag.severity ===
                "warning"
              ? "!"
              : "i"}
          </div>

          <div className="min-w-0 flex-1">

            <div className="flex flex-wrap items-center gap-2">

              <span
                className={`text-[10px] font-bold uppercase tracking-[0.08em] ${style.text}`}
              >
                {style.label}
              </span>

              {isInteraction && (
                <span className="rounded-full border border-current/10 bg-white/60 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide">
                  Drug interaction
                </span>
              )}

              {flag.medicine && (
                <span className="ml-auto font-mono text-[9px] opacity-60">
                  {flag.medicine}
                </span>
              )}
            </div>

            {isInteraction &&
              matchedDrugs.length >
                0 && (
                <div className="mt-4">

                  <p className="text-[9px] font-semibold uppercase tracking-[0.1em] opacity-60">
                    Matched medicines
                  </p>

                  <div className="mt-1.5 rounded-xl border border-current/10 bg-white/65 px-3.5 py-3 font-mono text-[10px] font-medium">
                    {matchedDrugs.join(
                      " + "
                    )}
                  </div>
                </div>
              )}

            <p className="mt-4 text-xs leading-6">
              {flag.message}
            </p>

            {isInteraction &&
              flag.interaction_category && (
                <div className="mt-4 flex flex-wrap items-center gap-2 text-[10px]">
                  <span className="font-semibold opacity-70">
                    Risk category
                  </span>

                  <span className="rounded-md bg-white/60 px-2 py-1 font-medium">
                    {formatInteractionCategory(
                      flag.interaction_category
                    )}
                  </span>
                </div>
              )}

            {isInteraction &&
              flag.review_action && (
                <div className="mt-4 rounded-xl border border-current/10 bg-white/50 p-4">
                  <p className="text-[9px] font-semibold uppercase tracking-[0.1em] opacity-65">
                    Recommended action
                  </p>

                  <p className="mt-1.5 text-[10px] leading-5">
                    {flag.review_action}
                  </p>
                </div>
              )}

            {isInteraction &&
              flag.evidence_source && (
                <p className="mt-4 text-[9px] opacity-60">
                  Evidence:{" "}
                  {flag.evidence_source}
                </p>
              )}

            {flag.interaction_id && (
              <p className="mt-2 font-mono text-[8px] opacity-40">
                Reference:{" "}
                {flag.interaction_id}
              </p>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

// =========================================================
// Empty state
// =========================================================

function EmptyState({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-[#d8e1dc] bg-white px-8 py-14 text-center">
      <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-[#f0f4f1] text-[10px] font-semibold text-[#5b6b62]">
        {icon}
      </div>

      <h3 className="mt-4 text-sm font-semibold text-[#344139]">
        {title}
      </h3>

      <p className="mx-auto mt-2 max-w-md text-[11px] leading-5 text-[#89948e]">
        {description}
      </p>
    </div>
  );
}

// =========================================================
// Empty safety
// =========================================================

function EmptySafetyState() {
  return (
    <div className="rounded-2xl border border-[#cde1d4] bg-[#f2faf5] px-8 py-14 text-center">

      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-[#dcefe2] text-base font-semibold text-[#367050]">
        ✓
      </div>

      <h3 className="mt-4 text-sm font-semibold text-[#2d6042]">
        No medication safety flags detected
      </h3>

      <p className="mx-auto mt-2 max-w-lg text-[11px] leading-5 text-[#688172]">
        No configured medication safety
        concerns were identified by the
        current analysis.
      </p>

      <p className="mx-auto mt-3 max-w-lg text-[10px] leading-5 text-[#82968a]">
        Professional verification is still
        required before dispensing or clinical
        use.
      </p>
    </div>
  );
}

// =========================================================
// Medical disclaimer
// =========================================================

function MedicalDisclaimer() {
  return (
    <div className="rounded-2xl border border-[#dfe6e1] bg-[#fafcfb] p-4 text-[10px] leading-5 text-[#77847d]">
      <span className="font-semibold text-[#5e6b64]">
        Medical disclaimer:
      </span>{" "}
      Safety checks are decision-support
      tools only. They are based on a limited,
      curated reference set and do not replace
      clinical judgment. Always verify safety
      information independently before
      dispensing.
    </div>
  );
}