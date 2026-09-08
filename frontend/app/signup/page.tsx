"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function SignUpPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!name || !email || !password || !confirmPassword) {
      setError("Please complete all fields.");
      return;
    }

    if (password.length < 8) {
      setError("Password must contain at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    localStorage.setItem(
      "prescription-intelligence-user",
      JSON.stringify({
        name,
        email,
      })
    );

    router.push("/dashboard");
  }

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center justify-center px-6 py-10">

        <div className="w-full max-w-md">

          <Link href="/" className="mb-8 flex items-center justify-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
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

          <div className="rounded-[28px] border border-[#dfe6e1] bg-white p-8 shadow-[0_25px_70px_rgba(30,45,38,0.07)]">

            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
                Get started
              </div>

              <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
                Create your account
              </h1>

              <p className="mt-2 text-sm leading-6 text-[#7b8580]">
                Create your workspace for prescription review.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-8 space-y-4">

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Full name
                </label>

                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none focus:border-[#82988b]"
                />
              </div>

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Email address
                </label>

                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none focus:border-[#82988b]"
                />
              </div>

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Password
                </label>

                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none focus:border-[#82988b]"
                />
              </div>

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Confirm password
                </label>

                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat your password"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none focus:border-[#82988b]"
                />
              </div>

              {error && (
                <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs text-[#8b5547]">
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="mt-2 w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white hover:bg-[#26332d]"
              >
                Create account →
              </button>
            </form>

            <p className="mt-7 text-center text-sm text-[#737e78]">
              Already have an account?{" "}
              <Link
                href="/sign-in"
                className="font-medium text-[#344f42] hover:underline"
              >
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}