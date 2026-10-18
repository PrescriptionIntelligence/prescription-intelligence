/**
 * Authentication library.
 *
 * P7.12-B: migrated from localStorage JWT to HttpOnly cookie authentication.
 *
 * Handles:
 * - Login / register API calls to the FastAPI backend
 * - Email verification
 * - Verification email resend
 * - Current user state (pi_user in localStorage for UI routing only)
 * - Customer profile information
 * - Logout (clears server cookie via POST /auth/logout)
 * - Authenticated API requests (credentials: "include" — cookie transport)
 *
 * What changed from P7.12-A:
 * - JWT is NO LONGER stored in localStorage.
 * - authFetch() uses credentials:"include" instead of manually attaching
 *   Authorization: Bearer from localStorage.
 * - login() does NOT call setToken(); the browser stores the cookie
 *   automatically from the backend Set-Cookie header.
 * - logout() calls POST /auth/logout to clear the server cookie, then
 *   clears local UI state.
 * - isAuthenticated() uses pi_user presence as a UI hint; the server
 *   is the ultimate authority (fetchMe() validates the session).
 * - getToken() / setToken() / removeToken() are kept as stubs for
 *   backward-compatibility with any callers; they are no longer the
 *   auth transport mechanism and will be removed in a future phase.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const USER_KEY = "pi_user";

// =========================================================
// Types
// =========================================================

export type CustomerProfile = {
  id: string;
  customer_code: string;
  name: string;
  phone: string | null;
  email: string | null;
};

export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  organization_id: string | null;
  is_active?: boolean;
  customer?: CustomerProfile | null;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
};

/**
 * Authentication result.
 *
 * Login returns an access_token in the JSON body for Swagger/Bearer
 * compatibility during this migration phase.  Frontend code MUST NOT
 * save it to localStorage — the HttpOnly cookie is the transport.
 *
 * Registration may NOT return an access token because the account must
 * verify its email before being allowed to authenticate.
 */
export type AuthResult = {
  access_token?: string | null;
  token_type?: string | null;
  user: User;
  organization: Organization | null;
  message: string;

  email_verification_required?: boolean;
  email_verified?: boolean;
};

export type EmailVerificationResult = {
  message: string;
  email_verified: boolean;
};

// =========================================================
// Token helpers — kept as stubs; no longer the auth transport
//
// getToken() / setToken() / removeToken() are intentionally
// no-ops or read-nothing so that existing callers that have
// not yet been migrated away from them do not break while
// also not accidentally writing the JWT back to localStorage.
// These will be removed in a future cleanup phase.
// =========================================================

/** @deprecated Cookie is the auth transport. Returns null. */
export function getToken(): string | null {
  return null;
}

/** @deprecated Cookie is the auth transport. Does nothing. */
export function setToken(_token: string): void {
  // Intentionally empty — do not store JWT in localStorage.
}

/** @deprecated Cookie is the auth transport. Clears user key only. */
export function removeToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.removeItem(USER_KEY);
}

// =========================================================
// User helpers
// =========================================================

export function getUser(): User | null {
  if (typeof window === "undefined") {
    return null;
  }

  const stored = localStorage.getItem(USER_KEY);

  if (!stored) {
    return null;
  }

  try {
    return JSON.parse(stored) as User;
  } catch {
    return null;
  }
}

export function setUser(user: User): void {
  if (typeof window === "undefined") {
    return;
  }

  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Lightweight UI hint: returns true when a pi_user profile is cached.
 *
 * This does NOT prove the server session is valid.  Use fetchMe() to
 * validate the actual session when security is required.  The cookie
 * is HttpOnly so JavaScript cannot read it directly.
 */
export function isAuthenticated(): boolean {
  return getUser() !== null;
}

export function isCustomer(): boolean {
  return getUser()?.role === "customer";
}

export function isPharmacist(): boolean {
  return getUser()?.role === "pharmacist";
}

export function isAdmin(): boolean {
  return getUser()?.role === "admin";
}

// =========================================================
// Role-based home
// =========================================================

export function getRoleHome(user?: User | null): string {
  const currentUser = user ?? getUser();

  if (!currentUser) {
    return "/sign-in";
  }

  switch (currentUser.role) {
    case "customer":
      return "/customer";

    case "pharmacist":
      return "/dashboard";

    case "admin":
      return "/admin";

    default:
      return "/dashboard";
  }
}

// =========================================================
// API: Login
// =========================================================

export async function login(
  email: string,
  password: string
): Promise<AuthResult> {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    // credentials:"include" ensures the browser stores the
    // HttpOnly Set-Cookie from the server response.
    credentials: "include",
    body: JSON.stringify({
      email,
      password,
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Login failed. Please check your credentials."
    );
  }

  const result = data as AuthResult;

  // The browser stores the HttpOnly cookie automatically.
  // Do NOT save result.access_token to localStorage.

  if (result.user) {
    setUser(result.user);
  }

  return result;
}

// =========================================================
// API: Register pharmacist
// =========================================================

export async function register(
  name: string,
  email: string,
  password: string,
  pharmacyName: string
): Promise<AuthResult> {
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      email,
      password,
      pharmacy_name: pharmacyName,
    }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Registration failed. Please try again."
    );
  }

  const result = data as AuthResult;

  /*
   * Registration does not automatically create an authenticated
   * session — email verification is required first.
   * Do NOT save access_token to localStorage.
   */
  if (result.user) {
    setUser(result.user);
  }

  return result;
}

