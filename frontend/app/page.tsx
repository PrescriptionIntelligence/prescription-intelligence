"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getUser, isAuthenticated, logout, User } from "../lib/auth";

export default function Home() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    // Read from localStorage only on the client.
    // Use Promise.resolve to defer setState and avoid the
    // react-hooks/set-state-in-effect rule.
    if (isAuthenticated()) {
      const stored = getUser();
      if (stored) Promise.resolve().then(() => setUser(stored));
    }
  }, []);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f3f6f3] text-[#17211d]">

      {/* Background */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/images/pharma-background.png')" }}
        />
        <div className="absolute inset-0 bg-[#f3f6f3]/82" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(255,255,255,0.75),transparent_32%),radial-gradient(circle_at_85%_65%,rgba(221,235,225,0.65),transparent_38%)]" />
      </div>

      {/* =====================================================
          HEADER
          ===================================================== */}

      <header className="relative z-10 border-b border-[#dde5de]/60 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">

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

          <nav className="hidden items-center gap-7 md:flex">
            <a href="#how-it-works" className="text-xs text-[#637069] hover:text-[#17211d] transition">
              How it works
            </a>
            <a href="#features" className="text-xs text-[#637069] hover:text-[#17211d] transition">
              Features
            </a>
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                <Link
                  href="/dashboard"
                  className="hidden rounded-xl border border-[#d0d8d3] bg-white px-4 py-2 text-xs font-medium text-[#53625a] hover:border-[#b0bcb7] transition sm:inline-flex"
                >
                  Dashboard
                </Link>
                <button
                  onClick={logout}
                  className="text-xs text-[#8a948f] hover:text-[#17211d] transition"
                >
                  Sign out
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/sign-in"
                  className="hidden text-xs text-[#637069] hover:text-[#17211d] transition sm:block"
                >
                  Sign in
                </Link>
                <Link
                  href="/analyze"
                  className="rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-medium text-white hover:bg-[#26332d] transition"
                >
                  Try free
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* =====================================================
          HERO
          ===================================================== */}

      <section className="relative z-10 mx-auto max-w-7xl px-6 py-20 md:py-28">

        <div className="mx-auto max-w-3xl text-center">

          <div className="mb-6 inline-flex rounded-full border border-[#d0dcd5] bg-white/80 px-3.5 py-2 text-xs text-[#5a7265]">
            ✦ AI-powered · Confidence-aware · Human-reviewed
          </div>

          <h1 className="text-5xl font-semibold leading-[1.07] tracking-[-0.05em] md:text-6xl">
            Understand every
            <br />
            <span className="text-[#3d6b55]">prescription</span> with clarity.
          </h1>

          <p className="mx-auto mt-7 max-w-xl text-base leading-7 text-[#5a7065]">
            Prescription Intelligence turns prescription images into structured,
            reviewed medicine data — with AI-extracted medicines, confidence
            scoring, and safety analysis built in.
          </p>

          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Link
              href="/analyze"
              className="rounded-xl bg-[#17211d] px-7 py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d]"
            >
              Analyze a prescription →
            </Link>
            <a
              href="#how-it-works"
              className="rounded-xl border border-[#c8d4cc] bg-white/80 px-7 py-3.5 text-sm font-medium text-[#3a4f45] transition hover:border-[#a0b0a8]"
            >
              How it works
            </a>
          </div>
        </div>

      </section>

      {/* =====================================================
          HOW IT WORKS
          ===================================================== */}

      <section id="how-it-works" className="relative z-10 border-t border-[#dde5de]/50 bg-white/60 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-6 py-20">

          <div className="mb-12 text-center">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[#77847d]">
              The pipeline
            </div>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              How it works
            </h2>
            <p className="mt-3 text-sm leading-6 text-[#6b7870]">
              A multi-stage AI pipeline processes each prescription image.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                num: "01",
                title: "Image upload & preprocessing",
                desc: "Upload a JPG or PNG prescription image. The system preprocesses it for optimal OCR quality — grayscale conversion, contrast enhancement, and sharpening.",
              },
              {
                num: "02",
                title: "Multi-mode OCR",
                desc: "Tesseract runs across multiple page-segmentation modes and the highest-quality output is selected automatically. OCR quality is scored and reported.",
              },
              {
                num: "03",
                title: "Medicine candidate detection",
                desc: "The extracted text is scanned for prescription markers (Tab, Cap, Inj, etc.) and strength patterns to identify likely medicine entries.",
              },
              {
                num: "04",
                title: "Medicine normalization",
                desc: "Each candidate is matched against a curated medicine vocabulary using fuzzy matching. A confidence score is produced for every identification.",
              },
              {
                num: "05",
                title: "Confidence scoring",
                desc: "Every medicine receives extraction and normalization confidence scores. Uncertain identifications are explicitly flagged for review.",
              },
              {
                num: "06",
                title: "Safety analysis",
                desc: "Duplicate medicine detection, known drug-drug interactions, dose anomalies, and structural validation are all checked and reported.",
              },
            ].map((step) => (
              <div key={step.num} className="rounded-2xl border border-[#dfe6e1] bg-white p-7">
                <div className="mb-4 font-mono text-2xl font-semibold text-[#c8d4cc]">
                  {step.num}
                </div>
                <h3 className="text-sm font-semibold">{step.title}</h3>
                <p className="mt-2.5 text-xs leading-5 text-[#6b7870]">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* =====================================================
          FEATURES
          ===================================================== */}

      <section id="features" className="relative z-10 border-t border-[#dde5de]/50">
        <div className="mx-auto max-w-7xl px-6 py-20">

          <div className="mb-12 text-center">
            <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[#77847d]">
              Key capabilities
            </div>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              Built for pharmacy workflows
            </h2>
          </div>

          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {[
              {
                icon: "↑",
                title: "Prescription upload",
                desc: "Drag-and-drop or browse to upload JPG/PNG images up to 10 MB.",
              },
              {
                icon: "◎",
                title: "OCR + extraction",
                desc: "Multi-mode Tesseract OCR with automatic quality scoring and best-result selection.",
              },
              {
                icon: "≋",
                title: "Medicine normalization",
                desc: "Fuzzy vocabulary matching with confidence scores. Uncertain identifications are never silently accepted.",
              },
              {
                icon: "⚑",
                title: "Safety intelligence",
                desc: "Duplicate detection, drug interactions, dose anomaly checks, and structural validation.",
              },
            ].map((feature) => (
              <div key={feature.title} className="rounded-2xl border border-[#dfe6e1] bg-white p-7">
                <div className="mb-4 grid h-11 w-11 place-items-center rounded-xl bg-[#edf3ef] text-lg text-[#587163]">
                  {feature.icon}
                </div>
                <h3 className="text-sm font-semibold">{feature.title}</h3>
                <p className="mt-2 text-xs leading-5 text-[#6b7870]">{feature.desc}</p>
              </div>
            ))}
          </div>

        </div>
      </section>

      {/* =====================================================
          DISCLAIMER + CTA
          ===================================================== */}

      <section className="relative z-10 border-t border-[#dde5de]/50 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto max-w-4xl px-6 py-16 text-center">

          <h2 className="text-2xl font-semibold tracking-[-0.04em]">
            Ready to analyze a prescription?
          </h2>
          <p className="mt-4 text-sm leading-6 text-[#6b7870]">
            Upload a clear prescription image and get a structured analysis
            with medicine data, confidence scores, and safety findings.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/analyze"
              className="rounded-xl bg-[#17211d] px-8 py-3.5 text-sm font-medium text-white hover:bg-[#26332d] transition"
            >
              Analyze prescription →
            </Link>
            {!user && (
              <Link
                href="/sign-up"
                className="rounded-xl border border-[#c8d4cc] bg-white px-8 py-3.5 text-sm font-medium text-[#3a4f45] hover:border-[#a0b0a8] transition"
              >
                Create account
              </Link>
            )}
          </div>

          <div className="mt-12 rounded-2xl border border-[#dfe6e1] bg-white/80 p-6 text-left text-xs leading-6 text-[#6b7870]">
            <strong className="text-[#17211d]">Medical disclaimer:</strong>{" "}
            Prescription Intelligence is a decision-support tool designed to
            assist qualified healthcare professionals and pharmacists. It is{" "}
            <strong>not</strong> a substitute for professional pharmacist review,
            clinical judgment, or authoritative drug databases. All AI output
            must be verified by a qualified professional before any clinical
            action. Uncertain identifications are explicitly flagged and should
            never be dispensed without verification.
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-[#dde5de]/50 px-6 py-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-[#17211d] text-[9px] font-semibold text-white">
              Rx
            </span>
            <span className="text-xs text-[#8a948f]">
              Prescription Intelligence
            </span>
          </div>
          <div className="flex gap-5 text-xs text-[#a0aaa5]">
            <Link href="/sign-in" className="hover:text-[#17211d] transition">Sign in</Link>
            <Link href="/sign-up" className="hover:text-[#17211d] transition">Sign up</Link>
            <Link href="/analyze" className="hover:text-[#17211d] transition">Analyze</Link>
          </div>
        </div>
      </footer>

    </main>
  );
}
