"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login, getRoleHome } from "../../lib/auth";

export default function SignInPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);

    try {
      const result = await login(email.trim(), password);

      // Role comes from the authenticated account.
      // Never let the login form decide the user's role.
      router.push(getRoleHome(result.user));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Sign in failed. Please check your credentials and try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f7f5] text-[#17211d]">
      <div className="mx-auto flex min-h-screen max-w-7xl">

        {/* Brand / product panel */}
        <section className="hidden flex-1 flex-col justify-between p-10 lg:flex">
          <Link href="/" className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-sm font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[10px] uppercase tracking-[0.18em] text-[#82908a]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <div className="max-w-lg pb-10">
            <div className="mb-5 inline-flex rounded-full border border-[#d7e0da] bg-white px-3 py-2 text-xs text-[#627269]">
              ✦ Built around real pharmacy workflows
            </div>

            <h1 className="text-5xl font-semibold leading-[1.05] tracking-[-0.05em]">
              A clearer way to review every prescription.
            </h1>

            <p className="mt-6 max-w-md text-sm leading-6 text-[#707b75]">
              Prescription Intelligence turns prescription images into
              structured, review-ready medicine data with medication safety
              decision support.
            </p>

            <div className="mt-8 grid max-w-md grid-cols-3 gap-3">
              <div className="border-l border-[#d7e0da] pl-3">
                <div className="text-sm font-semibold">Pharmacy</div>
                <div className="mt-1 text-[11px] leading-4 text-[#7c8881]">
                  Review prescriptions
                </div>
              </div>

              <div className="border-l border-[#d7e0da] pl-3">
                <div className="text-sm font-semibold">Customer</div>
                <div className="mt-1 text-[11px] leading-4 text-[#7c8881]">
                  View prescriptions
                </div>
              </div>

              <div className="border-l border-[#d7e0da] pl-3">
                <div className="text-sm font-semibold">Safety</div>
                <div className="mt-1 text-[11px] leading-4 text-[#7c8881]">
                  Human review
                </div>
              </div>
            </div>
          </div>

          <p className="text-xs text-[#8b9690]">
            AI-assisted · Evidence-aware · Human-reviewed
          </p>
        </section>

        {/* Authentication panel */}
        <section className="flex w-full items-center justify-center px-6 py-10 lg:w-[500px] lg:px-10">
          <div className="w-full max-w-sm">

            <Link
              href="/"
              className="mb-10 flex items-center gap-3 lg:hidden"
            >
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
                Rx
              </span>

              <span className="text-sm font-semibold">
                Prescription Intelligence
              </span>
            </Link>

            <div className="rounded-[28px] border border-[#dfe6e1] bg-white p-7 shadow-[0_25px_70px_rgba(30,45,38,0.07)] sm:p-9">

              <div>
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
                  Secure access
                </div>

                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
                  Sign in
                </h2>

                <p className="mt-2 text-sm leading-6 text-[#7b8580]">
                  Continue to your prescription workspace.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="mt-8 space-y-5">

                <div>
                  <label className="mb-2 block text-xs font-medium text-[#46534c]">
                    Email address
                  </label>

                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    disabled={loading}
                    className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                  />
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-xs font-medium text-[#46534c]">
                      Password
                    </label>

                    <Link
                      href="/forgot-password"
                      className="text-xs text-[#627b6d] hover:text-[#17211d]"
                    >
                      Forgot password?
                    </Link>
                  </div>

                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder="Enter your password"
                      autoComplete="current-password"
                      disabled={loading}
                      className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 pr-20 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                    />

                    <button
                      type="button"
                      onClick={() => setShowPassword((value) => !value)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#718078] hover:text-[#17211d]"
                    >
                      {showPassword ? "Hide" : "Show"}
                    </button>
                  </div>
                </div>

                {error && (
                  <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs leading-5 text-[#8b5547]">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? "Signing in…" : "Sign in →"}
                </button>
              </form>

              <div className="my-7 flex items-center gap-3">
                <div className="h-px flex-1 bg-[#e7ebe8]" />

                <span className="text-[10px] uppercase tracking-widest text-[#a0aaa5]">
                  new here
                </span>

                <div className="h-px flex-1 bg-[#e7ebe8]" />
              </div>

              <Link
                href="/sign-up"
                className="flex w-full items-center justify-between rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 py-3.5 text-sm font-medium text-[#344f42] transition hover:border-[#bdcbc2] hover:bg-[#f5f8f6]"
              >
                <span>Create an account</span>
                <span>→</span>
              </Link>

              <div className="mt-6 border-t border-[#edf0ee] pt-5 text-center">
                <Link
                  href="/admin/login"
                  className="text-[11px] text-[#89948e] transition hover:text-[#344f42]"
                >
                  Authorized administrator? Admin sign in
                </Link>
              </div>
            </div>

            <p className="mt-6 text-center text-[11px] leading-5 text-[#929b96]">
              Prescription Intelligence supports medication review workflows
              and does not replace professional clinical judgment.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}