// =========================================================
// API: Register customer
// =========================================================

export async function registerCustomer(
  name: string,
  email: string,
  password: string,
  phone?: string,
  customerCode?: string
): Promise<AuthResult> {
  const response = await fetch(
    `${API_URL}/auth/register/customer`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name,
        email,
        password,
        phone: phone || null,
        customer_code: customerCode || null,
      }),
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Customer registration failed. Please try again."
    );
  }

  const result = data as AuthResult;

  /*
   * Same rule: registration is not authenticated.
   * Do NOT save access_token to localStorage.
   */
  if (result.user) {
    setUser(result.user);
  }

  return result;
}

// =========================================================
// API: Verify email
// =========================================================

export async function verifyEmail(
  email: string,
  token: string
): Promise<EmailVerificationResult> {
  const response = await fetch(
    `${API_URL}/auth/verify-email`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        token,
      }),
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Email verification failed."
    );
  }

  return data as EmailVerificationResult;
}

// =========================================================
// API: Resend verification email
// =========================================================

export async function resendVerification(
  email: string
): Promise<{ message: string }> {
  const response = await fetch(
    `${API_URL}/auth/resend-verification`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
      }),
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Unable to resend verification email."
    );
  }

  return {
    message:
      typeof data?.message === "string"
        ? data.message
        : "If an account exists for this email, a verification email has been sent.",
  };
}

// =========================================================
// API: Get authenticated user profile
// =========================================================

export async function fetchMe(): Promise<User> {
  // credentials:"include" sends the HttpOnly cookie.
  // No Authorization header is needed for browser requests.
  const response = await fetch(`${API_URL}/users/me`, {
    credentials: "include",
  });

  if (!response.ok) {
    if (response.status === 401) {
      // Clear cached UI state; the cookie has expired or is absent.
      if (typeof window !== "undefined") {
        localStorage.removeItem(USER_KEY);
      }

      throw new Error(
        "Session expired. Please sign in again."
      );
    }

    throw new Error("Failed to load user profile.");
  }

  const data = await response.json();

  const user: User = {
    id: data.id,
    name: data.name,
    email: data.email,
    role: data.role,
    organization_id: data.organization?.id ?? null,
    is_active: data.is_active,
    customer: data.customer
      ? {
          id: data.customer.id,
          customer_code: data.customer.customer_code,
          name: data.customer.name,
          phone: data.customer.phone ?? null,
          email: data.customer.email ?? null,
        }
      : null,
  };

  setUser(user);

  return user;
}

// =========================================================
// Logout
// =========================================================

export async function logout(): Promise<void> {
  // Ask the server to clear the HttpOnly cookie.
  // The request is best-effort — local UI state is always cleared
  // even if the server returns an error (e.g., network failure,
  // already-expired cookie, 404, 401).
  try {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // Network error — continue with local cleanup.
  }

  // Clear cached UI state.
  if (typeof window !== "undefined") {
    localStorage.removeItem(USER_KEY);
    window.location.href = "/";
  }
}


// =========================================================
// API: Forgot password
// =========================================================

export async function forgotPassword(
  email: string
): Promise<{ message: string }> {
  const response = await fetch(
    `${API_URL}/auth/forgot-password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Unable to process your request."
    );
  }

  return {
    message:
      typeof data?.message === "string"
        ? data.message
        : "If an account exists for this email, a password reset link has been sent.",
  };
}

// =========================================================
// API: Reset password
// =========================================================

export async function resetPassword(
  token: string,
  newPassword: string
): Promise<{ message: string }> {
  const response = await fetch(
    `${API_URL}/auth/reset-password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        token,
        new_password: newPassword,
      }),
    }
  );

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Password reset failed. Please try again."
    );
  }

  return {
    message:
      typeof data?.message === "string"
        ? data.message
        : "Your password has been reset successfully.",
  };
}


// =========================================================
// Authenticated fetch wrapper
// =========================================================

export async function authFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  // credentials:"include" sends the HttpOnly cookie automatically.
  // The JWT is no longer read from localStorage or added as a header
  // for normal browser requests.
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
  });

  if (response.status === 401) {
    // Clear cached UI state and redirect to sign-in.
    if (typeof window !== "undefined") {
      localStorage.removeItem(USER_KEY);
      window.location.href = "/sign-in";
    }
  }

  return response;
}


// =========================================================
// Google OAuth helpers
// =========================================================

/**
 * Redirect the browser to the backend Google OAuth initiation endpoint.
 * The backend issues the state token and redirects to Google.
 */
export function loginWithGoogle(): void {
  window.location.href = `${API_URL}/auth/google/login`;
}

/**
 * Handle the data returned by the Google callback endpoint.
 * Call this after the callback URL is hit and the JSON is received.
 * Stores the user object in localStorage (for UI routing) exactly
 * like a normal password login.
 */
export function handleGoogleAuthResult(data: AuthResult): void {
  if (data.user) {
    setUser(data.user);
  }
}
