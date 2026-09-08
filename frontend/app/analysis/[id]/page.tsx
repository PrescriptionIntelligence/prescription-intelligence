"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

function confidencePercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  return `${Math.round(val * 100)}%`;
}

function confidenceBarColor(val: number | null | undefined): string {
  if (val === null || val === undefined) return "bg-[#d0d5d2]";
  if (val >= 0.85) return "bg-[#4a7a60]";
  if (val >= 0.70) return "bg-[#8a7a30]";
  return "bg-[#a04040]";
}

function getOverallConfidence(m: Medicine): number | null {
  const c = [m.extraction_confidence, m.normalization_confidence].filter(
    (v) => v !== null && v !== undefined
  ) as number[];
  if (c.length === 0) return null;
  return c.reduce((a, b) => a + b, 0) / c.length;
}

function severityStyle(severity: string): { cls: string; label: string } {
  switch (severity) {
    case "high":
    case "error":
      return { cls: "bg-[#fdf0f0] border-[#f0cccc] text-[#7a2020]", label: "High Priority" };
    case "warning":
      return { cls: "bg-[#fdf8e8] border-[#e8d8a0] text-[#5a4810]", label: "Caution" };
    default:
      return { cls: "bg-[#f0f4ff] border-[#c0cce8] text-[#283060]", label: "Info" };
  }
}

function medicineStatusStyle(m: Medicine): { label: string; cls: string } {
  const confidence = getOverallConfidence(m);
  if (m.needs_review || (m.status || "").toUpperCase() === "UNKNOWN") {
    return { label: "Review Required", cls: "bg-[#fdf8e8] text-[#6a5010]" };
  }
  if (confidence !== null && confidence >= 0.85) {
    return { label: "Verified", cls: "bg-[#e8f5ed] text-[#2d5a3e]" };
  }
  if (confidence !== null && confidence >= 0.70) {
    return { label: "Review", cls: "bg-[#fff3e0] text-[#7a4810]" };
  }
  return { label: "Low Confidence", cls: "bg-[#fdf0f0] text-[#7a2020]" };
}

// =========================================================
// Component
// =========================================================

