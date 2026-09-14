"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, getUser, isAuthenticated } from "../../lib/auth";

// =========================================================
// Types
// =========================================================

type Stage =
  | "idle"
  | "uploading"
  | "processing"
  | "complete"
  | "error";

const ALLOWED_TYPES = [
  "image/jpeg",
  "image/jpg",
  "image/png",
];

const MAX_SIZE_MB = 10;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

// =========================================================
// Component
// =========================================================

export default function AnalyzePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [fileName, setFileName] = useState("");
  const [previewUrl, setPreviewUrl] =
    useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  // ---------------------------------------------------------
  // File validation
  // ---------------------------------------------------------

  function validateFile(file: File): string | null {
    if (!ALLOWED_TYPES.includes(file.type)) {
      return `Unsupported file type: ${file.type}. Please upload a JPG or PNG image.`;
    }

    if (file.size > MAX_SIZE_BYTES) {
      return `File is too large (${(
        file.size /
        1024 /
        1024
      ).toFixed(1)} MB). Maximum allowed size is ${MAX_SIZE_MB} MB.`;
    }

    if (file.size === 0) {
      return "The selected file is empty.";
    }

    return null;
  }

  // ---------------------------------------------------------
  // File handling
  // ---------------------------------------------------------

  async function handleFile(file: File) {
    const validationError = validateFile(file);

    if (validationError) {
      setErrorMessage(validationError);
      setStage("error");
      return;
    }

    // -------------------------------------------------------
    // Authentication check before upload
    // -------------------------------------------------------

    if (!isAuthenticated()) {
      router.push("/sign-in");
      return;
    }

    const currentUser = getUser();

    if (!currentUser) {
      router.push("/sign-in");
      return;
    }

    // Customers should use their customer workflow instead
    // of the pharmacist analysis workspace.
    if (currentUser.role === "customer") {
      router.push("/customer");
      return;
    }

    setFileName(file.name);
    setErrorMessage("");

    // -------------------------------------------------------
    // Create preview
    // -------------------------------------------------------

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);

    setStage("uploading");
    setProgress(20);

    try {
      const formData = new FormData();
      formData.append("file", file);

      setProgress(40);

      // IMPORTANT:
      // Use authFetch instead of fetch().
      // authFetch automatically sends:
      //
      // Authorization: Bearer <JWT>
      //
      const response = await authFetch(
        "/prescriptions/upload",
        {
          method: "POST",
          body: formData,
        }
      );

      setProgress(80);
      setStage("processing");

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({}));

        throw new Error(
          typeof errorData?.detail === "string"
            ? errorData.detail
            : `Upload failed (${response.status})`
        );
      }

      const data = await response.json();

      if (!data?.prescription_id) {
        throw new Error(
          "The server did not return a prescription ID."
        );
      }

      setProgress(100);
      setStage("complete");

      // -----------------------------------------------------
      // Store result for analysis page
      // -----------------------------------------------------

      sessionStorage.setItem(
        "prescription_review",
        JSON.stringify(data)
      );

      sessionStorage.setItem(
        "prescription_file_name",
        file.name
      );

      // -----------------------------------------------------
      // Redirect to analysis
      // -----------------------------------------------------

      window.setTimeout(() => {
        router.push(
          `/analysis/${data.prescription_id}`
        );
      }, 800);
    } catch (error) {
      console.error("Upload error:", error);

      setStage("error");

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "An unexpected error occurred. Please try again."
      );

      setProgress(0);
    }
  }

  // ---------------------------------------------------------
  // Drag/drop handlers
  // ---------------------------------------------------------

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(true);
    },
    []
  );

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];

      if (file) {
        handleFile(file);
      }
    },
    // handleFile intentionally omitted because it is
    // recreated on render and this handler is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0];

    if (file) {
      handleFile(file);
    }
  };

  // ---------------------------------------------------------
  // Reset
  // ---------------------------------------------------------

  function reset() {
    setStage("idle");
    setFileName("");
    setErrorMessage("");
    setProgress(0);

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setPreviewUrl(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  // ---------------------------------------------------------
  // Render
  // ---------------------------------------------------------

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">
      {/* Header */}
      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link
            href="/"
            className="flex items-center gap-3"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908a]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <Link
              href="/dashboard"
              className="text-xs text-[#637069] hover:text-[#17211d]"
            >
              Dashboard
            </Link>

            <Link
              href="/history"
              className="text-xs text-[#637069] hover:text-[#17211d]"
            >
              History
            </Link>

            <Link
              href="/analyze"
              className="text-xs font-medium text-[#17211d]"
            >
              Analyze
            </Link>
          </nav>
        </div>
      </header>

      {/* Content */}
      <div className="mx-auto max-w-4xl px-6 py-14">
        {/* Page header */}
        <div className="mb-10">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
            Prescription analysis
          </div>

          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
            Upload a prescription
          </h1>

          <p className="mt-2 max-w-lg text-sm leading-6 text-[#7b8580]">
            Upload a clear image of a prescription. The
            system will extract medicine information, compute
            confidence scores, and identify potential safety
            concerns for your review.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-5">
          {/* Upload zone */}
          <div className="lg:col-span-3">
            {stage === "idle" && (
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() =>
                  inputRef.current?.click()
                }
                className={`
                  relative flex min-h-64 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition
                  ${
                    isDragging
                      ? "border-[#617a6d] bg-[#edf3ef]"
                      : "border-[#d1dcd5] bg-white hover:border-[#a0b0a8] hover:bg-[#f8fbf9]"
                  }
                `}
              >
                <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-[#edf3ef] text-2xl text-[#5a7a68]">
                  ↑
                </div>

                <p className="text-sm font-medium text-[#3a4f46]">
                  Drop prescription here or{" "}
                  <span className="text-[#3d6b55] underline underline-offset-2">
                    browse files
                  </span>
                </p>

                <p className="mt-2 text-xs text-[#8a948f]">
                  JPG, PNG · Maximum {MAX_SIZE_MB} MB
                </p>

                <input
                  ref={inputRef}
                  type="file"
                  accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                  className="hidden"
                  onChange={handleInputChange}
                />
              </div>
            )}

            {(stage === "uploading" ||
              stage === "processing") && (
              <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-[#dfe6e1] bg-white p-10 text-center">
                {previewUrl && (
                  <img
                    src={previewUrl}
                    alt="Prescription preview"
                    className="mb-6 h-36 w-auto rounded-lg object-contain opacity-70 shadow"
                  />
                )}

                <div className="mb-3 text-sm font-medium">
                  {stage === "uploading"
                    ? "Uploading…"
                    : "Analyzing prescription…"}
                </div>

                <div className="mb-2 text-xs text-[#8a948f]">
                  {fileName}
                </div>

                <div
                  className="mt-4 w-full max-w-xs rounded-full bg-[#e8ede9]"
                  style={{ height: 4 }}
                >
                  <div
                    className="h-full rounded-full bg-[#4a7a60] transition-all duration-500"
                    style={{
                      width: `${progress}%`,
                    }}
                  />
                </div>

                {stage === "processing" && (
                  <p className="mt-4 text-xs text-[#8a948f]">
                    Running OCR and medicine extraction
                    pipeline…
                  </p>
                )}
              </div>
            )}

            {stage === "complete" && (
              <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-[#c7dece] bg-[#f0faf4] p-10 text-center">
                <div className="mb-4 grid h-14 w-14 place-items-center rounded-full bg-[#c7dece] text-xl text-[#2d5a3e]">
                  ✓
                </div>

                <div className="text-sm font-medium text-[#2d5a3e]">
                  Analysis complete
                </div>

                <p className="mt-2 text-xs text-[#5a7a68]">
                  Redirecting to results…
                </p>
              </div>
            )}

            {stage === "error" && (
              <div className="rounded-2xl border border-[#e8d0cc] bg-[#fdf6f5] p-8">
                {previewUrl && (
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="mb-5 h-28 w-auto rounded-lg object-contain opacity-60"
                  />
                )}

                <div className="mb-2 text-sm font-medium text-[#7a3a30]">
                  Upload failed
                </div>

                <p className="text-sm leading-6 text-[#8a4a40]">
                  {errorMessage}
                </p>

                <button
                  onClick={reset}
                  className="mt-6 rounded-xl border border-[#d0b0aa] bg-white px-4 py-2.5 text-xs font-medium text-[#7a3a30] transition hover:bg-[#fdf0ee]"
                >
                  Try again
                </button>
              </div>
            )}
          </div>

          {/* Information panel */}
          <div className="space-y-6 lg:col-span-2">
            <div className="rounded-2xl border border-[#dfe6e1] bg-white p-6">
              <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-[#89938e]">
                What happens next
              </h3>

              <ol className="mt-4 space-y-3">
                {[
                  "Image preprocessing for better OCR accuracy",
                  "Text extraction with multi-mode OCR",
                  "Medicine candidate detection",
                  "Medicine normalization with confidence scoring",
                  "Safety analysis and flag detection",
                  "Structured report generation",
                ].map((step, i) => (
                  <li
                    key={i}
                    className="flex gap-3 text-xs text-[#5a6560]"
                  >
                    <span className="mt-0.5 shrink-0 text-[#9aaa9f]">
                      {i + 1}.
                    </span>

                    {step}
                  </li>
                ))}
              </ol>
            </div>

            <div className="rounded-2xl border border-[#dfe6e1] bg-white p-6">
              <h3 className="text-xs font-semibold uppercase tracking-[0.15em] text-[#89938e]">
                Important
              </h3>

              <p className="mt-3 text-xs leading-5 text-[#6b7870]">
                AI analysis is a decision-support tool. All
                results must be reviewed and verified by a
                qualified pharmacist before dispensing.
              </p>

              <p className="mt-3 text-xs leading-5 text-[#6b7870]">
                Uncertain medicines will be flagged for manual
                review. Low-confidence identifications are never
                automatically accepted.
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}