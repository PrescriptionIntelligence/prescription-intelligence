"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, isAuthenticated } from "@/lib/auth";

type Medicine = {
  id: string;
  name: string;
  generic_name: string | null;
  extraction_confidence: number | null;
  normalization_confidence: number | null;
};

type SafetyFlag = {
  type: string;
  severity: string;
  message: string;
};

type Prescription = {
  id: string;
  prescription_id: string;
  raw_text: string | null;
  status: string;
  safety_flags: SafetyFlag[];
  file_name: string | null;
  created_at: string;
  medicines: Medicine[];
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const PAGE_SIZE = 20;

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function getStatus(status: string) {
  if (status === "analyzed") {
    return {
      label: "Analyzed",
      className: "bg-[#EDF8F1] text-[#35664D] border-[#CBE0D3]",
    };
  }

  if (status === "ocr_failed") {
    return {
      label: "OCR failed",
      className: "bg-[#FFF0F0] text-[#A74646] border-[#E8CECA]",
    };
  }

  if (status === "uploaded") {
    return {
      label: "Uploaded",
      className: "bg-[#F5F8F6] text-[#526158] border-[#DFE6E1]",
    };
  }

  return {
    label: status,
    className: "bg-[#F5F8F6] text-[#526158] border-[#DFE6E1]",
  };
}

function getSafetyFlags(prescription: Prescription): SafetyFlag[] {
  return (prescription.safety_flags || []).filter(
    (flag) =>
      flag.type !== "ocr_extraction_failed" &&
      flag.type !== "poor_ocr_quality"
  );
}

function hasHighPriority(prescription: Prescription): boolean {
  return getSafetyFlags(prescription).some(
    (flag) => flag.severity.toLowerCase() === "high"
  );
}

function hasInteraction(prescription: Prescription): boolean {
  return getSafetyFlags(prescription).some(
    (flag) =>
      flag.type === "drug_interaction" ||
      flag.type === "interaction"
  );
}

function averageConfidence(
  medicines: Medicine[]
): number | null {
  const values: number[] = [];

  for (const medicine of medicines) {
    if (medicine.extraction_confidence !== null) {
      values.push(medicine.extraction_confidence);
    }

    if (medicine.normalization_confidence !== null) {
      values.push(medicine.normalization_confidence);
    }
  }

  if (values.length === 0) {
    return null;
  }

  const total = values.reduce(
    (sum, value) => sum + value,
    0
  );

  return total / values.length;
}

function getConfidenceLabel(
  confidence: number | null
): string {
  if (confidence === null) {
    return "—";
  }

  if (confidence >= 0.85) {
    return "High";
  }

  if (confidence >= 0.7) {
    return "Fair";
  }

  return "Low";
}

function getConfidenceClass(
  confidence: number | null
): string {
  if (confidence === null) {
    return "text-[#9AA39E]";
  }

  if (confidence >= 0.85) {
    return "text-[#35664D]";
  }

  if (confidence >= 0.7) {
    return "text-[#A47B2C]";
  }

  return "text-[#A74646]";
}

export default function HistoryPage() {
  const router = useRouter();

  const [prescriptions, setPrescriptions] = useState<
    Prescription[]
  >([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [safetyFilter, setSafetyFilter] = useState("all");
  const [filtersReady, setFiltersReady] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }

    const params = new URLSearchParams(window.location.search);

    setSearch(params.get("search") || "");

    setStatusFilter(
      params.get("status") || "all"
    );

    setSafetyFilter(
      params.get("safety") || "all"
    );

    setFiltersReady(true);

    loadPage(0);
  }, [router]);

  async function loadPage(offset: number) {
    setLoading(true);
    setError("");

    try {
      const response = await authFetch(
        `/prescriptions?skip=${offset}&limit=${PAGE_SIZE}`
      );

      if (!response.ok) {
        throw new Error("Failed to load prescription history.");
      }

      const data = (await response.json()) as Prescription[];

      if (offset === 0) {
        setPrescriptions(data);
      } else {
        setPrescriptions((previous) => [
          ...previous,
          ...data,
        ]);
      }

      setHasMore(data.length === PAGE_SIZE);
      setSkip(offset + data.length);
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load prescription history.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!filtersReady) {
      return;
    }

    const params = new URLSearchParams();

    if (search.trim()) {
      params.set("search", search.trim());
    }

    if (statusFilter !== "all") {
      params.set("status", statusFilter);
    }

    if (safetyFilter !== "all") {
      params.set("safety", safetyFilter);
    }

    const queryString = params.toString();

    const newUrl = queryString
      ? `/history?${queryString}`
      : "/history";

    window.history.replaceState(null, "", newUrl);
  }, [
    search,
    statusFilter,
    safetyFilter,
    filtersReady,
  ]);

  useEffect(() => {
    if (!filtersReady) {
      return;
    }

    function handlePopState() {
      const params = new URLSearchParams(
        window.location.search
      );

      setSearch(params.get("search") || "");

      setStatusFilter(
        params.get("status") || "all"
      );

      setSafetyFilter(
        params.get("safety") || "all"
      );
    }

    window.addEventListener(
      "popstate",
      handlePopState
    );

    return () => {
      window.removeEventListener(
        "popstate",
        handlePopState
      );
    };
  }, [filtersReady]);

  const filteredPrescriptions = prescriptions.filter(
    (prescription) => {
      const query = search.trim().toLowerCase();

      if (query) {
        const medicineNames = prescription.medicines
          .map((medicine) =>
            [
              medicine.name,
              medicine.generic_name || "",
            ].join(" ")
          )
          .join(" ");

        const searchableText = [
          prescription.prescription_id,
          prescription.file_name || "",
          prescription.raw_text || "",
          medicineNames,
        ]
          .join(" ")
          .toLowerCase();

        if (!searchableText.includes(query)) {
          return false;
        }
      }

      if (statusFilter === "review_required") {
        if (getSafetyFlags(prescription).length === 0) {
          return false;
        }
      }

      if (statusFilter === "analyzed") {
        if (prescription.status !== "analyzed") {
          return false;
        }
      }

      if (statusFilter === "uploaded") {
        if (prescription.status !== "uploaded") {
          return false;
        }
      }

      if (statusFilter === "ocr_failed") {
        if (prescription.status !== "ocr_failed") {
          return false;
        }
      }

      if (safetyFilter === "high_priority") {
        if (!hasHighPriority(prescription)) {
          return false;
        }
      }

      if (safetyFilter === "interactions") {
        if (!hasInteraction(prescription)) {
          return false;
        }
      }

      if (safetyFilter === "no_safety_findings") {
        if (getSafetyFlags(prescription).length !== 0) {
          return false;
        }
      }

      return true;
    }
  );

  const totalMedicines = prescriptions.reduce(
    (total, prescription) =>
      total + prescription.medicines.length,
    0
  );

  const prescriptionsWithSafety = prescriptions.filter(
    (prescription) =>
      getSafetyFlags(prescription).length > 0
  ).length;

  const highPriorityPrescriptions = prescriptions.filter(
    (prescription) => hasHighPriority(prescription)
  ).length;

  return (
    <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
      <header className="border-b border-[#DFE6E1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link
            href="/dashboard"
            className="flex items-center gap-3"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211D] text-xs font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908A]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <Link
              href="/dashboard"
              className="text-xs text-[#637069] hover:text-[#17211D]"
            >
              Dashboard
            </Link>

            <Link
              href="/history"
              className="text-xs font-medium text-[#17211D]"
            >
              History
            </Link>

            <Link
              href="/analyze"
              className="text-xs text-[#637069] hover:text-[#17211D]"
            >
              Analyze
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847D]">
              Analysis history
            </div>

            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">
              Prescription history
            </h1>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#69766F]">
              Review previous prescription analyses,
              extracted medicines, and safety findings.
            </p>
          </div>

          <Link
            href="/analyze"
            className="inline-flex w-fit rounded-xl bg-[#17211D] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
          >
            + New analysis
          </Link>
        </div>

        {error && (
          <div className="mt-6 rounded-xl border border-[#EAD8D2] bg-[#FBF5F2] px-4 py-3 text-xs text-[#8B5547]">
            {error}
          </div>
        )}

        {loading && prescriptions.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white px-8 py-16 text-center">
            <p className="text-sm text-[#8A948F]">
              Loading history...
            </p>
          </div>
        ) : prescriptions.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-dashed border-[#DFE6E1] bg-white px-8 py-16 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] text-sm font-semibold text-[#526158]">
              Rx
            </div>

            <h3 className="mt-4 text-sm font-medium text-[#526158]">
              No prescriptions yet
            </h3>

            <p className="mt-2 text-xs text-[#9AA4A0]">
              Upload your first prescription to get started.
            </p>

            <Link
              href="/analyze"
              className="mt-6 inline-flex rounded-xl bg-[#17211D] px-5 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
            >
              Analyze prescription
            </Link>
          </div>
        ) : (
          <>
            <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-2xl border border-[#DFE6E1] bg-white px-5 py-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]">
                  Prescriptions
                </div>

                <div className="mt-2 text-2xl font-semibold">
                  {prescriptions.length}
                </div>
              </div>

              <div className="rounded-2xl border border-[#DFE6E1] bg-white px-5 py-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]">
                  Medicines
                </div>

                <div className="mt-2 text-2xl font-semibold">
                  {totalMedicines}
                </div>
              </div>

              <div className="rounded-2xl border border-[#DFE6E1] bg-white px-5 py-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]">
                  Safety alerts
                </div>

                <div className="mt-2 text-2xl font-semibold text-[#A74646]">
                  {prescriptionsWithSafety}
                </div>
              </div>

              <div className="rounded-2xl border border-[#DFE6E1] bg-white px-5 py-4">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]">
                  High priority
                </div>

                <div className="mt-2 text-2xl font-semibold text-[#A74646]">
                  {highPriorityPrescriptions}
                </div>
              </div>
            </div>

            <div className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white p-4">
              <div className="grid gap-4 md:grid-cols-[1fr_220px_auto] md:items-end">
                <div>
                  <label
                    htmlFor="history-search"
                    className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
                  >
                    Search history
                  </label>

                  <input
                    id="history-search"
                    type="text"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search by prescription ID, medicine, or file name"
                    className="h-11 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm text-[#17211D] outline-none placeholder:text-[#9AA39E] focus:border-[#9AAEA4] focus:bg-white"
                  />
                </div>

                <div>
                  <label
                    htmlFor="history-status"
                    className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
                  >
                    Status
                  </label>

                  <select
                    id="history-status"
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                    className="h-11 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm text-[#17211D] outline-none focus:border-[#9AAEA4] focus:bg-white"
                  >
                    <option value="all">All</option>
                    <option value="review_required">Review required</option>
                    <option value="analyzed">Analyzed</option>
                    <option value="uploaded">Uploaded</option>
                    <option value="ocr_failed">OCR failed</option>
                  </select>
                </div>

                <div className="flex flex-wrap items-end gap-2">
                  <div>
                    <label
                      htmlFor="history-safety"
                      className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
                    >
                      Safety
                    </label>

                    <select
                      id="history-safety"
                      value={safetyFilter}
                      onChange={(event) => setSafetyFilter(event.target.value)}
                      className="h-11 rounded-xl border border-[#DFE6E1] bg-white px-3 text-sm text-[#17211D] outline-none transition focus:border-[#35664D]"
                    >
                      <option value="all">All safety</option>
                      <option value="high_priority">High priority</option>
                      <option value="interactions">Interactions</option>
                      <option value="no_safety_findings">No safety findings</option>
                    </select>
                  </div>

                  {(search.trim() ||
                    statusFilter !== "all" ||
                    safetyFilter !== "all") && (
                    <button
                      type="button"
                      onClick={() => {
                        setSearch("");
                        setStatusFilter("all");
                        setSafetyFilter("all");
                      }}
                      className="h-11 rounded-xl border border-[#DFE6E1] bg-white px-4 text-xs font-medium text-[#526158] transition hover:bg-[#FAFCFB]"
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              </div>
                </div>

            {filteredPrescriptions.length === 0 ? (
              <div className="mt-8 rounded-2xl border border-dashed border-[#DFE6E1] bg-white px-8 py-16 text-center">
                <h3 className="text-sm font-medium text-[#526158]">
                  No matching prescriptions
                </h3>

                <p className="mt-2 text-xs text-[#9AA4A0]">
                  Try another search term or change the filters.
                </p>

                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setStatusFilter("all");
                    setSafetyFilter("all");
                  }}
                  className="mt-5 text-xs font-medium text-[#526C5D] hover:underline"
                >
                  Clear search
                </button>
              </div>
            ) : (
              <div className="mt-8 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[850px] text-sm">
                    <thead>
                      <tr className="border-b border-[#E8EDE9] bg-[#FAFCFB] text-[10px] uppercase tracking-[0.12em] text-[#8A948F]">
                        <th className="px-5 py-3.5 text-left font-medium">
                          Prescription
                        </th>

                        <th className="px-5 py-3.5 text-left font-medium">
                          Date
                        </th>

                        <th className="px-5 py-3.5 text-left font-medium">
                          Status
                        </th>

                        <th className="px-5 py-3.5 text-right font-medium">
                          Medicines
                        </th>

                        <th className="px-5 py-3.5 text-right font-medium">
                          Safety
                        </th>

                        <th className="px-5 py-3.5 text-right font-medium">
                          Confidence
                        </th>

                        <th className="px-5 py-3.5" />
                      </tr>
                    </thead>

                    <tbody>
                      {filteredPrescriptions.map(
                        (prescription, index) => {
                          const status = getStatus(
                            prescription.status
                          );

                          const safetyFlags =
                            getSafetyFlags(prescription);

                          const confidence =
                            averageConfidence(
                              prescription.medicines
                            );

                          const highPriority =
                            hasHighPriority(prescription);

                          const interaction =
                            hasInteraction(prescription);

                          return (
                            <tr
                              key={
                                prescription.prescription_id
                              }
                              className={
                                index > 0
                                  ? "border-t border-[#EDF0EE] hover:bg-[#FAFCFB]"
                                  : "hover:bg-[#FAFCFB]"
                              }
                            >
                              <td className="px-5 py-5">
                                <div className="font-mono text-xs font-medium text-[#17211D]">
                                  {
                                    prescription.prescription_id
                                  }
                                </div>

                                <div className="mt-1 max-w-[240px] truncate text-[10px] text-[#8A948F]">
                                  {prescription.file_name ||
                                    "Prescription image"}
                                </div>
                              </td>

                              <td className="px-5 py-5 text-xs text-[#69766F]">
                                {formatDate(
                                  prescription.created_at
                                )}
                              </td>

                              <td className="px-5 py-5">
                                <span
                                  className={`inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-medium ${status.className}`}
                                >
                                  {status.label}
                                </span>

                                {highPriority && (
                                  <div className="mt-1.5 text-[10px] text-[#A74646]">
                                    High-priority finding
                                  </div>
                                )}
                              </td>

                              <td className="px-5 py-5 text-right">
                                <div className="text-xs font-medium">
                                  {
                                    prescription.medicines
                                      .length
                                  }
                                </div>

                                <div className="mt-1 max-w-[180px] truncate text-[10px] text-[#8A948F]">
                                  {prescription.medicines
                                    .map(
                                      (medicine) =>
                                        medicine.name
                                    )
                                    .join(", ")}
                                </div>
                              </td>

                              <td className="px-5 py-5 text-right">
                                {safetyFlags.length === 0 ? (
                                  <span className="text-xs text-[#9AA39E]">
                                    0
                                  </span>
                                ) : (
                                  <div>
                                    <div
                                      className={`text-xs font-semibold ${
                                        highPriority
                                          ? "text-[#A74646]"
                                          : "text-[#A47B2C]"
                                      }`}
                                    >
                                      {safetyFlags.length}
                                    </div>

                                    <div className="mt-1 text-[10px] text-[#8A948F]">
                                      {interaction
                                        ? "Interaction"
                                        : "Findings"}
                                    </div>
                                  </div>
                                )}
                              </td>

                              <td className="px-5 py-5 text-right">
                                <div
                                  className={`text-xs font-semibold ${getConfidenceClass(
                                    confidence
                                  )}`}
                                >
                                  {getConfidenceLabel(
                                    confidence
                                  )}
                                </div>

                                {confidence !== null && (
                                  <div className="mt-1 text-[10px] text-[#9AA39E]">
                                    {Math.round(
                                      confidence * 100
                                    )}
                                    %
                                  </div>
                                )}
                              </td>

                              <td className="px-5 py-5 text-right">
                                <Link
                                  href={`/analysis/${prescription.prescription_id}`}
                                  className="text-xs font-medium text-[#526C5D] hover:underline"
                                >
                                  Open →
                                </Link>
                              </td>
                            </tr>
                          );
                        }
                      )}
                    </tbody>
                  </table>
                </div>

                {hasMore && (
                  <div className="border-t border-[#EDF0EE] px-5 py-4 text-center">
                    <button
                      type="button"
                      onClick={() => loadPage(skip)}
                      disabled={loading}
                      className="text-xs font-medium text-[#526C5D] hover:underline disabled:opacity-50"
                    >
                      {loading
                        ? "Loading..."
                        : "Load more"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {prescriptions.length > 0 && (
          <div className="mt-8 border-t border-[#DFE6E1] pt-5 text-[10px] leading-5 text-[#8A948F]">
            Prescription Intelligence provides AI-generated
            decision support only. Medicine identification and
            extraction do not constitute clinical approval.
            Pharmacist verification is required before
            dispensing or clinical use.
          </div>
        )}
      </div>
    </main>
  );
}