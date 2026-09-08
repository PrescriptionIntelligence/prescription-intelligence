"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { getUser, isAuthenticated, login } from "../../lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isAuthenticated()) {
      window.location.href = "/";
    }
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    const user = getUser();

    if (!user) {
      setError(
        "No account found. Please create an account first."
      );
      return;
    }

    const authenticatedUser = login(email, password);

    if (!authenticatedUser) {
      setError(
        "The email or password you entered is incorrect."
      );
      return;
    }

    window.location.href = "/";
  }

  return (
    <main className="min-h-screen bg-[#f4f7f4] text-[#17211d]">

      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-96 w-96 rounded-full bg-[#dfe9e2] blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-[28rem] w-[28rem] rounded-full bg-[#e5eee8] blur-3xl" />
      </div>

      <header className="relative mx-auto flex max-w-7xl items-center justify-between px-6 py-7 lg:px-10">

        <Link href="/" className="flex items-center gap-3">

          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-sm font-semibold text-white">
            Rx
          </span>

          <div>
            <div className="text-[15px] font-semibold tracking-[-0.02em]">
              Prescription Intelligence
            </div>

            <div className="text-[10px] uppercase tracking-[0.2em] text-[#82908a]">
              Medication intelligence
            </div>
          </div>

        </Link>

        <Link
          href="/signup"
          className="rounded-full border border-[#d7dfda] bg-white px-5 py-2.5 text-sm font-medium shadow-sm transition hover:border-[#bdc9c1]"
        >
          Create account
        </Link>

      </header>


      <section className="relative flex min-h-[calc(100vh-100px)] items-center justify-center px-6 pb-16">

        <div className="w-full max-w-md">

          <div className="mb-8 text-center">

            <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-[#d9e2dc] bg-white text-lg font-semibold text-[#587062] shadow-sm">
              Rx
            </div>

            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#718078]">
              Pharmacy workspace
            </p>

            <h1 className="text-4xl font-semibold tracking-[-0.045em]">
              Welcome back.
            </h1>

            <p className="mt-3 text-sm leading-6 text-[#78837d]">
              Sign in to continue reviewing prescription
              intelligence.
            </p>

          </div>


          <div className="rounded-[28px] border border-[#dfe6e1] bg-white p-7 shadow-[0_24px_70px_rgba(30,45,38,0.08)] sm:p-9">

            <form
              onSubmit={handleSubmit}
              className="space-y-5"
            >

              <div>

                <label
                  htmlFor="email"
                  className="mb-2 block text-xs font-semibold text-[#46534d]"
                >
                  Email address
                </label>

                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  placeholder="you@example.com"
                  autoComplete="email"
                  className="w-full rounded-xl border border-[#dce4df] bg-[#fafcfb] px-4 py-3.5 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#8da197] focus:bg-white focus:ring-4 focus:ring-[#edf2ee]"
                />

              </div>


              <div>

                <div className="mb-2 flex items-center justify-between">

                  <label
                    htmlFor="password"
                    className="text-xs font-semibold text-[#46534d]"
                  >
                    Password
                  </label>

                  <button
                    type="button"
                    className="text-xs text-[#718078] hover:text-[#17211d]"
                  >
                    Forgot password?
                  </button>

                </div>

                <div className="relative">

                  <input
                    id="password"
                    type={
                      showPassword
                        ? "text"
                        : "password"
                    }
                    value={password}
                    onChange={(event) =>
                      setPassword(event.target.value)
                    }
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    className="w-full rounded-xl border border-[#dce4df] bg-[#fafcfb] px-4 py-3.5 pr-20 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#8da197] focus:bg-white focus:ring-4 focus:ring-[#edf2ee]"
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowPassword(!showPassword)
                    }
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg px-2 py-1 text-xs font-medium text-[#718078] hover:bg-[#eef3ef]"
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>

                </div>

              </div>


              {error && (
                <div className="rounded-xl border border-[#ead9d4] bg-[#fbf5f3] px-4 py-3 text-xs leading-5 text-[#855c52]">
                  {error}
                </div>
              )}


              <button
                type="submit"
                className="w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-semibold text-white transition hover:-translate-y-0.5 hover:bg-[#26332d]"
              >
                Sign in
                <span className="ml-2">→</span>
              </button>

            </form>


            <div className="my-7 flex items-center gap-4">

              <div className="h-px flex-1 bg-[#e6ebe7]" />

              <span className="text-[10px] uppercase tracking-[0.15em] text-[#a0aaa5]">
                secure workspace
              </span>

              <div className="h-px flex-1 bg-[#e6ebe7]" />

            </div>


            <div className="text-center">

              <p className="text-sm text-[#7a847f]">
                Don&apos;t have an account?
              </p>

              <Link
                href="/signup"
                className="mt-2 inline-block text-sm font-semibold text-[#536b5e] transition hover:text-[#17211d]"
              >
                Create your account →
              </Link>

            </div>

          </div>


          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-[#dfe6e1] bg-white/70 p-4">

            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[#edf2ee] text-xs text-[#5f7669]">
              ✓
            </div>

            <p className="text-[11px] leading-5 text-[#7c8781]">
              Prescription Intelligence is designed to
              support pharmacy and healthcare workflows.
              AI-generated information should always remain
              subject to professional review.
            </p>

          </div>

        </div>

      </section>

    </main>
  );
}