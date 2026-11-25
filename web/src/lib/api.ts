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

/**
 * ADR-0014: narrow the gate's answer to "allowed *here*", keeping the raw one beside it.
 *
 * **Every page in this app reads `allowed` and almost none of them filters by scope.** The
 * gate now answers "may this caller do this anywhere", and the server's `permit` refuses a
 * brand- or location-scoped caller on any route that has not opted in -- so a page keyed on
 * the raw answer renders as permitted over a read that answers 403. `/members` did exactly
 * that the hour the gate changed: the heading drew, the list read refused, and the page showed
 * neither the refusal nor the rows.
 *
 * So `allowed` keeps its old meaning and `allowed_anywhere` carries the new one. A page that
 * filters -- `/staff` is the first -- reads the second and the boundary beside it; every other
 * page behaves exactly as it did, which is ADR-0014 D3 applied one layer up.
 */
function narrow(answer: GateAnswer): GateAnswer {
  const anywhere = answer.allowed === true;
  return {
    ...answer,
    allowed_anywhere: anywhere,
    allowed: anywhere && answer.tenant_wide === true,
  };
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
  /**
   * ADR-0014: whether the caller holds the action everywhere in the tenant.
   *
   * **`allowed` is narrowed to this by default**, which keeps every page in this app behaving
   * exactly as it did: the server's `permit` refuses a brand- or location-scoped caller on any
   * route that has not opted in, so a page keyed on the gate's raw answer would render as
   * permitted over a read that answers 403 -- which is what happened to `/members` the hour
   * the gate learned to say "anywhere".
   */
  tenant_wide: boolean;
  /**
   * Where the caller holds it, from their own live assignments.
   *
   * A page that filters reads this; a page that does not gets `allowed: false` for a scoped
   * caller and never sees it. `allowed_anywhere` is the raw answer for the former.
   */
  scopes: { scope_type: string; brand_id: string | null; location_id: string | null }[];
  /** The gate's own answer, before `allowed` is narrowed to the tenant-wide case. */
  allowed_anywhere: boolean;
};

/**
 * The gate's whole answer, because the three refusals are three different interfaces.
 *
 * `allowed: false` with `step_up_required` is a prompt for a second factor; without it the
 * control is simply hidden. `reachable: false` means `/auth/step-up` cannot reach the level
 * the action needs -- MOD-008 computes it from the two factors that endpoint accepts -- so
 * the honest interface names the door that does reach it, a passkey sign-in, rather than
 * inviting a step-up that can never succeed. Collapsing all three to a boolean is how a UI
 * ends up with a button that can never work.
 */
/**
 * The gate's answer for several actions, in one request.
 *
 * **A rich page asks the gate many times.** The shell asks about thirteen navigation
 * entries and the Command Center about six reads, so rendering `/` cost nineteen round
 * trips -- and MOD-011's `api.request` budget is 600 a minute per identity, whose own
 * comment says "a limit that trips during ordinary use is a limit somebody will raise to
 * infinity rather than investigate". The browser suite tripped it, which is the cheap way
 * to find out.
 *
 * **Same semantics, fewer requests.** `/authz/checks` runs the same `authz.check` per
 * action with the same scope and the same assurance weighing. It is not a permission list:
 * a client that fetched `effective_permissions` and decided for itself would be MOD-014's
 * "a grant is not a session", where a permission held on a session too weak for the action
 * reads as held.
 *
 * **Fails closed per action**, like `gate`: an unreachable gate is not permission.
 */
export async function gateAll<A extends readonly string[]>(
  actions: A,
): Promise<{ [K in keyof A]: GateAnswer }> {
  const closed = (action: string, reason: string): GateAnswer => ({
    action,
    allowed: false,
    reason,
    step_up_required: false,
    required_aal: null,
    reachable: true,
    masked_fields: [],
    tenant_wide: false,
    scopes: [],
    allowed_anywhere: false,
  });
  const query = new URLSearchParams();
  for (const action of actions) query.append("action", action);
  query.set("correlation_id", correlationId());
  try {
    const answer = await api<{ checks: GateAnswer[] }>(`/authz/checks?${query.toString()}`);
    const byAction = new Map(answer.checks.map((check) => [check.action, check]));
    return actions.map((action) => {
      const found = byAction.get(action);
      // An action the server did not answer about is not permission either.
      return found === undefined
        ? closed(action, "gate_unreachable")
        : narrow({ ...closed(action, "gate"), ...found });
    }) as { [K in keyof A]: GateAnswer };
  } catch (error) {
    if (error instanceof ApiError) {
      return actions.map((action) => closed(action, error.reason)) as {
        [K in keyof A]: GateAnswer;
      };
    }
    throw error;
  }
}

