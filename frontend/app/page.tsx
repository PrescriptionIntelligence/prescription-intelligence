"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getUser, isAuthenticated, logout, User } from "../lib/auth";

type Stage = "idle" | "processing" | "complete" | "error";

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<Stage>("idle");
  const [fileName, setFileName] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (isAuthenticated()) {
      setUser(getUser());
    }
  }, []);

  function chooseFile() {
    inputRef.current?.click();
  }

  async function handleFile(file?: File) {
    if (!file) return;

    setFileName(file.name);
    setErrorMessage("");
    setStage("processing");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(
        "http://localhost:8000/prescriptions/upload",
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        let message = "Unable to process the prescription.";

        try {
          const errorData = await response.json();

          if (typeof errorData?.detail === "string") {
            message = errorData.detail;
          }
        } catch {
          // Keep default error message.
        }

        throw new Error(message);
      }

      const data = await response.json();

      // Store the backend result so /review can display it.
      sessionStorage.setItem(
        "prescription_review",
        JSON.stringify(data)
      );

      sessionStorage.setItem(
        "prescription_file_name",
        file.name
      );

      setStage("complete");

      // Give the user a moment to see the completed state,
      // then move into the review workspace.
      window.setTimeout(() => {
        window.location.href = "/review";
      }, 500);
    } catch (error) {
      console.error("Prescription processing failed:", error);

      setStage("error");

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "We couldn't process that prescription."
      );
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f3f6f3] text-[#17211d]">

      {/* =====================================================
          PHARMA BACKGROUND
          ===================================================== */}

      <div className="pointer-events-none fixed inset-0 z-0">

        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage:
              "url('/images/pharma-background.png')",
          }}
        />

        <div className="absolute inset-0 bg-[#f3f6f3]/78" />

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(255,255,255,0.75),transparent_32%),radial-gradient(circle_at_85%_65%,rgba(221,235,225,0.65),transparent_38%)]" />

      </div>


      {/* =====================================================
          NAVIGATION
          ===================================================== */}

      <nav className="relative z-30 border-b border-[#dce5df]/70 bg-white/65 backdrop-blur-xl">

        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-10">

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


          <div className="hidden items-center gap-8 text-sm text-[#66736c] md:flex">

            <a
              href="#overview"
              className="transition hover:text-[#17211d]"
            >
              Overview
            </a>

            <a
              href="#review"
              className="transition hover:text-[#17211d]"
            >
              Review
            </a>

            <a
              href="#workflow"
              className="transition hover:text-[#17211d]"
            >
              How it works
            </a>

          </div>


          {/* AUTH */}

          {!user ? (

            <Link
              href="/login"
              className="rounded-full border border-[#d5ded8] bg-white/90 px-5 py-2.5 text-sm font-medium shadow-sm transition hover:border-[#b9c6bd]"
            >
              Sign in
            </Link>

          ) : (

            <div className="relative">

              <button
                onClick={() => setMenuOpen(!menuOpen)}
                className="flex items-center gap-3 rounded-full border border-[#d5ded8] bg-white/90 py-1.5 pl-2 pr-4 shadow-sm"
              >

                <span className="grid h-8 w-8 place-items-center rounded-full bg-[#e2ebe5] text-xs font-semibold text-[#536c5e]">
                  {user.name
                    .split(" ")
                    .map((part) => part[0])
                    .slice(0, 2)
                    .join("")
                    .toUpperCase()}
                </span>

                <span className="hidden text-sm font-medium text-[#34413b] sm:block">
                  {user.name}
                </span>

                <span className="text-xs text-[#7c8982]">
                  {menuOpen ? "↑" : "↓"}
                </span>

              </button>


              {menuOpen && (

                <div className="absolute right-0 top-14 w-64 overflow-hidden rounded-2xl border border-[#dce4df] bg-white p-2 shadow-[0_20px_50px_rgba(30,45,38,0.12)]">

                  <div className="border-b border-[#edf0ee] px-3 py-3">

                    <div className="text-sm font-semibold">
                      {user.name}
                    </div>

                    <div className="mt-1 truncate text-xs text-[#89938e]">
                      {user.email}
                    </div>

                    <div className="mt-2 inline-flex rounded-full bg-[#edf3ee] px-2.5 py-1 text-[10px] font-medium text-[#61766a]">
                      {user.role}
                    </div>

                  </div>


                  <button
                    onClick={() => logout()}
                    className="mt-1 w-full rounded-xl px-3 py-2.5 text-left text-sm font-medium text-[#785b54] transition hover:bg-[#faf4f2]"
                  >
                    Log out
                  </button>

                </div>

              )}

            </div>

          )}

        </div>

      </nav>


      {/* =====================================================
          HERO
          ===================================================== */}

      <section
        id="overview"
        className="relative z-10 mx-auto max-w-7xl px-6 pb-20 pt-14 lg:px-10 lg:pb-28 lg:pt-20"
      >

        <div className="grid items-center gap-14 lg:grid-cols-[1.02fr_.98fr]">


          {/* LEFT */}

          <div>

            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[#d6e1da] bg-white/85 px-3.5 py-2 text-xs font-medium text-[#607269] shadow-sm backdrop-blur">

              <span className="h-1.5 w-1.5 rounded-full bg-[#5e7d6e]" />

              Built around real pharmacy workflows

            </div>


            <h1 className="max-w-2xl text-5xl font-semibold leading-[1.03] tracking-[-0.055em] sm:text-6xl lg:text-[72px]">

              A clearer way to read every prescription.

            </h1>


            <p className="mt-7 max-w-xl text-base leading-7 text-[#68756e] sm:text-lg">

              Turn handwritten and printed prescriptions into
              structured medicine information — giving pharmacists
              and healthcare teams a cleaner starting point for review.

            </p>


            <div className="mt-9 flex flex-wrap gap-3">

              <button
                onClick={chooseFile}
                className="rounded-full bg-[#17211d] px-6 py-3.5 text-sm font-medium text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-[#26332d]"
              >
                Start a prescription review
                <span className="ml-2">→</span>
              </button>


              <a
                href="#workflow"
                className="rounded-full border border-[#d3ddd7] bg-white/90 px-6 py-3.5 text-sm font-medium text-[#34413b] transition hover:border-[#b8c5bc]"
              >
                See how it works
              </a>

            </div>


            <div className="mt-9 flex flex-wrap gap-x-7 gap-y-3 text-xs text-[#748079]">

              <span>✓ OCR extraction</span>

              <span>✓ Medicine normalization</span>

              <span>✓ Human review</span>

            </div>

          </div>


          {/* =================================================
              REVIEW CARD
              ================================================= */}

          <div
            id="review"
            className="relative"
          >

            <div className="absolute -right-3 -top-5 z-10 hidden rounded-2xl border border-[#d9e3dd] bg-white px-4 py-3 shadow-[0_12px_35px_rgba(30,45,38,0.08)] sm:block">

              <div className="flex items-center gap-2">

                <span className="grid h-7 w-7 place-items-center rounded-lg bg-[#eaf1ec] text-xs text-[#5c7466]">
                  Rx
                </span>

                <div>

                  <div className="text-[10px] font-semibold text-[#52635a]">
                    Pharmacy workspace
                  </div>

                  <div className="text-[9px] text-[#96a09b]">
                    Human-reviewed
                  </div>

                </div>

              </div>

            </div>


            <div className="rounded-[30px] border border-[#dce5df] bg-white/95 p-3 shadow-[0_28px_80px_rgba(30,45,38,0.10)] backdrop-blur">

              <div className="rounded-[24px] bg-[#f1f5f2]/95 p-7 sm:p-9">

                <div className="mb-8 flex items-center justify-between">

                  <div>

                    <div className="text-sm font-semibold">
                      Prescription review
                    </div>

                    <div className="mt-1 max-w-sm text-xs leading-5 text-[#89938e]">
                      Upload a prescription and we&apos;ll prepare
                      the medicine information for review.
                    </div>

                  </div>

                  <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white text-sm font-semibold text-[#61776b] shadow-sm">
                    Rx
                  </div>

                </div>


                <input
                  ref={inputRef}
                  type="file"
                  accept=".jpg,.jpeg,.png,.pdf"
                  className="hidden"
                  onChange={(event) => {
                    handleFile(event.target.files?.[0]);

                    // Allows selecting the same file again
                    // after an error.
                    event.currentTarget.value = "";
                  }}
                />


                {/* UPLOAD AREA */}

                <button
                  onClick={chooseFile}
                  disabled={stage === "processing"}
                  className={`group w-full rounded-2xl border border-dashed px-5 py-12 text-center transition ${
                    stage === "error"
                      ? "border-[#d9bdb5] bg-[#fffaf8]"
                      : "border-[#c5d2ca] bg-white hover:border-[#8ea297] hover:bg-[#fcfdfc]"
                  }`}
                >

                  <span className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-[#e9f0eb] text-[#5d7668]">

                    {stage === "processing" ? (

                      <span className="h-5 w-5 animate-spin rounded-full border-2 border-[#b6c6bc] border-t-[#536b5d]" />

                    ) : stage === "complete" ? (

                      <span className="text-lg">✓</span>

                    ) : stage === "error" ? (

                      <span className="text-lg">!</span>

                    ) : (

                      <span className="text-lg">↑</span>

                    )}

                  </span>


                  <span className="block text-sm font-semibold">

                    {stage === "idle" &&
                      "Drop your prescription here"}

                    {stage === "processing" &&
                      "Preparing your prescription…"}

                    {stage === "complete" &&
                      "Prescription ready for review"}

                    {stage === "error" &&
                      "We couldn't process that file"}

                  </span>


                  <span className="mt-2 block text-xs text-[#8a948f]">

                    {stage === "idle"
                      ? "or click to browse from your device"
                      : stage === "error"
                        ? errorMessage
                        : fileName}

                  </span>


                  <span className="mt-5 inline-flex gap-2 text-[10px] font-medium tracking-widest text-[#9aa39f]">

                    JPG
                    <span>•</span>
                    PNG
                    <span>•</span>
                    PDF

                  </span>

                </button>


                <button
                  onClick={chooseFile}
                  disabled={stage === "processing"}
                  className="mt-5 w-full rounded-xl bg-[#dfe9e2] py-3 text-sm font-medium text-[#34413b] transition hover:bg-[#d4e1d8] disabled:cursor-not-allowed disabled:opacity-60"
                >

                  {stage === "processing"
                    ? "Processing prescription…"
                    : "Choose prescription"}

                  {stage !== "processing" && (
                    <span className="ml-1">→</span>
                  )}

                </button>


                <div className="mt-5 flex items-center justify-center gap-2 text-[11px] text-[#89958e]">

                  <span className="grid h-5 w-5 place-items-center rounded-full bg-[#e8efe9] text-[9px] text-[#60766a]">
                    ✓
                  </span>

                  Your prescription stays in a human-reviewed workflow

                </div>

              </div>

            </div>

          </div>

        </div>

      </section>


      {/* =====================================================
          INTELLIGENCE LAYER
          ===================================================== */}

      <section className="relative z-10 border-y border-[#dfe7e2] bg-white/80 backdrop-blur">

        <div className="mx-auto max-w-7xl px-6 py-7 lg:px-10">

          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">

            <div className="flex items-center gap-4">

              <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf3ee] text-xs font-semibold text-[#607568]">
                Rx
              </div>

              <div>

                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#718079]">
                  Medication intelligence layer
                </div>

                <div className="mt-1 text-sm text-[#5e6964]">
                  Prescription image → OCR → structured review
                </div>

              </div>

            </div>


            <div className="flex items-center gap-3 text-[11px] font-medium text-[#738079]">

              <span>OCR</span>

              <span className="text-[#aab3ae]">→</span>

              <span>Normalize</span>

              <span className="text-[#aab3ae]">→</span>

              <span>Review</span>

            </div>

          </div>

        </div>

      </section>


      {/* =====================================================
          WORKFLOW
          ===================================================== */}

      <section
        id="workflow"
        className="relative z-10 mx-auto max-w-7xl px-6 py-24 lg:px-10 lg:py-28"
      >

        <div className="max-w-2xl">

          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[#738078]">
            The workflow
          </div>

          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">
            From prescription image to review-ready data.
          </h2>

          <p className="mt-5 text-base leading-7 text-[#737d78]">
            Upload the prescription, let the intelligence layer
            extract and normalize the medicine information, then
            review the result before it enters a professional workflow.
          </p>

        </div>


        <div className="mt-14 grid gap-5 md:grid-cols-3">

          {[
            {
              number: "01",
              eyebrow: "Read what is written",
              title: "Extract",
              description:
                "Send the prescription to the OCR pipeline and preserve the returned text for review.",
            },
            {
              number: "02",
              eyebrow: "Make names usable",
              title: "Normalize",
              description:
                "Use the medicine vocabulary and confidence-aware matching to turn noisy names into structured candidates.",
            },
            {
              number: "03",
              eyebrow: "Keep people in control",
              title: "Review",
              description:
                "Show medicine details, confidence, and OCR evidence in a workflow designed for human review.",
            },
          ].map((item) => (

            <article
              key={item.number}
              className="group rounded-3xl border border-[#dfe6e1] bg-white/90 p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-[0_20px_50px_rgba(30,45,38,0.07)]"
            >

              <div className="flex items-center justify-between">

                <span className="text-xs font-semibold text-[#89948e]">
                  {item.number}
                </span>

                <span className="text-xs text-[#9aa49f] transition group-hover:translate-x-1">
                  ↗
                </span>

              </div>


              <div className="mt-10 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#839089]">
                {item.eyebrow}
              </div>


              <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em]">
                {item.title}
              </h3>


              <p className="mt-3 text-sm leading-6 text-[#77817c]">
                {item.description}
              </p>

            </article>

          ))}

        </div>

      </section>


      {/* =====================================================
          FOOTER
          ===================================================== */}

      <footer className="relative z-10 border-t border-[#dfe7e2] bg-white/65 px-6 py-8 backdrop-blur lg:px-10">

        <div className="mx-auto flex max-w-7xl flex-col gap-3 text-xs text-[#8a948f] sm:flex-row sm:items-center sm:justify-between">

          <span>
            Prescription Intelligence · Medication intelligence platform
          </span>

          <span>
            AI-assisted · Evidence-aware · Human-reviewed
          </span>

        </div>

      </footer>

    </main>
  );
}