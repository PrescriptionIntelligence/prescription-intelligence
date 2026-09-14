"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Loader2,
  Mail,
  MailCheck,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  resendVerification,
  verifyEmail,
} from "../../lib/auth";

type VerificationState =
  | "pending"
  | "verifying"
  | "success"
  | "expired"
  | "invalid"
  | "error";

const RESEND_COOLDOWN_SECONDS = 60;
const RESEND_COOLDOWN_KEY =
  "prescription-intelligence-email-resend-cooldown";

export default function VerifyEmailPage() {
  const router = useRouter();

  const [state, setState] =
    useState<VerificationState>("pending");

  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");

  const [message, setMessage] = useState(
    "Check your inbox for the verification email."
  );

  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState("");
  const [cooldown, setCooldown] = useState(0);

  /*
   * Restore the resend cooldown after a refresh.
   *
   * The backend remains authoritative. This is only a UX layer
   * to prevent the user from repeatedly clicking the button.
   */
  useEffect(() => {
    const stored =
      window.sessionStorage.getItem(
        RESEND_COOLDOWN_KEY
      );

    if (!stored) {
      return;
    }

    const expiresAt = Number(stored);

    if (!Number.isFinite(expiresAt)) {
      window.sessionStorage.removeItem(
        RESEND_COOLDOWN_KEY
      );
      return;
    }

    const remaining = Math.ceil(
      (expiresAt - Date.now()) / 1000
    );

    if (remaining > 0) {
      setCooldown(remaining);
    } else {
      window.sessionStorage.removeItem(
        RESEND_COOLDOWN_KEY
      );
    }
  }, []);

  /*
   * Countdown timer.
   */
  useEffect(() => {
    if (cooldown <= 0) {
      return;
    }

    const timer = window.setInterval(() => {
      setCooldown((current) => {
        if (current <= 1) {
          window.sessionStorage.removeItem(
            RESEND_COOLDOWN_KEY
          );

          window.clearInterval(timer);
          return 0;
        }

        return current - 1;
      });
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [cooldown]);

  /*
   * Read verification parameters and automatically verify
   * when a valid verification link is opened.
   */
  useEffect(() => {
    const params = new URLSearchParams(
      window.location.search
    );

    const urlEmail = params.get("email") || "";
    const urlToken = params.get("token") || "";

    setEmail(urlEmail);
    setToken(urlToken);

    // Signup sends the user here without a token.
    // Show the pending verification state.
    if (!urlEmail || !urlToken) {
      setState("pending");
      return;
    }

    let cancelled = false;

    async function verify() {
      setState("verifying");
      setMessage("Verifying your email address...");

      try {
        const result = await verifyEmail(
          urlEmail,
          urlToken
        );

        if (cancelled) {
          return;
        }

        if (result.email_verified) {
          setState("success");
          setMessage(
            result.message ||
              "Your email address has been verified successfully."
          );

          // Verification succeeded, so any old resend
          // cooldown is no longer relevant.
          window.sessionStorage.removeItem(
            RESEND_COOLDOWN_KEY
          );
          setCooldown(0);
        } else {
          setState("error");
          setMessage(
            "Your email could not be verified. Please request a new verification email."
          );
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        const errorMessage =
          error instanceof Error
            ? error.message
            : "Email verification failed.";

        if (
          errorMessage
            .toLowerCase()
            .includes("expired")
        ) {
          setState("expired");
          setMessage(errorMessage);
        } else {
          setState("invalid");
          setMessage(errorMessage);
        }
      }
    }

    verify();

    return () => {
      cancelled = true;
    };
  }, []);

  function startResendCooldown() {
    const expiresAt =
      Date.now() +
      RESEND_COOLDOWN_SECONDS * 1000;

    window.sessionStorage.setItem(
      RESEND_COOLDOWN_KEY,
      String(expiresAt)
    );

    setCooldown(RESEND_COOLDOWN_SECONDS);
  }

  async function handleResend() {
    if (!email || resending || cooldown > 0) {
      return;
    }

    setResending(true);
    setResendMessage("");

    try {
      const result =
        await resendVerification(email);

      setResendMessage(
        result.message ||
          "If an account exists for this email, a new verification email has been sent."
      );

      startResendCooldown();
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Unable to resend the verification email.";

      setResendMessage(errorMessage);

      /*
       * If the backend rejected the request because of
       * the resend cooldown, lock the UI as well.
       */
      if (
        errorMessage
          .toLowerCase()
          .includes("wait before requesting")
      ) {
        startResendCooldown();
      }
    } finally {
      setResending(false);
    }
  }

  function goToSignIn() {
    router.push("/sign-in");
  }

  const showResend =
    state === "pending" ||
    state === "expired" ||
    state === "invalid" ||
    state === "error";

  const resendDisabled =
    resending || cooldown > 0;

  function renderResendButton(
    label: string
  ) {
    return (
      <button
        type="button"
        onClick={handleResend}
        disabled={resendDisabled}
        className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-[#DFE6E1] bg-white px-6 text-sm font-medium text-[#17211D] transition hover:bg-[#FAFCFB] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {resending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Sending...
          </>
        ) : cooldown > 0 ? (
          <>
            <RefreshCw className="h-4 w-4" />
            Resend available in {cooldown}s
          </>
        ) : (
          <>
            <RefreshCw className="h-4 w-4" />
            {label}
          </>
        )}
      </button>
    );
  }

  return (
    <main className="min-h-screen bg-[#F4F7F5] px-6 py-12 text-[#17211D]">
      <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-xl items-center justify-center">
        <section className="w-full overflow-hidden rounded-3xl border border-[#DFE6E1] bg-white shadow-[0_24px_70px_rgba(23,33,29,0.08)]">

          {/* Header */}
          <div className="border-b border-[#DFE6E1] bg-[#FAFCFB] px-8 py-7">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#17211D] text-white">
                <span className="text-lg font-semibold">
                  Rx
                </span>
              </div>

              <div>
                <p className="text-sm font-semibold tracking-tight">
                  Prescription Intelligence
                </p>

                <p className="text-xs text-[#7C8881]">
                  Account verification
                </p>
              </div>
            </div>
          </div>

          {/* Pending */}
          {state === "pending" && (
            <div className="px-8 py-12 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#EDF8F1] text-[#35664D]">
                <Mail className="h-8 w-8" />
              </div>

              <h1 className="mt-7 text-2xl font-semibold tracking-tight">
                Check your email
              </h1>

              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#526158]">
                We&apos;ve created your account. Before you
                can sign in, verify your email address using
                the link we sent to your inbox.
              </p>

              {email && (
                <div className="mx-auto mt-6 flex max-w-md items-center justify-center gap-2 rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] px-4 py-3 text-sm text-[#35664D]">
                  <MailCheck className="h-4 w-4 shrink-0" />
                  <span className="truncate">
                    {email}
                  </span>
                </div>
              )}

              <div className="mx-auto mt-7 max-w-md rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] p-5 text-left">
                <p className="text-sm font-medium text-[#17211D]">
                  What to do next
                </p>

                <ol className="mt-3 space-y-3 text-sm leading-5 text-[#526158]">
                  <li className="flex gap-3">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#17211D] text-[11px] font-semibold text-white">
                      1
                    </span>
                    <span>
                      Open the verification email.
                    </span>
                  </li>

                  <li className="flex gap-3">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#17211D] text-[11px] font-semibold text-white">
                      2
                    </span>
                    <span>
                      Click the secure verification link.
                    </span>
                  </li>

                  <li className="flex gap-3">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#17211D] text-[11px] font-semibold text-white">
                      3
                    </span>
                    <span>
                      Return here and sign in to your account.
                    </span>
                  </li>
                </ol>
              </div>

              {email && (
                <div className="mt-7">
                  {renderResendButton(
                    "Resend verification email"
                  )}
                </div>
              )}

              {resendMessage && (
                <p className="mx-auto mt-4 max-w-md text-xs leading-5 text-[#526158]">
                  {resendMessage}
                </p>
              )}

              <div className="mt-8">
                <button
                  type="button"
                  onClick={goToSignIn}
                  className="text-sm font-medium text-[#35664D] hover:underline"
                >
                  Already verified? Sign in
                </button>
              </div>
            </div>
          )}

          {/* Verifying */}
          {state === "verifying" && (
            <div className="px-8 py-12 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#EDF8F1] text-[#35664D]">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>

              <h1 className="mt-7 text-2xl font-semibold tracking-tight">
                Verifying your email
              </h1>

              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#526158]">
                Please wait while we securely verify your
                email address.
              </p>
            </div>
          )}

          {/* Success */}
          {state === "success" && (
            <div className="px-8 py-12 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#EDF8F1] text-[#35664D]">
                <CheckCircle2 className="h-8 w-8" />
              </div>

              <h1 className="mt-7 text-2xl font-semibold tracking-tight">
                Email verified
              </h1>

              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#526158]">
                {message}
              </p>

              {email && (
                <div className="mx-auto mt-6 inline-flex max-w-full items-center gap-2 rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] px-4 py-3 text-sm text-[#35664D]">
                  <MailCheck className="h-4 w-4 shrink-0" />
                  <span className="truncate">
                    {email}
                  </span>
                </div>
              )}

              <div className="mt-8">
                <button
                  type="button"
                  onClick={goToSignIn}
                  className="inline-flex h-11 items-center justify-center rounded-xl bg-[#17211D] px-6 text-sm font-medium text-white transition hover:bg-[#26352E]"
                >
                  Continue to sign in
                </button>
              </div>

              <div className="mt-8 flex items-center justify-center gap-2 text-xs text-[#7C8881]">
                <ShieldCheck className="h-4 w-4 text-[#35664D]" />
                <span>
                  Email ownership confirmed.
                </span>
              </div>
            </div>
          )}

          {/* Failure */}
          {(state === "expired" ||
            state === "invalid" ||
            state === "error") && (
            <div className="px-8 py-12 text-center">
              <div
                className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full ${
                  state === "expired"
                    ? "bg-[#FFF7DF] text-[#A47B2C]"
                    : "bg-[#FFF0F0] text-[#A74646]"
                }`}
              >
                {state === "expired" ? (
                  <RefreshCw className="h-8 w-8" />
                ) : (
                  <XCircle className="h-8 w-8" />
                )}
              </div>

              <h1 className="mt-7 text-2xl font-semibold tracking-tight">
                {state === "expired"
                  ? "Verification link expired"
                  : "Verification unsuccessful"}
              </h1>

              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#526158]">
                {message}
              </p>

              {email && (
                <div className="mx-auto mt-6 inline-flex max-w-full items-center gap-2 rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 py-3 text-sm text-[#526158]">
                  <MailCheck className="h-4 w-4 shrink-0" />
                  <span className="truncate">
                    {email}
                  </span>
                </div>
              )}

              {showResend && email && (
                <>
                  <div className="mt-8">
                    {renderResendButton(
                      "Send new verification email"
                    )}
                  </div>

                  {resendMessage && (
                    <p className="mx-auto mt-4 max-w-md text-xs leading-5 text-[#526158]">
                      {resendMessage}
                    </p>
                  )}
                </>
              )}

              <div className="mt-8">
                <button
                  type="button"
                  onClick={goToSignIn}
                  className="text-sm font-medium text-[#35664D] hover:underline"
                >
                  Return to sign in
                </button>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="border-t border-[#DFE6E1] bg-[#FAFCFB] px-8 py-5 text-center text-xs leading-5 text-[#7C8881]">
            Verification links expire after a limited period
            and can only be used once.
          </div>
        </section>
      </div>
    </main>
  );
}