/**
 * Gate reasons that mean the request never got an answer.
 *
 * `gate` and `gateAll` fail closed -- an unreachable gate is not permission -- which is right
 * for access and does not change. But a transport failure and a refusal then reach a page in
 * the same shape, and every page in this app said "Not permitted" for both. That teaches
 * somebody they lack access they have, in the one place they decide whether to go and ask
 * for a grant.
 *
 * `forbidden` and `step_up_required` are the gate speaking. Everything here is the request
 * failing before it got that far.
 */
export const UNREACHED: ReadonlySet<string> = new Set([
  "unreachable",
  "gate_unreachable",
  "gate",
  "no_session",
  "no_tenant_selected",
]);

/**
 * What a closed gate answer actually means, for a page deciding what to say.
 *
 * Four states, and the app had words for three of them:
 *
 * - `gate_failed` — the request did not get an answer. **This is the one that was missing**,
 *   and it is not about the reader's access at all.
 * - `unreachable_level` — the action needs an assurance a step-up cannot reach.
 *   `member.health.read` is `biometric_sensitive`, which maps to AAL 3, and `/auth/step-up`
 *   takes a password or a recovery code: neither gets past 2. Signing in with a passkey does
 *   reach it, so the page names that door instead of offering a step-up that would be
 *   refused. The name of this verdict is older than the capability.
 * - `needs_step_up` — a stronger sign-in would open it, and the page can offer one.
 * - `denied` — the gate said no. Only this one is about what the reader holds.
 */
export type GateVerdict = "gate_failed" | "unreachable_level" | "needs_step_up" | "denied";

export function gateVerdict(answer: GateAnswer): GateVerdict {
  if (UNREACHED.has(answer.reason)) return "gate_failed";
  if (!answer.reachable) return "unreachable_level";
  if (answer.step_up_required) return "needs_step_up";
  return "denied";
}

/**
 * The message a closed gate answer deserves, as a key.
 *
 * **Every page in this app said "Not permitted" for four different things**, because the two
 * it could tell apart were the two it had words for. A transport failure and a refusal reach
 * a page in the same shape -- that is what failing closed means -- so the page reported a
 * fault as a statement about the reader's access, and a reader who believes it goes and asks
 * somebody for a grant they already hold.
 *
 * The verdicts and what each one is for are on `gateVerdict`. The one worth repeating here:
 * `unreachable_level` offers no step-up on purpose, because the assurance it wants cannot be
 * reached in this build at all and a link would send somebody looking for a hardware key
 * that changes nothing.
 */
export function gateMessage(
  answer: GateAnswer,
): "gate.failed" | "gate.unreachable" | "gate.needsStepUp" | "gate.denied" {
  switch (gateVerdict(answer)) {
    case "gate_failed":
      return "gate.failed";
    case "unreachable_level":
      return "gate.unreachable";
    case "needs_step_up":
      return "gate.needsStepUp";
    default:
      return "gate.denied";
  }
}

export async function gate(action: string): Promise<GateAnswer> {
  const closed: GateAnswer = {
    action,
    allowed: false,
    reason: "gate_unreachable",
    step_up_required: false,
    required_aal: null,
    reachable: true,
    masked_fields: [],
    tenant_wide: false,
    scopes: [],
    allowed_anywhere: false,
  };
  try {
    const answer = await api<GateAnswer>(
      `/authz/check?action=${encodeURIComponent(action)}&correlation_id=${correlationId()}`,
    );
    return narrow({ ...closed, ...answer });
  } catch (error) {
    // Fail closed. An unreachable gate is not permission.
    if (error instanceof ApiError) return { ...closed, reason: error.reason };
    throw error;
  }
}

/**
 * Which message an API failure deserves.
 *
 * **Three answers, and conflating them is the defect this exists for.** Every surface in this
 * app rendered `error.unexpected` -- "Something went wrong." -- for anything that was not a
 * network failure, so a reader whose *own* request had been refused by MOD-011's rate limiter
 * was told the product had broken. It is the one refusal that is both temporary and the
 * reader's to act on, and it says "wait a moment" rather than "this is broken": CI found it,
 * because the browser suite makes more requests in a minute than any operator does and six
 * tests came back with the page saying something had gone wrong when nothing had.
 *
 * A 429 is the only status broken out, deliberately. A 403 and a 404 are handled where they
 * are meaningful -- the gate's own refusal, "no such person" -- and anything else really is
 * unexpected, which is what that message is for.
 */
export function failureMessage(error: unknown): "error.network" | "error.tooMany"
| "error.unexpected" {
  if (!(error instanceof ApiError)) return "error.unexpected";
  if (error.reason === "unreachable") return "error.network";
  return error.status === 429 ? "error.tooMany" : "error.unexpected";
}
