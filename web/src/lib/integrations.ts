import { api } from "@/lib/api";

/**
 * MOD-012's reads, typed: what is installed, what it may reach, and what it has done.
 *
 * **Nothing syncs.** There is no provider, no outbound HTTP and no adapter code in this
 * build: `start_run`, `finish_run` and `fail_run` are written by whatever does the work, and
 * nothing does. So a run here is the record that somebody *said* a sync happened, and a board
 * rendering it as evidence of data moving would be the fabricated-evidence shape this codebase
 * has been bitten by six times.
 *
 * **A credential reference holds a reference and there is no column it could hold a secret
 * in.** `vault_ref` names a secret kept somewhere this build cannot read, and the definition
 * catalogue carries the same rule from the other side: a configuration field declares a type
 * and there is no `secret` type, so a definition cannot invite a tenant to paste an API key
 * into a value every list route reads. The vault those references point at is the one
 * MOD-007's TOTP seeds, MOD-009's crypto-shred and MOD-021's device certificates are all
 * waiting on -- which is why the board says it in the same words the fleet board does.
 *
 * **`validated` means somebody recorded a validation, not that this build performed one.**
 * There is no provider to call, so the state carries an actor and a written piece of evidence
 * and the row says what it is: a claim made by a named party at a time. The same shape as
 * MOD-014's contact verification and MOD-021's commissioning.
 */

export type Install = {
  install_id: string;
  definition_key: string;
  definition_version: number;
  criticality: string;
  state: string;
  config: Record<string, unknown>;
  /** Paragraph 3033's three written obligations, as presence rather than prose. */
  has_fallback: boolean;
  has_reconciliation: boolean;
  has_exit_plan: boolean;
  installed_at: string;
  uninstalled_at: string | null;
};

export type Connection = {
  connection_id: string;
  install_id: string;
  external_account_ref: string;
  region: string | null;
  granted_scopes: string[];
  state: string;
  authorized_at: string | null;
  validated_at: string | null;
  revoked_at: string | null;
};

export type CredentialRef = {
  credential_ref_id: string;
  connection_id: string;
  /** A locator, by constraint. No secret can be stored here and no column could hold one. */
  vault_ref: string;
  scopes: string[];
  issued_at: string;
  expires_at: string | null;
  retired_at: string | null;
  supersedes: string | null;
};

export type SyncCursor = {
  cursor_id: string;
  connection_id: string;
  resource: string;
  position: string;
  observed_at: string;
  conflict_policy: string;
  reset_at: string | null;
  updated_at: string;
};

export type ConnectorRun = {
  run_id: string;
  connection_id: string;
  resource: string;
  status: string;
  attempts: number;
  max_attempts: number;
  records_read: number;
  records_written: number;
  conflicts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  started_at: string;
  finished_at: string | null;
};

export function listInstalls(): Promise<Install[]> {
  return api("/integrations");
}

export function listConnections(): Promise<Connection[]> {
  return api("/integrations/connections");
}

export function listCredentials(): Promise<CredentialRef[]> {
  return api("/integrations/credentials");
}

export function listCursors(): Promise<SyncCursor[]> {
  return api("/integrations/cursors");
}

export function listRuns(): Promise<ConnectorRun[]> {
  return api("/integrations/runs");
}

/**
 * Whether a `live_critical` install has the three things paragraph 3033 requires in writing
 * before it may carry traffic.
 *
 * **The three are checked at activation and nothing re-checks them**, which is how MOD-012's
 * review found that three blank strings erased the fallback, the reconciliation procedure and
 * the exit plan from a live critical install with the same permission that wrote them and no
 * refusal anywhere -- `coalesce` replaces NULL, not the empty string. The read returns each
 * as presence rather than prose, so a board can say which is missing without carrying a
 * tenant's written procedure onto a screen.
 */
/**
 * **`critical`, not `live_critical`.** The first version compared against the latter, which
 * `int_installs.criticality` never holds -- the vocabulary is `convenience`, `important`,
 * `critical`, and `lifecycle.py` compares `!= "critical"`. So the check matched nothing, every
 * install reported "not required at this criticality", and the one control this block exists
 * for was decorative. That is a control keyed on a value that never occurs, which is the shape
 * `CLAUDE.md` records across five modules -- here caused by taking the prose ("a live critical
 * install") for the stored value. Found by looking at the board and seeing a `critical` row
 * say the obligations did not apply to it.
 */
export const OBLIGED_CRITICALITY = "critical";

/**
 * Whether paragraph 3033's written obligations bind this install at all.
 *
 * **Exported so the page cannot ask the question a second way.** The first version had the
 * page re-deriving `criticality !== "live_critical"` inline for its own cell while the
 * library answered the banner, so fixing the wrong constant in one place left the other
 * wrong -- the banner correctly named an install carrying traffic without its obligations
 * while the row beside it said they did not apply. "A control consulted on one path and not
 * its sibling" is MOD-014's finding; a comparison written twice is how it happens.
 */
export function obligationsApply(install: Install): boolean {
  return install.criticality === OBLIGED_CRITICALITY;
}

export function obligationsMet(install: Install): boolean {
  if (install.criticality !== OBLIGED_CRITICALITY) return true;
  return install.has_fallback && install.has_reconciliation && install.has_exit_plan;
}

export function missingObligations(install: Install): string[] {
  if (install.criticality !== OBLIGED_CRITICALITY) return [];
  return [
    ...(install.has_fallback ? [] : ["fallback"]),
    ...(install.has_reconciliation ? [] : ["reconciliation"]),
    ...(install.has_exit_plan ? [] : ["exit_plan"]),
  ];
}

/**
 * A credential reference that is still the one a provider would be reached with.
 *
 * A rotation is a new row that supersedes the old one -- `vault_ref`, `scopes` and
 * `expires_at` carry no UPDATE grant for any runtime role -- so "what did this connection hold
 * on the fourteenth" stays answerable. A board showing every row without saying which is
 * current would be showing a history as though it were a state.
 */
export function credentialIsCurrent(credential: CredentialRef): boolean {
  return credential.retired_at === null;
}

/**
 * Whether a run can still be retried, which is not the same as whether it failed.
 *
 * A run that has burned its attempt budget is `dead` and needs an attributed release before
 * it goes back in front of a provider -- the act MOD-012's review found recorded nobody,
 * while resetting the attempt count, so the row afterwards read as a fresh run with a stale
 * error. A board that showed `failed` and `dead` alike would hide the one that needs a person.
 */
export function needsSomebody(run: ConnectorRun): boolean {
  return run.status === "dead";
}

/**
 * What a run actually demonstrates, which is less than it looks.
 *
 * Nothing in this build calls a provider, so `records_read` and `records_written` are figures
 * a caller supplied. The run is evidence that somebody started one and reported a result, and
 * the board says so rather than letting a count read as data that moved.
 */
export function reportedNotObserved(run: ConnectorRun): boolean {
  return run.records_read > 0 || run.records_written > 0;
}
