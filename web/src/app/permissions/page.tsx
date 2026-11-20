import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate, type GateAnswer } from "@/lib/api";
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
import { utcStamp } from "@/lib/time";

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

  // **The gate's own answers, which the permission list above cannot give.** `simulate`
  // reads role assignments, and MOD-014's finding is that a grant is not a session: a
  // permission held at an assurance the action refuses is not a permission the action will
  // accept. So this asks `GET /authz/check`, which asks authorization and assurance together,
  // and renders the three answers as three different facts.
  //
  // **It used to be the product's front door.** `/` printed this table, the caller's identity
  // uuid and their assurance level, where the design puts the Command Center -- the mismatch
  // the owner directive names by example. It is diagnostic, it is about MOD-008, and this is
  // the page about MOD-008, so it lives here beside the roles and the log.
  const probes = [
    "people.person.read",
    "booking.booking.write",
    "access.decision.evaluate",
    "devices.command.unlock",
    "finance.ledger.read",
    "support.session.start",
  ] as const;
  const answers = await Promise.all(probes.map((action) => gate(action)));

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
    <div className="stack">
      <PageHeader title={text("perms.title")} />

      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("perms.mine")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("perms.mineLead")}
        </p>
        {!mayRoles.allowed ? (
          <Banner severity="info">
            {mayRoles.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Banner>
        ) : rolesFailed ? (
          <Banner severity="critical">{text(rolesFailed)}</Banner>
        ) : mine === null ? null : (
          <>
            <p className="muted" style={{ margin: 0 }}>
              {text("perms.scope")}: <span className="data" dir="ltr">{mine.scope_type}</span>
            </p>
            <PermissionList permissions={mine.permissions} locale={locale} />
          </>
        )}
      </section>

      <section className="page-section" aria-labelledby="gate-heading">
        <h2 id="gate-heading" style={{ margin: 0 }}>{text("perms.gateTitle")}</h2>
        <p className="muted" style={{ margin: 0 }}>{text("perms.gateLead")}</p>
        <DataGrid
          caption={text("perms.gateTitle")}
          labelledBy="gate-heading"
          rows={answers}
          rowKey={(answer) => answer.action}
          columns={[
            {
              header: text("home.action"),
              kind: "text",
              priority: 1,
              // A permission name is a Latin identifier that may sit inside an RTL
              // paragraph, so it is isolated rather than left to the bidi algorithm, which
              // would move the dots.
              render: (answer) => <span className="data" dir="ltr">{answer.action}</span>,
            },
            {
              header: text("home.gate"),
              kind: "status",
              priority: 1,
              render: (answer) => text(describeGate(answer)),
            },
          ]}
        />
      </section>

      <section className="page-section">
        <h2 id="roles-heading" style={{ margin: 0 }}>
          {text("perms.roles")}
        </h2>
        {!mayRoles.allowed ? (
          <Banner severity="info">
            {mayRoles.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Banner>
        ) : rolesFailed ? null : roles.length === 0 ? (
          <Banner severity="info">{text("perms.noRoles")}</Banner>
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

      <section className="page-section">
        <h2 id="audit-heading" style={{ margin: 0 }}>
          {text("perms.audit")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("perms.auditLead")}
        </p>
        {!mayAudit.allowed ? (
          <Banner severity="info">
            {mayAudit.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Banner>
        ) : auditFailed ? (
          <Banner severity="critical">{text(auditFailed)}</Banner>
        ) : (
          <>
            {verdict ? (
              <Banner severity={verdict.verified ? "info" : "critical"}>
                {verdict.verified ? text("perms.chainOk") : text("perms.chainBroken")}{" "}
                {/* **Always, including on the green answer.** */}
                {text("perms.chainCaveat")}
              </Banner>
            ) : null}
            {audit.length === 0 ? (
              <Banner severity="info">{text("perms.noAudit")}</Banner>
            ) : (
              <DataGrid
                caption={text("perms.audit")}
labelledBy="audit-heading"
                rows={audit}
                rowKey={(entry) => String(entry.sequence)}
                columns={[
                  {
                    header: text("perms.sequence"),
                    kind: "text",
                    // **Priority 1: the sequence is how an entry is referred to.** The grid
                    // drops 3 then 2 as the viewport narrows, and whatever stays has to be
                    // enough to identify a row on its own.
                    priority: 1,
                    render: (entry) => (
                      <span className="data">{formatInteger(entry.sequence, "latn")}</span>
                    ),
                  },
                  {
                    header: text("perms.action"),
                    kind: "text",
                    priority: 1,
                    // A permission name is an identifier: ASCII, not translated, and it must
                    // not be reordered by the bidi algorithm in an Arabic page.
                    render: (entry) => (
                      <span className="data" dir="ltr">{entry.action}</span>
                    ),
                  },
                  {
                    header: text("perms.outcome"),
                    kind: "status",
                    priority: 2,
                    render: (entry) => entry.outcome,
                  },
                  {
                    header: text("perms.category"),
                    kind: "text",
                    priority: 3,
                    render: (entry) => entry.category,
                  },
                  {
                    header: text("perms.when"),
                    kind: "date",
                    priority: 2,
                    render: (entry) => (
                      <span className="data" dir="ltr">{utcStamp(entry.occurred_at)}</span>
                    ),
                  },
                ]}
              />
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
    <dl className="facts">
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

/**
 * Four answers, four messages -- and the order matters.
 *
 * `reachable: false` is checked before `step_up_required`, because the gate sets both for an
 * AAL-3 action: it is true that a stronger sign-in is required and false that one is
 * available. Reading them the other way round would offer a step-up that can never succeed,
 * and `support.session.start` -- in the probe list above -- is exactly that case.
 */
function describeGate(answer: GateAnswer): MessageKey {
  if (answer.allowed) return "gate.allowed";
  if (!answer.reachable) return "gate.unreachable";
  if (answer.step_up_required) return "gate.stepUp";
  return "gate.denied";
}