export default function AnalysisDetailPage() {
  const params = useParams();
  const prescriptionId = params?.id as string;

  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<
    "medicines" | "ocr" | "safety"
  >("medicines");

  useEffect(() => {
    if (!prescriptionId) return;

    // First try session storage (from immediate upload redirect)
    const cached = sessionStorage.getItem("prescription_review");
    if (cached) {
      try {
        const data = JSON.parse(cached);
        if (data.prescription_id === prescriptionId) {
          const rx: Prescription = {
            id: data.prescription_id,
            prescription_id: data.prescription_id,
            raw_text: data.raw_text,
            status: data.status,
            safety_flags: data.safety_flags || [],
            file_name: data.file_name,
            file_path: data.file_path,
            file_type: data.file_type,
            created_at: new Date().toISOString(),
            updated_at: null,
            medicines: data.medicines || [],
          };
          Promise.resolve().then(() => {
            setPrescription(rx);
            setLoading(false);
          });
          return;
        }
      } catch {
        // fall through to API fetch
      }
    }

    // Fetch from backend
    fetch(`${API_URL}/prescriptions/${prescriptionId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Prescription not found");
        return res.json();
      })
      .then((data) => {
        setPrescription(data);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load prescription");
      })
      .finally(() => setLoading(false));
  }, [prescriptionId]);

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f6f3]">
        <p className="text-sm text-[#8a948f]">Loading analysis…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f6f3]">
        <div className="text-center">
          <p className="text-sm text-[#8b4040]">{error}</p>
          <Link href="/history" className="mt-4 block text-xs text-[#526c5d] hover:underline">
            ← Back to history
          </Link>
        </div>
      </main>
    );
  }

  if (!prescription) return null;

  // OCR/extraction process warnings — not medication safety issues.
  const OCR_FLAG_TYPES = new Set(["ocr_extraction_failed", "poor_ocr_quality"]);
  const ocrFlags = prescription.safety_flags.filter((f) =>
    OCR_FLAG_TYPES.has(f.type)
  );
  // Medication safety flags only.
  const medicationFlags = prescription.safety_flags.filter(
    (f) => !OCR_FLAG_TYPES.has(f.type)
  );

  const highPriorityFlags = medicationFlags.filter(
    (f) => f.severity === "high" || f.severity === "error"
  );
  const cautionFlags = medicationFlags.filter(
    (f) => f.severity === "warning"
  );
  const infoFlags = medicationFlags.filter(
    (f) => f.severity === "info" || f.severity === "informational"
  );

  const reviewRequired = prescription.medicines.filter(
    (m) =>
      m.needs_review ||
      getOverallConfidence(m) !== null &&
      (getOverallConfidence(m) as number) < 0.70
  );

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">

      {/* Header */}
      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>
            <div>
              <div className="text-sm font-semibold">Prescription Intelligence</div>
            </div>
          </Link>
          <nav className="flex items-center gap-5 text-xs">
            <Link href="/dashboard" className="text-[#637069] hover:text-[#17211d]">
              Dashboard
            </Link>
            <Link href="/history" className="text-[#637069] hover:text-[#17211d]">
              History
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-10">

        {/* Breadcrumb */}
        <div className="mb-6 flex items-center gap-2 text-xs text-[#8a948f]">
          <Link href="/history" className="hover:text-[#17211d]">
            History
          </Link>
          <span>/</span>
          <span className="font-mono text-[#17211d]">{prescription.prescription_id}</span>
        </div>

        {/* Page title */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.03em]">
              Analysis: {prescription.prescription_id}
            </h1>
            <p className="mt-1 text-sm text-[#8a948f]">
              {prescription.file_name && `${prescription.file_name} · `}
              {formatDate(prescription.created_at)}
            </p>
          </div>
          <div className="flex gap-3">
            {highPriorityFlags.length > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fdf0f0] px-3 py-1.5 text-xs font-medium text-[#7a2020]">
                ● {highPriorityFlags.length} High Priority
              </span>
            )}
            {reviewRequired.length > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fdf8e8] px-3 py-1.5 text-xs font-medium text-[#6a5010]">
                ⚑ {reviewRequired.length} Review Required
              </span>
            )}
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-12">

          {/* Left: image + summary */}
          <div className="lg:col-span-3 space-y-5">

            {/* Image */}
            {prescription.file_path && (
              <div className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white">
                <div className="border-b border-[#edf0ee] px-4 py-3">
                  <span className="text-xs font-medium text-[#5a6560]">
                    Prescription image
                  </span>
                </div>
                <div className="p-4">
                  <img
                    src={`${API_URL}/uploads/${prescription.file_path.split(/[\\/]/).pop()}`}
                    alt="Prescription"
                    className="w-full rounded-xl object-contain"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                </div>
              </div>
            )}

            {/* Summary card */}
            <div className="rounded-2xl border border-[#dfe6e1] bg-white p-5">
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[#89938e]">
                Summary
              </div>
              <dl className="mt-4 space-y-3 text-xs">
                <SummaryRow label="Medicines extracted" value={String(prescription.medicines.length)} />
                <SummaryRow label="Safety flags" value={String(medicationFlags.length)} />
                {ocrFlags.length > 0 && (
                  <SummaryRow label="OCR / Extraction" value={String(ocrFlags.length)} />
                )}
                <SummaryRow label="Needs review" value={String(reviewRequired.length)} />
                <SummaryRow label="Status" value={prescription.status} />
              </dl>
            </div>

          </div>

          {/* Right: tabbed content */}
          <div className="lg:col-span-9">

            {/* Tabs */}
            <div className="mb-6 flex gap-1 rounded-xl border border-[#dfe6e1] bg-white p-1">
              {(["medicines", "safety", "ocr"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 rounded-lg py-2.5 text-xs font-medium capitalize transition ${
                    activeTab === tab
                      ? "bg-[#17211d] text-white"
                      : "text-[#637069] hover:bg-[#f0f3f1]"
                  }`}
                >
                  {tab === "medicines"
                    ? `Medicines (${prescription.medicines.length})`
                    : tab === "safety"
                    ? `Safety (${medicationFlags.length})`
                    : "OCR Text"}
                </button>
              ))}
            </div>

            {/* Medicines tab */}
            {activeTab === "medicines" && (
              <div className="space-y-4">
                {prescription.medicines.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-[#dfe6e1] bg-white px-8 py-12 text-center">
                    <p className="text-sm text-[#8a948f]">
                      No medicines could be extracted from this prescription.
                    </p>
                    <p className="mt-2 text-xs text-[#a0aaa5]">
                      This may indicate poor image quality or an unsupported format.
                    </p>
                  </div>
                ) : (
                  prescription.medicines.map((medicine) => (
                    <MedicineCard key={medicine.id} medicine={medicine} />
                  ))
                )}
              </div>
            )}

            {/* Safety tab */}
            {activeTab === "safety" && (
              <div className="space-y-4">
                {/* OCR / Extraction issues — shown first, visually distinct */}
                {ocrFlags.length > 0 && (
                  <div>
                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#4a5a70]">
                      OCR / Extraction
                    </div>
                    <div className="space-y-3">
                      {ocrFlags.map((flag, i) => (
                        <OcrFlagCard key={i} flag={flag} />
                      ))}
                    </div>
                  </div>
                )}

                {/* Medication safety flags */}
                {medicationFlags.length === 0 ? (
                  <div className="rounded-2xl border border-[#c7dece] bg-[#f0faf4] px-8 py-10 text-center">
                    <p className="text-sm font-medium text-[#2d5a3e]">
                      No medication safety flags detected
                    </p>
                    <p className="mt-1 text-xs text-[#5a7a68]">
                      Manual pharmacist review is still required before dispensing.
                    </p>
                  </div>
                ) : (
                  <>
                    {highPriorityFlags.length > 0 && (
                      <div>
                        <div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#7a2020]">
                          High Priority
                        </div>
                        <div className="space-y-3">
                          {highPriorityFlags.map((flag, i) => (
                            <SafetyFlagCard key={i} flag={flag} />
                          ))}
                        </div>
                      </div>
                    )}
                    {cautionFlags.length > 0 && (
                      <div>
                        <div className="mb-3 mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-[#6a5010]">
                          Caution / Review
                        </div>
                        <div className="space-y-3">
                          {cautionFlags.map((flag, i) => (
                            <SafetyFlagCard key={i} flag={flag} />
                          ))}
                        </div>
                      </div>
                    )}
                    {infoFlags.length > 0 && (
                      <div>
                        <div className="mb-3 mt-6 text-xs font-semibold uppercase tracking-[0.14em] text-[#4a5070]">
                          Informational
                        </div>
                        <div className="space-y-3">
                          {infoFlags.map((flag, i) => (
                            <SafetyFlagCard key={i} flag={flag} />
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                <div className="mt-6 rounded-xl border border-[#dfe6e1] bg-[#fafcfb] p-4 text-xs text-[#6b7870] leading-5">
                  <strong>Medical disclaimer:</strong> Safety checks are
                  decision-support tools only. They are based on a limited,
                  curated reference set and do not replace clinical judgment.
                  Always verify safety information independently before dispensing.
                </div>
              </div>
            )}

            {/* OCR tab */}
            {activeTab === "ocr" && (
              <div className="space-y-4">
                <div className="rounded-2xl border border-[#dfe6e1] bg-white p-6">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[#89938e]">
                    Extracted OCR text
                  </div>
                  {prescription.raw_text ? (
                    <pre className="mt-4 whitespace-pre-wrap text-xs leading-6 text-[#3a4540] font-mono">
                      {prescription.raw_text}
                    </pre>
                  ) : (
                    <p className="mt-4 text-sm text-[#8a948f]">
                      No OCR text available.
                    </p>
                  )}
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </main>
  );
}

// =========================================================
// Sub-components
// =========================================================

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-[#8a948f]">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function MedicineCard({ medicine }: { medicine: Medicine }) {
  const status = medicineStatusStyle(medicine);

  return (
    <div className="rounded-2xl border border-[#dfe6e1] bg-white p-5">

      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">
            {medicine.generic_name || medicine.name}
          </h3>
          {medicine.brand_name && medicine.brand_name !== medicine.generic_name && (
            <p className="text-xs text-[#8a948f]">
              Brand: {medicine.brand_name}
            </p>
          )}
          {medicine.raw_text && (
            <p className="mt-1 font-mono text-xs text-[#a0aaa5]">
              OCR: &ldquo;{medicine.raw_text}&rdquo;
            </p>
          )}
        </div>
        <span className={`rounded-full px-3 py-1 text-[10px] font-medium ${status.cls}`}>
          {status.label}
        </span>
      </div>

      {/* Details grid */}
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
        <MedDetail label="Strength" value={medicine.strength_value != null ? `${medicine.strength_value}${medicine.strength_unit ? " " + medicine.strength_unit : ""}` : null} />
        <MedDetail label="Dose" value={medicine.dose_value != null ? `${medicine.dose_value}${medicine.dose_unit ? " " + medicine.dose_unit : ""}` : null} />
        <MedDetail label="Route" value={medicine.route} />
        <MedDetail label="Frequency" value={medicine.frequency_value != null ? `${medicine.frequency_value}×/${medicine.frequency_unit || "day"}` : null} />
        <MedDetail label="Duration" value={medicine.duration_value != null ? `${medicine.duration_value} ${medicine.duration_unit || "days"}` : null} />
        {medicine.daily_dose_value != null && (
          <MedDetail label="Daily dose" value={`${medicine.daily_dose_value} ${medicine.daily_dose_unit || "mg"}`} />
        )}
      </div>

      {medicine.instructions && (
        <div className="mt-3 rounded-lg bg-[#f7faf8] px-3 py-2 text-xs text-[#5a6560]">
          Instructions: {medicine.instructions}
        </div>
      )}

      {/* Confidence bars */}
      <div className="mt-4 space-y-2">
        <ConfidenceRow
          label="Extraction confidence"
          value={medicine.extraction_confidence}
        />
        <ConfidenceRow
          label="Normalization confidence"
          value={medicine.normalization_confidence}
        />
      </div>
    </div>
  );
}

function MedDetail({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <span className="text-[#8a948f]">{label}: </span>
      <span className="font-medium">{value ?? "—"}</span>
    </div>
  );
}

function ConfidenceRow({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-44 shrink-0 text-[10px] text-[#8a948f]">{label}</span>
      <div className="flex-1 rounded-full bg-[#e8ede9]" style={{ height: 4 }}>
        <div
          className={`h-full rounded-full ${confidenceBarColor(value)} transition-all`}
          style={{ width: value !== null && value !== undefined ? `${value * 100}%` : "0%" }}
        />
      </div>
      <span className="w-12 text-right text-[10px] font-medium">
        {confidencePercent(value)}
      </span>
    </div>
  );
}

function OcrFlagCard({ flag }: { flag: SafetyFlag }) {
  return (
    <div className="rounded-2xl border border-[#d8e0ea] bg-[#f7f9fc] p-5">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#e8edf5] text-xs text-[#4a5a70]">
          OCR
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-[#34445a]">
              {flag.message}
            </span>

            <span className="rounded-full bg-[#e8edf5] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#4a5a70]">
              Extraction
            </span>
          </div>

          {flag.medicine && (
            <p className="mt-2 text-xs text-[#6b7888]">
              Related text:{" "}
              <span className="font-mono">{flag.medicine}</span>
            </p>
          )}

          <p className="mt-2 text-xs leading-5 text-[#7a8794]">
            This indicates an OCR or extraction limitation. Verify the
            prescription image and manually confirm the extracted information.
          </p>
        </div>
      </div>
    </div>
  );
}

function SafetyFlagCard({ flag }: { flag: SafetyFlag }) {
  const style = severityStyle(flag.severity);
  return (
    <div className={`rounded-xl border p-4 text-xs ${style.cls}`}>
      <div className="flex items-center justify-between">
        <span className="font-semibold">{style.label}</span>
        {flag.medicine && (
          <span className="font-mono">{flag.medicine}</span>
        )}
      </div>
      <p className="mt-2 leading-5">{flag.message}</p>
    </div>
  );
}
