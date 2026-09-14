"use client";

import Link from "next/link";

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-sm font-semibold text-white">
        Rx
      </span>

      <div>
        <div className="text-sm font-semibold text-[#17211d]">
          Prescription Intelligence
        </div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-[#82908a]">
          Medication intelligence
        </div>
      </div>
    </Link>
  );
}

export default function SignUpPage() {
  return (
    <main className="min-h-screen bg-[#f4f7f5] text-[#17211d]">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-8">

        <header className="flex items-center justify-between">
          <Brand />

          <Link
            href="/sign-in"
            className="text-sm text-[#66736c] transition hover:text-[#17211d]"
          >
            Sign in
          </Link>
        </header>

        <div className="flex flex-1 items-center justify-center py-14">
          <section className="w-full max-w-4xl">

            <div className="mx-auto max-w-2xl text-center">
              <div className="text-xs font-semibold uppercase tracking-[0.2em] text-[#77847d]">
                Get started
              </div>

              <h1 className="mt-4 text-4xl font-semibold tracking-[-0.05em] sm:text-5xl">
                Choose how you use Rx.
              </h1>

              <p className="mx-auto mt-5 max-w-xl text-sm leading-6 text-[#707b75]">
                Choose the workspace that matches your role. You can always
                sign in later with the same account.
              </p>
            </div>

            <div className="mt-12 grid gap-5 md:grid-cols-2">

              {/* Pharmacy */}
              <Link
                href="/signup/pharmacy"
                className="group rounded-[26px] border border-[#dfe6e1] bg-white p-7 shadow-[0_18px_55px_rgba(30,45,38,0.05)] transition hover:-translate-y-0.5 hover:border-[#c5d2ca] hover:shadow-[0_25px_65px_rgba(30,45,38,0.09)]"
              >
                <div className="flex items-start justify-between">
                  <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#edf8f1] text-[#35664d]">
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.7"
                    >
                      <path d="M4 21h16" />
                      <path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" />
                      <path d="M9 7h6" />
                      <path d="M9 11h2" />
                      <path d="M13 11h2" />
                      <path d="M9 15h2" />
                      <path d="M13 15h2" />
                    </svg>
                  </div>

                  <span className="text-xl text-[#9aa39e] transition group-hover:translate-x-1 group-hover:text-[#35664d]">
                    →
                  </span>
                </div>

                <div className="mt-7">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#77847d]">
                    Pharmacy
                  </div>

                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                    Pharmacy workspace
                  </h2>

                  <p className="mt-3 text-sm leading-6 text-[#707b75]">
                    For pharmacists and pharmacy teams managing prescriptions,
                    customers and medication safety reviews.
                  </p>
                </div>

                <div className="mt-7 flex items-center gap-2 text-sm font-medium text-[#344f42]">
                  Create pharmacy account
                  <span className="transition group-hover:translate-x-1">
                    →
                  </span>
                </div>
              </Link>

              {/* Customer */}
              <Link
                href="/signup/customer"
                className="group rounded-[26px] border border-[#dfe6e1] bg-white p-7 shadow-[0_18px_55px_rgba(30,45,38,0.05)] transition hover:-translate-y-0.5 hover:border-[#c5d2ca] hover:shadow-[0_25px_65px_rgba(30,45,38,0.09)]"
              >
                <div className="flex items-start justify-between">
                  <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#f4f7f5] text-[#526158]">
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.7"
                    >
                      <circle cx="12" cy="8" r="3.5" />
                      <path d="M5 21c.8-4.1 3.1-6.2 7-6.2s6.2 2.1 7 6.2" />
                    </svg>
                  </div>

                  <span className="text-xl text-[#9aa39e] transition group-hover:translate-x-1 group-hover:text-[#526158]">
                    →
                  </span>
                </div>

                <div className="mt-7">
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#77847d]">
                    Customer
                  </div>

                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">
                    Customer account
                  </h2>

                  <p className="mt-3 text-sm leading-6 text-[#707b75]">
                    View your prescriptions, medicines, safety information and
                    connected pharmacy records.
                  </p>
                </div>

                <div className="mt-7 flex items-center gap-2 text-sm font-medium text-[#344f42]">
                  Create customer account
                  <span className="transition group-hover:translate-x-1">
                    →
                  </span>
                </div>
              </Link>
            </div>

            {/* Admin */}
            <div className="mx-auto mt-7 max-w-2xl rounded-2xl border border-[#e2e7e4] bg-[#fafcfb] px-5 py-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-xs font-medium text-[#526158]">
                    Authorized administrator
                  </div>
                  <p className="mt-1 text-[11px] leading-5 text-[#89948e]">
                    Administrator accounts are provisioned separately and
                    cannot be created through public registration.
                  </p>
                </div>

                <Link
                  href="/admin/login"
                  className="shrink-0 text-xs font-medium text-[#344f42] hover:underline"
                >
                  Admin sign in →
                </Link>
              </div>
            </div>

            <p className="mt-8 text-center text-sm text-[#737e78]">
              Already have an account?{" "}
              <Link
                href="/sign-in"
                className="font-medium text-[#344f42] hover:underline"
              >
                Sign in
              </Link>
            </p>
          </section>
        </div>

        <p className="text-center text-[11px] leading-5 text-[#929b96]">
          Prescription Intelligence supports medication review workflows and
          does not replace professional clinical judgment.
        </p>
      </div>
    </main>
  );
}
