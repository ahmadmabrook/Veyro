import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  byDomain,
  listRoles,
  readAudit,
  simulate,
  verifyAudit,
  type AuditEntry,
  type ChainVerdict,
  type EffectivePermissions,
  type Role,
} from "@/lib/authz";
import { presentation } from "@/lib/preferences";

/**
 * MOD-008, rendered: the roles, what this session may do, and the log every refusal lands in.
 *
 * **What the log holds is stated accurately, which took a correction.** The first version of
 * this page said allowed actions are never recorded. They mostly are not -- there is no row
 * saying somebody read a member's profile -- but MOD-008 records the acts that *hand out*
 * access: a role created, a role granted, an approval decided. The fixture's own log shows
 * `role.assigned` with outcome `recorded`, which is how the claim was caught. A surface that
 * describes a log wrongly is worse than one that does not describe it.
 *
 * **Two permissions, two blocks, gated separately.** `authz.role.read` opens the roles and the
 * simulator; `authz.audit.read` opens the log. A page that asked for one and rendered both
 * would show an operator an empty audit table and let them conclude nothing had been refused --
 * which is the difference between "nothing happened" and "you may not see what happened", and
 * the reason every refusal on this surface is rendered as a refusal.
 *
 * **The chain's verdict is never shown without its caveat.** MOD-008's own note: the chain
 * detects editing, not truncation by somebody who also moves the head, because every value the
 * verifier compares lives in the database that actor already controls. A green tick with no
 * caveat is the more misleading of the two answers, so the caveat is part of the green answer
 * rather than a footnote under the red one.
 */
export default async function PermissionsPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const [mayRoles, mayAudit] = await Promise.all([
    gate("authz.role.read"),
    gate("authz.audit.read"),
  ]);

  let roles: Role[] = [];
  let mine: EffectivePermissions | null = null;
  let rolesFailed: MessageKey | null = null;
  if (mayRoles.allowed) {
    try {
      [roles, mine] = await Promise.all([listRoles(), simulate(session.identity_id)]);
    } catch (error) {
      rolesFailed = failure(error);
    }
  }

  let audit: AuditEntry[] = [];
  let verdict: ChainVerdict | null = null;
  let auditFailed: MessageKey | null = null;
  if (mayAudit.allowed) {
    try {
      [audit, verdict] = await Promise.all([readAudit(), verifyAudit()]);
    } catch (error) {
      auditFailed = failure(error);
    }
  }

  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{text("perms.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("perms.lead")}
      </p>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("perms.mine")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("perms.mineLead")}
        </p>
        {!mayRoles.allowed ? (
          <Alert tone="info">
            {mayRoles.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : rolesFailed ? (
          <Alert tone="error">{text(rolesFailed)}</Alert>
        ) : mine === null ? null : (
          <>
            <p className="muted" style={{ margin: 0 }}>
              {text("perms.scope")}: <span className="data" dir="ltr">{mine.scope_type}</span>
            </p>
            <PermissionList permissions={mine.permissions} locale={locale} />
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 id="roles-heading" style={{ margin: 0 }}>
          {text("perms.roles")}
        </h2>
        {!mayRoles.allowed ? (
          <Alert tone="info">
            {mayRoles.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : rolesFailed ? null : roles.length === 0 ? (
          <Alert tone="info">{text("perms.noRoles")}</Alert>
        ) : (
          roles.map((role) => (
            <div key={role.role_id} className="stack" style={{ gap: "var(--space-2)" }}>
              <h3 style={{ margin: 0 }}>{role.display_name}</h3>
              <p className="muted" style={{ margin: 0 }}>
                <span className="data" dir="ltr">
                  {role.role_key}
                </span>
                {" · "}
                {role.builtin ? text("perms.builtin") : text("perms.tenantDefined")}
                {" · "}
                {text("perms.held")}:{" "}
                <span className="data">
                  {formatInteger(role.permissions.length, "latn")}
                </span>
              </p>
              <PermissionList permissions={role.permissions} locale={locale} />
            </div>
          ))
        )}
      </section>

      <section className="panel stack">
        <h2 id="audit-heading" style={{ margin: 0 }}>
          {text("perms.audit")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("perms.auditLead")}
        </p>
        {!mayAudit.allowed ? (
          <Alert tone="info">
            {mayAudit.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : auditFailed ? (
          <Alert tone="error">{text(auditFailed)}</Alert>
        ) : (
          <>
            {verdict ? (
              <Alert tone={verdict.verified ? "info" : "error"}>
                {verdict.verified ? text("perms.chainOk") : text("perms.chainBroken")}{" "}
                {/* **Always, including on the green answer.** */}
                {text("perms.chainCaveat")}
              </Alert>
            ) : null}
            {audit.length === 0 ? (
              <Alert tone="info">{text("perms.noAudit")}</Alert>
            ) : (
              <table
                aria-labelledby="audit-heading"
                style={{ width: "100%", borderCollapse: "collapse" }}
              >
                <thead>
                  <tr>
                    <th scope="col" style={headCell}>{text("perms.sequence")}</th>
                    <th scope="col" style={headCell}>{text("perms.category")}</th>
                    <th scope="col" style={headCell}>{text("perms.action")}</th>
                    <th scope="col" style={headCell}>{text("perms.outcome")}</th>
                    <th scope="col" style={headCell}>{text("perms.when")}</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((entry) => (
                    <tr key={entry.sequence}>
                      <td style={cell}>
                        <span className="data">{formatInteger(entry.sequence, "latn")}</span>
                      </td>
                      <td style={cell}>{entry.category}</td>
                      <td style={cell}>
                        {/* A permission name is an identifier: ASCII, not translated, and it
                            must not be reordered by the bidi algorithm in an Arabic page. */}
                        <span className="data" dir="ltr">
                          {entry.action}
                        </span>
                      </td>
                      <td style={cell}>{entry.outcome}</td>
                      <td style={cell}>
                        <span className="data" dir="ltr">
                          {entry.occurred_at.slice(0, 16).replace("T", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function PermissionList({
  permissions,
  locale,
}: {
  permissions: string[];
  locale: Locale;
}) {
  if (permissions.length === 0) {
    return (
      <p className="muted" style={{ margin: 0 }}>
        {t(locale, "perms.noRoles")}
      </p>
    );
  }
  return (
    <dl style={listStyle}>
      {byDomain(permissions).map(([domain, names]) => (
        <div key={domain} style={{ display: "contents" }}>
          <dt className="muted">
            <span className="data" dir="ltr">
              {domain}
            </span>
          </dt>
          <dd style={{ margin: 0 }}>
            <span className="data" dir="ltr">
              {names.join(", ")}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function failure(error: unknown): MessageKey {
  return error instanceof ApiError && error.reason === "unreachable"
    ? "error.network"
    : "error.unexpected";
}

const headCell: React.CSSProperties = {
  textAlign: "start",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-default)",
  background: "var(--color-surface-sunken)",
  fontSize: "var(--type-label-size)",
  fontWeight: "var(--type-label-weight)",
};

const cell: React.CSSProperties = {
  textAlign: "start",
  verticalAlign: "top",
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

const listStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(8rem, auto) 1fr",
  gap: "var(--space-2) var(--space-4)",
  margin: 0,
};
