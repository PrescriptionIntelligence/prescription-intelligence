"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "../../lib/auth";

// =========================================================
// Types
// =========================================================

type Medicine = {
  id: string;
  name: string;
  generic_name: string | null;
  extraction_confidence: number | null;
  normalization_confidence: number | null;
};

type Prescription = {
  id: string;
  prescription_id: string;
  raw_text: string | null;
  status: string;
  safety_flags: { type: string; severity: string; message: string }[];
  file_name: string | null;
  created_at: string;
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

function statusBadge(status: string): { label: string; cls: string } {
  switch (status) {
    case "analyzed":
      return { label: "Analyzed", cls: "bg-[#e8f5ed] text-[#3a6b4e]" };
    case "ocr_failed":
      return { label: "OCR Failed", cls: "bg-[#fef3f2] text-[#8b4a3a]" };
    case "uploaded":
      return { label: "Uploaded", cls: "bg-[#f0f3ff] text-[#3a4a8b]" };
    default:
      return { label: status, cls: "bg-[#f0f0f0] text-[#606060]" };
  }
}

function avgConfidence(medicines: Medicine[]): number | null {
  const vals = medicines.flatMap((m) =>
    [m.extraction_confidence, m.normalization_confidence].filter(
      (v) => v !== null && v !== undefined
    )
  ) as number[];
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}

function confidenceLabel(c: number | null): string {
  if (c === null) return "—";
  if (c >= 0.85) return "High";
  if (c >= 0.70) return "Fair";
  return "Low";
}

function confidenceColor(c: number | null): string {
  if (c === null) return "text-[#a0aaa5]";
  if (c >= 0.85) return "text-[#3a6b4e]";
  if (c >= 0.70) return "text-[#756c3a]";
  return "text-[#8b4a3a]";
}

// =========================================================
// Component
// =========================================================

export default function HistoryPage() {
  const router = useRouter();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const PAGE_SIZE = 20;

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }

    loadPage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadPage(offset: number) {
    setLoading(true);
    fetch(`${API_URL}/prescriptions?skip=${offset}&limit=${PAGE_SIZE}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load history");
        return res.json();
      })
      .then((data: Prescription[]) => {
        if (offset === 0) {
          setPrescriptions(data);
        } else {
          setPrescriptions((prev) => [...prev, ...data]);
        }
        setHasMore(data.length === PAGE_SIZE);
        setSkip(offset + data.length);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load history");
      })
      .finally(() => setLoading(false));
  }

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">

      {/* Header */}
      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>
            <div>
              <div className="text-sm font-semibold">Prescription Intelligence</div>
              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908a]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <Link href="/dashboard" className="text-xs text-[#637069] hover:text-[#17211d]">
              Dashboard
            </Link>
            <Link href="/history" className="text-xs font-medium text-[#17211d]">
              History
            </Link>
            <Link href="/analyze" className="text-xs text-[#637069] hover:text-[#17211d]">
              Analyze
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-12">

        <div className="mb-8 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
              Analysis history
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">
              Prescription history
            </h1>
          </div>
          <Link
            href="/analyze"
            className="rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-medium text-white hover:bg-[#26332d] transition"
          >
            + New analysis
          </Link>
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs text-[#8b5547]">
            {error}
          </div>
        )}

        {loading && prescriptions.length === 0 ? (
          <div className="rounded-2xl border border-[#dfe6e1] bg-white px-8 py-16 text-center">
            <p className="text-sm text-[#8a948f]">Loading history…</p>
          </div>
        ) : prescriptions.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#dfe6e1] bg-white px-8 py-16 text-center">
            <div className="text-3xl text-[#cdd6d0]">Rx</div>
            <h3 className="mt-4 text-sm font-medium text-[#6b7870]">
              No prescriptions yet
            </h3>
            <p className="mt-2 text-xs text-[#9aa4a0]">
              Upload your first prescription to get started.
            </p>
            <Link
              href="/analyze"
              className="mt-6 inline-flex rounded-xl bg-[#17211d] px-5 py-2.5 text-xs font-medium text-white hover:bg-[#26332d] transition"
            >
              Analyze prescription
            </Link>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#e8ede9] bg-[#f7faf8] text-xs uppercase tracking-[0.12em] text-[#8a948f]">
                  <th className="px-5 py-3 text-left font-medium">
                    Prescription ID
                  </th>
                  <th className="hidden px-5 py-3 text-left font-medium md:table-cell">
                    File
                  </th>
                  <th className="hidden px-5 py-3 text-left font-medium lg:table-cell">
                    Date
                  </th>
                  <th className="px-5 py-3 text-left font-medium">
                    Status
                  </th>
                  <th className="hidden px-5 py-3 text-right font-medium sm:table-cell">
                    Medicines
                  </th>
                  <th className="hidden px-5 py-3 text-right font-medium lg:table-cell">
                    Safety
                  </th>
                  <th className="hidden px-5 py-3 text-right font-medium xl:table-cell">
                    Confidence
                  </th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {prescriptions.map((rx, i) => {
                  const badge = statusBadge(rx.status);
                  const confidence = avgConfidence(rx.medicines);
                  const safetyCount = (rx.safety_flags || []).length;
                  return (
                    <tr
                      key={rx.prescription_id}
                      className={`${i !== 0 ? "border-t border-[#edf0ee]" : ""} hover:bg-[#fafcfb] transition`}
                    >
                      <td className="px-5 py-4 font-mono text-xs">
                        {rx.prescription_id}
                      </td>
                      <td className="hidden px-5 py-4 text-xs text-[#6b7870] md:table-cell">
                        {rx.file_name || "—"}
                      </td>
                      <td className="hidden px-5 py-4 text-xs text-[#77847d] lg:table-cell">
                        {formatDate(rx.created_at)}
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-medium ${badge.cls}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="hidden px-5 py-4 text-right text-xs sm:table-cell">
                        {rx.medicines.length}
                      </td>
                      <td className="hidden px-5 py-4 text-right text-xs lg:table-cell">
                        {safetyCount > 0 ? (
                          <span className="font-medium text-[#8b4a3a]">{safetyCount}</span>
                        ) : (
                          <span className="text-[#a0aaa5]">0</span>
                        )}
                      </td>
                      <td className={`hidden px-5 py-4 text-right text-xs font-medium xl:table-cell ${confidenceColor(confidence)}`}>
                        {confidenceLabel(confidence)}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Link
                          href={`/analysis/${rx.prescription_id}`}
                          className="text-xs text-[#526c5d] hover:underline"
                        >
                          Open →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {hasMore && (
              <div className="border-t border-[#edf0ee] px-5 py-4 text-center">
                <button
                  onClick={() => loadPage(skip)}
                  disabled={loading}
                  className="text-xs font-medium text-[#526c5d] hover:underline disabled:opacity-50"
                >
                  {loading ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
