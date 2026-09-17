"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authFetch, getUser, isAuthenticated } from "@/lib/auth";

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
  prescription_strength?: string | null;
  reference_strength?: string | null;
  resolution_reason?: string | null;
};

type Prescription = {
  id: string;
  prescription_id: string;
  raw_text: string | null;
  status: string;
  safety_flags: SafetyFlag[];
  file_name: string | null;
  file_type: string | null;
  /** True when an image is available via the authenticated image endpoint. */
  has_image: boolean;
  created_at: string;
  updated_at: string | null;
  medicines: Medicine[];
};

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

function confidencePercent(value: number | null) {
  if (value === null || value === undefined) return "—";

  const normalized = value <= 1 ? value * 100 : value;

  return `${Math.round(normalized)}%`;
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

function isMedicineVerified(medicine: Medicine): boolean {
  const confidence = getOverallConfidence(medicine);

  return (
    !medicine.needs_review &&
    confidence !== null &&
    confidence >= 0.85
  );
}

function severityStyle(severity: string) {
  const normalized = severity.toLowerCase();

  if (normalized === "high" || normalized === "error") {
    return {
      label: "High priority",
      badge: "border border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]",
      iconBackground:
        "border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]",
    };
  }

  if (normalized === "medium" || normalized === "warning") {
    return {
      label: "Caution",
      badge: "border border-[#E5D4A8] bg-[#FFF7DF] text-[#A47B2C]",
      iconBackground:
        "border-[#E5D4A8] bg-[#FFF7DF] text-[#A47B2C]",
    };
  }

  return {
    label: "Informational",
    badge: "border border-[#DFE6E1] bg-[#F5F8F6] text-[#526158]",
    iconBackground:
      "border-[#DFE6E1] bg-[#F5F8F6] text-[#526158]",
  };
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

// =========================================================
// Component
// =========================================================

export default function AnalysisDetailPage() {
  const params = useParams();
  const router = useRouter();

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

  const [imageObjectUrl, setImageObjectUrl] =
    useState<string | null>(null);

  const [reportError, setReportError] =
    useState("");

  // -------------------------------------------------------
  // Customer assignment state
  // -------------------------------------------------------

  const [assignedCustomer, setAssignedCustomer] = useState<{
    id: string;
    name: string;
    customer_code: string;
  } | null>(null);
  const [showAssign, setShowAssign] = useState(false);
  const [assignSearch, setAssignSearch] = useState("");
  const [assignResults, setAssignResults] = useState<
    { id: string; name: string; customer_code: string; phone: string | null }[]
  >([]);
  const [assignSearching, setAssignSearching] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState("");
  const [assignSuccess, setAssignSuccess] = useState("");
  const assignSearchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // -------------------------------------------------------
  // Download report
  // -------------------------------------------------------

  const handleDownloadReport =
    async () => {
      setDownloadingReport(true);
      setReportError("");

      try {
        const response = await authFetch(
          `/prescriptions/${encodeURIComponent(
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
  // Customer assignment
  // -------------------------------------------------------

  const isPharmacistUser = getUser()?.role === "pharmacist";

  async function handleAssignSearch(query: string) {
    setAssignSearch(query);
    if (assignSearchRef.current) clearTimeout(assignSearchRef.current);
    if (!query.trim()) {
      setAssignResults([]);
      return;
    }
    assignSearchRef.current = setTimeout(async () => {
      setAssignSearching(true);
      try {
        const response = await authFetch(
          `/customers/search?q=${encodeURIComponent(query.trim())}`
        );
        if (response.ok) {
          const data = await response.json();
          setAssignResults(data);
        }
      } catch {
        setAssignResults([]);
      } finally {
        setAssignSearching(false);
      }
    }, 300);
  }

  async function handleAssignCustomer(
    event: FormEvent<HTMLFormElement>,
    customerId: string,
    customerName: string,
    customerCode: string
  ) {
    event.preventDefault();
    setAssigning(true);
    setAssignError("");
    setAssignSuccess("");
    try {
      const response = await authFetch(
        `/prescriptions/${encodeURIComponent(prescriptionId)}/customer`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ customer_id: customerId }),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Failed to assign customer"
        );
      }
      setAssignedCustomer({ id: customerId, name: customerName, customer_code: customerCode });
      setAssignSuccess(`Assigned to ${customerName}`);
      setShowAssign(false);
      setAssignSearch("");
      setAssignResults([]);
      setTimeout(() => setAssignSuccess(""), 3000);
    } catch (err) {
      setAssignError(err instanceof Error ? err.message : "Failed to assign customer");
    } finally {
      setAssigning(false);
    }
  }

  // -------------------------------------------------------
  // Open pharmacist review
  // -------------------------------------------------------

  const handleReviewPrescription = () => {
    if (!prescription) {
      return;
    }

    sessionStorage.setItem(
      "prescription_review",
      JSON.stringify(prescription)
    );

    sessionStorage.setItem(
      "prescription_file_name",
      prescription.file_name ||
        "uploaded prescription"
    );

    window.location.href = "/review";
  };

  // -------------------------------------------------------
  // Load prescription
  // -------------------------------------------------------

  // Auth guard: redirect unauthenticated users to sign-in
  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
    }
  }, [router]);

  useEffect(() => {
    if (!prescriptionId) {
      return;
    }

    // Second-layer auth check before API call
    if (!isAuthenticated()) {
      router.replace("/sign-in");
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
            file_type:
              data.file_type,
            has_image:
              Boolean(data.has_image),
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

    authFetch(
      `/prescriptions/${encodeURIComponent(
        prescriptionId
      )}`
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
  // Load prescription image (authenticated)
  // -------------------------------------------------------

  useEffect(() => {
    if (!prescriptionId || !prescription?.has_image) {
      return;
    }

    let objectUrl: string | null = null;

    authFetch(
      `/prescriptions/${encodeURIComponent(prescriptionId)}/image`
    )
      .then((response) => {
        if (!response.ok) {
          return null;
        }
        return response.blob();
      })
      .then((blob) => {
        if (blob) {
          objectUrl = URL.createObjectURL(blob);
          setImageObjectUrl(objectUrl);
        }
      })
      .catch(() => {
        // Image unavailable — section will not render.
      });

    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [prescriptionId, prescription?.has_image]);

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

  const cautionFlags = medicationFlags.filter((flag) => {
    const severity = flag.severity.toLowerCase();

    return severity === "medium" || severity === "warning";
  });

  const infoFlags = medicationFlags.filter((flag) => {
    const severity = flag.severity.toLowerCase();

    return (
      severity === "low" ||
      severity === "info" ||
      severity === "informational"
    );
  });

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

  const prescriptionSafetyReviewRequired = medicationFlags.some((flag) => {
    const severity = flag.severity.toLowerCase();

    return (
      severity === "high" ||
      severity === "error" ||
      severity === "medium" ||
      severity === "warning"
    );
  });

  const needsReview =
    medicineReviewRequired.length > 0 ||
    prescriptionSafetyReviewRequired ||
    ocrFlags.length > 0;

  const imageUrl = imageObjectUrl;

  const verifiedMedicines =
    prescription.medicines.filter(
      isMedicineVerified
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

                {needsReview ? (
                  <button
                    type="button"
                    onClick={
                      handleReviewPrescription
                    }
                    className="inline-flex items-center gap-2 rounded-xl border border-[#d6b96d] bg-[#fff9e8] px-4 py-2.5 text-xs font-semibold text-[#725719] shadow-sm transition hover:bg-[#fff4d2]"
                  >
                    <span className="text-sm leading-none">
                      ✓
                    </span>
                    Review prescription
                  </button>
                ) : isPharmacistUser && prescription ? (
                  <button
                    type="button"
                    onClick={handleReviewPrescription}
                    className="inline-flex items-center gap-2 rounded-xl border border-[#dfe6e1] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] shadow-sm transition hover:bg-[#f4f7f5]"
                  >
                    Open in review workspace →
                  </button>
                ) : null}

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
            <div className="border-t border-red-100 bg-red-50/50 px-5 py-4 sm:px-7">
              <div className="flex items-start gap-3.5">
                <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-red-100 text-sm font-bold text-red-700">
                  !
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-red-800">
                      Human review recommended
                    </p>

                    {highPriorityFlags.length > 0 && (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-700">
                        {highPriorityFlags.length} high priority
                      </span>
                    )}
                  </div>

                  <p className="mt-1 text-xs leading-5 text-red-900/70">
                    {highPriorityFlags.length > 0
                      ? `${highPriorityFlags.length} high-priority safety finding${
                          highPriorityFlags.length === 1 ? "" : "s"
                        } detected. Review the medication safety findings before dispensing or clinical use.`
                      : "This analysis contains findings that require verification by a qualified healthcare professional before dispensing or clinical use."}
                  </p>

                  {medicationFlags.some(
                    (flag) =>
                      flag.type === "drug_interaction" ||
                      !!flag.interaction_id
                  ) && (
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-semibold text-red-800">
                        Medication interaction detected
                      </span>

                      <span className="text-red-300">•</span>

                      <span className="text-red-800/70">
                        Review the Safety tab for details
                      </span>
                    </div>
                  )}
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

            {/* Assign customer — pharmacists only */}

            {isPharmacistUser && (
              <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">

                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-[#344139]">
                    Assigned customer
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setShowAssign((v) => !v);
                      setAssignError("");
                      setAssignSearch("");
                      setAssignResults([]);
                    }}
                    className="text-[10px] font-medium text-[#35664d] hover:text-[#17211d]"
                  >
                    {showAssign ? "Cancel" : assignedCustomer ? "Change" : "Assign"}
                  </button>
                </div>

                {assignSuccess && (
                  <div className="mt-3 rounded-xl border border-[#d9e5dd] bg-[#f3f8f4] px-3 py-2.5 text-xs text-[#2d6444]">
                    {assignSuccess}
                  </div>
                )}

                {assignedCustomer ? (
                  <div className="mt-3 flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#3f7658]" />
                    <span className="text-xs font-medium text-[#17211d]">
                      {assignedCustomer.name}
                    </span>
                    <span className="font-mono text-[10px] text-[#7b8580]">
                      {assignedCustomer.customer_code}
                    </span>
                    <Link
                      href={`/customers/${encodeURIComponent(assignedCustomer.id)}`}
                      className="ml-auto text-[10px] text-[#35664d] hover:text-[#17211d]"
                    >
                      View →
                    </Link>
                  </div>
                ) : !showAssign ? (
                  <p className="mt-3 text-xs text-[#9aa39e]">
                    No customer assigned
                  </p>
                ) : null}

                {showAssign && (
                  <div className="mt-3">
                    <input
                      type="search"
                      value={assignSearch}
                      onChange={(e) => handleAssignSearch(e.target.value)}
                      placeholder="Search customers…"
                      className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-3 py-2 text-xs outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7]"
                    />

                    {assignSearching && (
                      <div className="mt-2 flex items-center gap-1.5 text-[11px] text-[#7b8580]">
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
                        Searching…
                      </div>
                    )}

                    {assignResults.length > 0 && (
                      <ul className="mt-2 divide-y divide-[#edf0ee] overflow-hidden rounded-xl border border-[#dfe6e1] bg-white">
                        {assignResults.map((c) => (
                          <li key={c.id}>
                            <form
                              onSubmit={(e) =>
                                handleAssignCustomer(e, c.id, c.name, c.customer_code)
                              }
                            >
                              <button
                                type="submit"
                                disabled={assigning}
                                className="flex w-full items-center justify-between px-3 py-2.5 text-left text-xs transition hover:bg-[#f4f7f5] disabled:opacity-60"
                              >
                                <span>
                                  <span className="font-medium text-[#17211d]">
                                    {c.name}
                                  </span>
                                  <span className="ml-1.5 font-mono text-[10px] text-[#7b8580]">
                                    {c.customer_code}
                                  </span>
                                  {c.phone && (
                                    <span className="ml-2 text-[10px] text-[#9aa39e]">
                                      {c.phone}
                                    </span>
                                  )}
                                </span>
                                <span className="shrink-0 text-[#35664d]">
                                  {assigning ? "…" : "Assign →"}
                                </span>
                              </button>
                            </form>
                          </li>
                        ))}
                      </ul>
                    )}

                    {assignSearch.trim() &&
                      !assignSearching &&
                      assignResults.length === 0 && (
                        <p className="mt-2 text-[11px] text-[#9aa39e]">
                          No customers found
                        </p>
                      )}

                    {assignError && (
                      <div className="mt-2 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-3 py-2 text-[11px] text-[#8b5547]">
                        {assignError}
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

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

                  {/* OCR header */}
                  <div className="border-b border-[#edf0ee] px-5 py-4 sm:px-6">
                    <div className="flex flex-wrap items-start justify-between gap-3">

                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[#edf6f1] text-[10px] font-bold text-[#35664d]">
                            OCR
                          </div>

                          <p className="text-xs font-bold text-[#26332c]">
                            Extracted prescription text
                          </p>
                        </div>

                        <p className="mt-1 pl-9 text-[10px] leading-4 text-[#89938d]">
                          Text recognized from the uploaded prescription image.
                        </p>
                      </div>

                      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-[#dce7e0] bg-[#f7faf8] px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.08em] text-[#617169]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#4d8063]" />
                        OCR processed
                      </span>

                    </div>
                  </div>

                  {/* OCR document */}
                  <div className="p-5 sm:p-6">

                    {prescription.raw_text ? (
                      <div className="overflow-hidden rounded-xl border border-[#e1e7e3] bg-[#fcfdfc]">

                        {/* Document top bar */}
                        <div className="flex items-center justify-between border-b border-[#edf1ee] bg-[#f7f9f8] px-4 py-2.5">
                          <span className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[#87928b]">
                            Recognition output
                          </span>

                          <span className="font-mono text-[9px] text-[#a0aaa5]">
                            READ-ONLY
                          </span>
                        </div>

                        {/* Recognized text */}
                        <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words px-5 py-5 font-mono text-[11px] leading-7 text-[#34423a] sm:px-6">
                          {prescription.raw_text}
                        </pre>

                      </div>
                    ) : (
                      <EmptyState
                        icon="OCR"
                        title="No OCR text available"
                        description="The prescription did not return readable OCR text."
                      />
                    )}
                  </div>

                </section>

                {/* Verification notice */}
                <div className="flex items-start gap-3 rounded-xl border border-[#e0e7e2] bg-[#f7faf8] px-4 py-3.5">

                  <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#e8f2ec] text-[10px] font-bold text-[#46735a]">
                    i
                  </div>

                  <div>
                    <p className="text-[10px] font-semibold text-[#536159]">
                      Verify against the original prescription
                    </p>

                    <p className="mt-0.5 text-[10px] leading-5 text-[#7d8982]">
                      OCR output is shown for transparency and verification.
                      Recognition errors can occur, so extracted text should
                      always be checked against the original prescription image.
                    </p>
                  </div>

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
  const isDanger = emphasis === "danger";

  return (
    <div
      className={
        isDanger
          ? "relative overflow-hidden rounded-2xl border border-[#e8cccc] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.03)]"
          : "relative overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.03)]"
      }
    >
      {/* Clinical accent */}
      <div
        className={
          isDanger
            ? "absolute inset-y-0 left-0 w-0.5 bg-[#a74646]"
            : "absolute inset-y-0 left-0 w-0.5 bg-[#d8e5dc]"
        }
      />

      <div className="flex items-start justify-between gap-4">

        <div className="min-w-0">

          <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-[#8b9690]">
            {label}
          </p>

          <div className="mt-2 flex items-baseline gap-2">
            <p
              className={
                isDanger
                  ? "text-[28px] font-semibold leading-none tracking-[-0.04em] text-[#8a3434]"
                  : "text-[28px] font-semibold leading-none tracking-[-0.04em] text-[#17211d]"
              }
            >
              {value}
            </p>
          </div>

          <p
            className={
              isDanger
                ? "mt-2 text-[10px] font-medium text-[#8a3434]"
                : "mt-2 text-[10px] text-[#7d8982]"
            }
          >
            {detail}
          </p>
        </div>

        <div
          className={
            isDanger
              ? "grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#efdada] bg-[#fff5f5] text-[10px] font-bold text-[#a74646]"
              : "grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-[#e1e9e4] bg-[#f7faf8] text-[10px] font-semibold text-[#53645a]"
          }
          aria-hidden="true"
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

function MedicineCard({ medicine }: { medicine: Medicine }) {
  const rawConfidence = getOverallConfidence(medicine);

  const confidenceDisplay =
    rawConfidence === null
      ? "—"
      : confidencePercent(rawConfidence);

  const extractionNeedsReview =
    medicine.needs_review === true ||
    (rawConfidence !== null && rawConfidence < 0.70);

  const isVerified = isMedicineVerified(medicine);

  const cardBorder = isVerified
    ? "border-[#CBE0D3]"
    : extractionNeedsReview
      ? "border-[#E5D4A8]"
      : "border-[#DFE6E1]";

  const statusStyle = isVerified
    ? "border border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]"
    : "border border-[#E5D4A8] bg-[#FFF7DF] text-[#A47B2C]";

  const iconStyle = isVerified
    ? "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]"
    : "border-[#E5D4A8] bg-[#FFF7DF] text-[#A47B2C]";

  return (
    <article
      className={`overflow-hidden rounded-2xl border bg-white shadow-sm transition-shadow hover:shadow-md ${cardBorder}`}
    >
      {/* Medication identity */}
      <div className="border-b border-[#DFE6E1] px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3.5">
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${iconStyle}`}
            >
              <span className="text-base font-semibold">Rx</span>
            </div>

            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold tracking-tight text-[#17211D]">
                  {medicine.name}
                </h3>

                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${statusStyle}`}
                >
                  <span>{isVerified ? "✓" : "!"}</span>
                  {isVerified ? "Verified" : "Review"}
                </span>
              </div>

              {medicine.generic_name &&
                medicine.generic_name.toLowerCase() !==
                  medicine.name.toLowerCase() && (
                  <p className="mt-1 text-sm text-[#7C8881]">
                    {medicine.generic_name}
                  </p>
                )}

              <div className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-xl font-semibold tracking-tight text-[#17211D]">
                  {medicine.strength_value && medicine.strength_unit
                    ? `${medicine.strength_value} ${medicine.strength_unit}`
                    : medicine.strength_value || "Strength not available"}
                </span>

                {medicine.dose_unit && (
                  <span className="text-sm text-[#7C8881]">
                    {medicine.dose_unit}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="shrink-0 text-right">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E]">
              Confidence
            </p>

            <p className="mt-1 text-sm font-semibold text-[#526158]">
              {confidenceDisplay}
            </p>
          </div>
        </div>
      </div>

      {/* Prescription details */}
      <div className="px-5 py-5">
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-[#DFE6E1] bg-[#DFE6E1] sm:grid-cols-3 lg:grid-cols-4">
          <MedDetail
            label="Dose"
            value={
              medicine.dose_value && medicine.dose_unit
                ? `${medicine.dose_value} ${medicine.dose_unit}`
                : "—"
            }
            emphasized
          />

          <MedDetail
            label="Route"
            value={medicine.route || "—"}
          />

          <MedDetail
            label="Frequency"
            value={
              medicine.frequency_value && medicine.frequency_unit
                ? `${medicine.frequency_value}× / ${medicine.frequency_unit}`
                : "—"
            }
          />

          <MedDetail
            label="Duration"
            value={
              medicine.duration_value && medicine.duration_unit
                ? `${medicine.duration_value} ${medicine.duration_unit}`
                : "—"
            }
          />

          <MedDetail
            label="Daily dose"
            value={
              medicine.daily_dose_value && medicine.daily_dose_unit
                ? `${medicine.daily_dose_value} ${medicine.daily_dose_unit}`
                : "—"
            }
          />

          <MedDetail
            label="Normalization"
            value={confidencePercent(medicine.normalization_confidence)}
          />

          <MedDetail
            label="Status"
            value={isVerified ? "Verified" : "Review required"}
          />
        </div>

        {/* Patient directions */}
        {medicine.instructions && (
          <div className="mt-5 rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 py-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-[#35664D]">▸</span>

              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7C8881]">
                Patient directions
              </p>
            </div>

            <p className="mt-2 text-sm leading-6 text-[#526158]">
              {medicine.instructions}
            </p>
          </div>
        )}

        {/* Extraction quality */}
        <div className="mt-5 border-t border-[#DFE6E1] pt-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#7C8881]">
              Confidence
            </span>

            <span className="text-xs font-semibold text-[#526158]">
              {confidenceDisplay}
            </span>
          </div>

          <div className="mt-2">
            <ConfidenceBar value={rawConfidence} />
          </div>
        </div>

        {/* Human review */}
        {extractionNeedsReview && !isVerified && (
          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-[#E5D4A8] bg-[#FFF7DF] px-3.5 py-3">
            <span className="mt-0.5 text-sm font-semibold text-[#A47B2C]">
              !
            </span>

            <div>
              <p className="text-xs font-semibold text-[#8A681F]">
                Pharmacist verification recommended
              </p>

              <p className="mt-0.5 text-xs leading-5 text-[#A47B2C]">
                Verify the extracted medication details against the original
                prescription before dispensing or clinical use.
              </p>
            </div>
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
  emphasized = false,
}: {
  label: string;
  value:
    | string
    | null
    | undefined;
  emphasized?: boolean;
}) {
  return (
    <div className="bg-white px-3.5 py-3.5">
      <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-[#9aa39e]">
        {label}
      </p>

      <p
        className={
          emphasized
            ? "mt-1 text-[11px] font-semibold text-[#17211d]"
            : "mt-1 text-[11px] font-semibold text-[#35423b]"
        }
      >
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

function SafetyFlagCard({ flag }: { flag: SafetyFlag }) {
  const severity = severityStyle(flag.severity);
  const normalizedSeverity = flag.severity.toLowerCase();

  const isHigh =
    normalizedSeverity === "high" ||
    normalizedSeverity === "error";

  const isCaution =
    normalizedSeverity === "medium" ||
    normalizedSeverity === "warning";

  const isInformational =
    normalizedSeverity === "low" ||
    normalizedSeverity === "info" ||
    normalizedSeverity === "informational";

  const isStrengthConflict =
    flag.type === "strength_conflict";

  const isInteraction =
    flag.type === "drug_interaction" ||
    !!flag.interaction_id;

  return (
    <article
      className={`overflow-hidden rounded-2xl border bg-white shadow-sm ${
        isStrengthConflict || isHigh
          ? "border-[#E7CACA]"
          : isCaution
          ? "border-[#E5D4A8]"
          : "border-[#DFE6E1]"
      }`}
    >
      <div
        className={`border-l-4 px-5 py-5 ${
          isStrengthConflict || isHigh
            ? "border-[#A74646]"
            : isCaution
            ? "border-[#A47B2C]"
            : "border-[#8A9891]"
        }`}
      >
        <div className="flex items-start gap-3">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-sm font-bold ${
              isStrengthConflict
                ? "border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]"
                : severity.iconBackground
            }`}
          >
            {isHigh || isStrengthConflict
              ? "!"
              : isCaution
              ? "!"
              : "i"}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${
                  isStrengthConflict
                    ? "border border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]"
                    : severity.badge
                }`}
              >
                {isStrengthConflict
                  ? "High priority"
                  : severity.label}
              </span>

              {isStrengthConflict && (
                <span className="rounded-full border border-[#E7CACA] bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#A74646]">
                  Strength conflict
                </span>
              )}

              {isInteraction && !isStrengthConflict && (
                <span className="rounded-full border border-[#DFE6E1] bg-[#FAFCFB] px-2.5 py-1 text-[10px] font-medium text-[#526158]">
                  Drug interaction
                </span>
              )}
            </div>

            <h3 className="mt-3 text-[15px] font-semibold leading-6 tracking-[-0.01em] text-[#17211D]">
              {flag.message}
            </h3>

            {flag.medicine && (
              <p className="mt-1.5 text-xs text-[#7C8881]">
                Medicine:{" "}
                <span className="font-medium text-[#526158]">
                  {flag.medicine}
                </span>
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Keep your existing strength-conflict section unchanged */}

      {isStrengthConflict && (
        <div className="border-t border-[#E7CACA] bg-[#FFF8F8] px-5 py-5">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#A74646]" />

            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#A74646]">
              Strength verification required
            </p>
          </div>

          <p className="mt-2 max-w-2xl text-xs leading-5 text-[#8F4A4A]">
            The prescribed strength does not match the strength
            associated with the resolved medicine reference.
          </p>

          <div className="mt-4 grid gap-px overflow-hidden rounded-xl border border-[#E7CACA] bg-[#E7CACA] sm:grid-cols-2">
            <div className="bg-white px-4 py-4">
              <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#9AA39E]">
                Prescription strength
              </p>

              <div className="mt-2 flex items-baseline gap-2">
                <p className="text-2xl font-semibold tracking-[-0.03em] text-[#17211D]">
                  {flag.prescription_strength || "Not available"}
                </p>

                <span className="text-[10px] font-medium uppercase tracking-wide text-[#A74646]">
                  Prescribed
                </span>
              </div>
            </div>

            <div className="bg-white px-4 py-4">
              <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-[#9AA39E]">
                Reference strength
              </p>

              <div className="mt-2 flex items-baseline gap-2">
                <p className="text-2xl font-semibold tracking-[-0.03em] text-[#17211D]">
                  {flag.reference_strength || "Not available"}
                </p>

                <span className="text-[10px] font-medium uppercase tracking-wide text-[#526158]">
                  Resolved reference
                </span>
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-[#E7CACA] bg-[#FFF0F0] px-4 py-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#F8DEDE] text-[#A74646]">
                <span className="text-xs font-bold">!</span>
              </div>

              <div>
                <p className="text-[11px] font-bold text-[#8F3D3D]">
                  Do not rely on the extracted strength
                </p>

                <p className="mt-1 text-xs leading-5 text-[#A74646]">
                  Confirm the prescribed strength against the
                  original prescription before dispensing or
                  clinical use.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Existing interaction details section */}

      {isInteraction &&
        flag.matched_drugs?.length &&
        !isStrengthConflict && (
          <div className="mx-5 mt-5 rounded-xl border border-[#E7CACA] bg-[#FFF0F0] p-4">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[#A74646]" />

              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#A74646]">
                Matched medicines
              </p>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {flag.matched_drugs.map((drug, index) => (
                <div
                  key={`${drug}-${index}`}
                  className="flex items-center gap-2"
                >
                  <span className="rounded-lg border border-[#DFE6E1] bg-white px-3 py-2 text-xs font-semibold text-[#526158] shadow-sm">
                    {drug}
                  </span>

                  {index < flag.matched_drugs!.length - 1 && (
                    <span className="text-xs font-bold text-[#A74646]">
                      +
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      {/* Existing clinical metadata section */}

      {(flag.interaction_category || flag.evidence_source) && (
        <div className="mx-5 mt-5 grid gap-3 sm:grid-cols-2">
          {flag.interaction_category && (
            <div className="rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E]">
                Risk category
              </p>

              <p className="mt-2 text-sm font-semibold text-[#526158]">
                {formatInteractionCategory(flag.interaction_category)}
              </p>
            </div>
          )}

          {flag.evidence_source && (
            <div className="rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E]">
                Evidence
              </p>

              <p className="mt-2 text-sm font-semibold text-[#526158]">
                {flag.evidence_source}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Recommended action */}

      {flag.review_action && (
        <div
          className={`mx-5 mt-5 rounded-xl border px-4 py-4 ${
            isStrengthConflict || isHigh
              ? "border-[#E7CACA] bg-[#FFF0F0]"
              : isCaution
              ? "border-[#E5D4A8] bg-[#FFF7DF]"
              : "border-[#DFE6E1] bg-[#FAFCFB]"
          }`}
        >
          <div className="flex items-start gap-3">
            <div
              className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                isStrengthConflict || isHigh
                  ? "bg-[#F8DEDE] text-[#A74646]"
                  : isCaution
                  ? "bg-[#F8EDC8] text-[#A47B2C]"
                  : "bg-[#EDF1EE] text-[#68766F]"
              }`}
            >
              <span className="text-xs font-bold">
                {isInformational ? "i" : "!"}
              </span>
            </div>

            <div className="min-w-0">
              <p
                className={`text-[10px] font-semibold uppercase tracking-[0.12em] ${
                  isStrengthConflict || isHigh
                    ? "text-[#A74646]"
                    : isCaution
                    ? "text-[#A47B2C]"
                    : "text-[#68766F]"
                }`}
              >
                Recommended action
              </p>

              <p className="mt-1.5 text-sm font-semibold leading-6 text-[#526158]">
                {flag.review_action}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Existing resolution metadata */}

      {isStrengthConflict && flag.resolution_reason && (
        <div className="mx-5 mt-5 rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E]">
              Resolution
            </span>

            <code className="rounded-md bg-white px-2 py-1 text-[10px] font-medium text-[#7C8881]">
              {flag.resolution_reason}
            </code>
          </div>
        </div>
      )}

      {flag.interaction_id && (
        <div className="mx-5 mt-5 flex flex-col gap-2 border-t border-[#DFE6E1] py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E]">
              Reference
            </span>

            <code className="rounded-md bg-[#FAFCFB] px-2 py-1 text-[10px] font-medium text-[#7C8881]">
              {flag.interaction_id}
            </code>
          </div>

          <span className="text-[11px] font-medium text-[#9AA39E]">
            Clinical review required
          </span>
        </div>
      )}

      {!flag.interaction_id && <div className="h-1" />}
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
