"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type User = {
  name: string;
  email: string;
};

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(
      "prescription-intelligence-user"
    );

    if (!stored) {
      router.replace("/sign-in");
      return;
    }

    setUser(JSON.parse(stored));
  }, [router]);

  function logout() {
    localStorage.removeItem("prescription-intelligence-user");
    router.push("/");
  }

  if (!user) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f6f3]">
        <div className="text-sm text-[#718078]">
          Loading workspace…
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">

      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">

          <Link href="/" className="flex items-center gap-3">
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

          <div className="flex items-center gap-4">

            <div className="hidden text-right sm:block">
              <div className="text-xs font-medium">
                {user.name}
              </div>

              <div className="text-[10px] text-[#8a948f]">
                {user.email}
              </div>
            </div>

            <button
              onClick={logout}
              className="rounded-xl border border-[#dce3de] bg-white px-4 py-2 text-xs font-medium text-[#53625a] hover:border-[#bbc7bf]"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-12">

        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
            Your workspace
          </div>

          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">
            Good to see you, {user.name}.
          </h1>

          <p className="mt-3 max-w-xl text-sm leading-6 text-[#737e78]">
            Review prescriptions, inspect extracted medicine information,
            and keep human verification in the loop.
          </p>
        </div>

        <div className="mt-10 grid gap-5 md:grid-cols-3">

          <Link
            href="/"
            className="group rounded-3xl border border-[#dfe6e1] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
          >
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#edf3ef] text-[#587163]">
              +
            </div>

            <h2 className="mt-7 text-xl font-semibold">
              New prescription review
            </h2>

            <p className="mt-2 text-sm leading-6 text-[#7b8580]">
              Upload a prescription and prepare its medicine information
              for review.
            </p>

            <div className="mt-6 text-xs font-medium text-[#526c5d]">
              Start review →
            </div>
          </Link>

          <div className="rounded-3xl border border-[#dfe6e1] bg-white p-7">
            <div className="text-xs uppercase tracking-[0.16em] text-[#89938e]">
              Reviews
            </div>

            <div className="mt-5 text-4xl font-semibold">
              0
            </div>

            <p className="mt-2 text-sm text-[#7b8580]">
              Prescription reviews
            </p>
          </div>

          <div className="rounded-3xl border border-[#dfe6e1] bg-white p-7">
            <div className="text-xs uppercase tracking-[0.16em] text-[#89938e]">
              Review status
            </div>

            <div className="mt-5 flex items-center gap-2 text-sm font-medium">
              <span className="h-2 w-2 rounded-full bg-[#6d8b78]" />
              Human review enabled
            </div>

            <p className="mt-3 text-sm leading-6 text-[#7b8580]">
              AI output remains supporting evidence.
            </p>
          </div>

        </div>
      </section>
    </main>
  );
}