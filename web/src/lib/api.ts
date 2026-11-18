/**
 * The only path from this app to the Veyro API, and it is server-side.
 *
 * **The browser never holds a bearer token.** MOD-007 stores a session only as a SHA-256
 * digest precisely so a stolen database cannot replay one; putting the token itself into
 * client JavaScript would hand it to any XSS instead. So the token lives in an httpOnly
 * cookie, every call is made from a Next route handler or a server component, and the client
 * bundle has no code that could read it.
 *
 * **`X-Veyro-Tenant` is a claim and the backend says so.** MOD-004's note: it is shape-checked
 * and nothing more, and tenant isolation does not depend on it being honest. This file does
 * not treat it as authentication either -- it is carried because the API requires it, and the
 * session cookie is what actually identifies the caller.
 */

import { cookies } from "next/headers";

/** Where the FastAPI backend answers. Read per request, never inlined into a bundle. */
export function apiOrigin(): string {
  return process.env.VEYRO_API_ORIGIN ?? "http://127.0.0.1:8000";
}

export const SESSION_COOKIE = "veyro_session";
export const TENANT_COOKIE = "veyro_tenant";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    /** The backend's own machine-readable reason, e.g. `forbidden`, `step_up_required`. */
    readonly reason: string,
  ) {
    super(`${status} ${reason}`);
  }
}

/** A correlation id per request, so a decision here can be traced to one there. */
export function correlationId(): string {
  return crypto.randomUUID();
}

type Options = {
  method?: "GET" | "POST";
  body?: unknown;
  /** Send the session cookie's bearer token. Off for login, which has no session yet. */
  authenticated?: boolean;
  tenantId?: string;
};

/**
 * Call the API. Returns parsed JSON, or throws `ApiError` carrying the backend's reason.
 *
 * The reason is preserved rather than flattened to a message, because the UI decides what to
 * render from it: `step_up_required` is a prompt for a second factor, `forbidden` is a hidden
 * control, and `422` is a field error. A string the user reads cannot carry that.
 */
export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { method = "GET", body, authenticated = true, tenantId } = options;
  const jar = await cookies();
  const tenant = tenantId ?? jar.get(TENANT_COOKIE)?.value;
  if (!tenant) throw new ApiError(400, "no_tenant_selected");

  const headers: Record<string, string> = {
    "X-Veyro-Tenant": tenant,
    Accept: "application/json",
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authenticated) {
    const token = jar.get(SESSION_COOKIE)?.value;
    if (!token) throw new ApiError(401, "no_session");
    headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${apiOrigin()}${path}`, {
      method,
      headers,
      // Spread rather than `body: undefined`: under `exactOptionalPropertyTypes` an explicit
      // undefined is not the same as an absent property, and `RequestInit.body` does not
      // accept it. The strictness is worth keeping -- it is the same distinction that makes
      // an omitted field and a null field different at an API boundary.
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      // Never cache an authenticated read: a tenant's data must not be served to the next
      // request, which is the cross-tenant leakage the isolation rule's layer 7 names.
      cache: "no-store",
    });
  } catch {
    throw new ApiError(503, "unreachable");
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let parsed: unknown = undefined;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = undefined;
  }
  if (!response.ok) {
    throw new ApiError(response.status, reasonOf(parsed, response.status));
  }
  return parsed as T;
}

/**
 * Pull the backend's machine reason out of an error body.
 *
 * FastAPI answers 422 with `detail`, and this app's own handlers answer `{"error": "..."}`.
 * Anything else becomes a status-shaped reason rather than leaking a server string into the
 * interface -- a 500's body is for a log, not for a member.
 */
function reasonOf(parsed: unknown, status: number): string {
  if (parsed && typeof parsed === "object") {
    const body = parsed as Record<string, unknown>;
    if (typeof body.error === "string") return body.error;
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "invalid_request";
  }
  return status >= 500 ? "server_error" : "request_failed";
}

export type SessionFacts = {
  identity_id: string;
  aal: number;
  [key: string]: unknown;
};

/**
 * The caller's own session, or `null` when there is none. **Never throws for being signed out.**
 *
 * The reasons there is no session are all ordinary rather than exceptional, and the first one is
 * easy to miss: a visitor who has never signed in has no tenant cookie either, so `api` refuses
 * before it reaches the network with `no_tenant_selected`. Treating that as an error made
 * `/login` -- the one page whose entire audience is signed-out people -- answer 500 to every
 * first-time visitor, so the sign-in page could not be reached at all. This function fails
 * closed, and on a sign-in page "closed" has to mean "anonymous", not "broken".
 */
export async function currentSession(): Promise<SessionFacts | null> {
  try {
    return await api<SessionFacts>("/auth/session");
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.status === 401 ||
        error.status === 403 ||
        error.reason === "no_session" ||
        error.reason === "no_tenant_selected")
    ) {
      return null;
    }
    throw error;
  }
}

/**
 * Ask the gate whether this session may do something. **This is how the UI decides what to
 * render**, and it asks the real evaluator rather than guessing from a permission list.
 *
 * `GET /authz/check` needs no permission to ask about oneself, which is what makes it safe to
 * call for every control on a page. A false answer hides the control; it does not disable a
 * visible one, because a disabled button a caller cannot use is still a disclosure that the
 * action exists.
 */
export async function may(action: string): Promise<boolean> {
  return (await gate(action)).allowed;
}

export type GateAnswer = {
  action: string;
  allowed: boolean;
  reason: string;
  step_up_required: boolean;
  required_aal: number | null;
  /** False when the action needs an assurance level this build cannot reach. */
  reachable: boolean;
  /** The fields a read must render masked. MOD-014's list, carried rather than dropped. */
  masked_fields: string[];
};

/**
 * The gate's whole answer, because the three refusals are three different interfaces.
 *
 * `allowed: false` with `step_up_required` is a prompt for a second factor; without it the
 * control is simply hidden. `reachable: false` means the action needs AAL 3, which needs a
 * hardware factor MOD-007 cannot verify -- so the honest interface says the capability is not
 * available in this build rather than inviting a step-up that can never succeed. Collapsing
 * all three to a boolean is how a UI ends up with a button that can never work.
 */
export async function gate(action: string): Promise<GateAnswer> {
  const closed: GateAnswer = {
    action,
    allowed: false,
    reason: "gate_unreachable",
    step_up_required: false,
    required_aal: null,
    reachable: true,
    masked_fields: [],
  };
  try {
    const answer = await api<GateAnswer>(
      `/authz/check?action=${encodeURIComponent(action)}&correlation_id=${correlationId()}`,
    );
    return { ...closed, ...answer, allowed: answer.allowed === true };
  } catch (error) {
    // Fail closed. An unreachable gate is not permission.
    if (error instanceof ApiError) return { ...closed, reason: error.reason };
    throw error;
  }
}
