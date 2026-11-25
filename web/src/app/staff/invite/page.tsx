import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { PageHeader } from "@/components/ds/page-header";
import { ProseNote } from "@/components/prose";
import { fill, t, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { listRoles, readCatalog } from "@/lib/authz";
import { numerals } from "@/lib/display";
import { clubNames, pendingCount, stateKey, type Invitation } from "@/lib/invitations";
import { listInvitations } from "@/lib/invitations-reads";
import { listLocations } from "@/lib/organization";
import { presentation } from "@/lib/preferences";

import { InviteForm } from "./invite-form";
import { PendingActions } from "./pending-actions";

/**
 * ADM-STF-03 · INVITE — "Invite someone", and the pending list beside it. ADR-0017.
 *
 * **This is the first path in the build that creates an identity with a role**, which is what
 * makes it worth more than a form: `POST /identities` is open, so until now somebody joined a
 * tenant by being registered by whoever held its uuid and then granted a role in a second act.
 * The invitation is one act with a link at the end, and the escalation rule — a grantor may
 * only grant what they hold — is checked when it is written *and* again when it is accepted,
 * because a week is long enough for the inviter's own grant to be revoked.
 *
 * **The link is shown once, on the screen, because nothing sends it.** MOD-013 authors a
 * message and has no dispatcher, so this page is where the invitation reaches a person — and
 * it says so rather than implying an email went out.
 *
 * **The pending list's states are derived.** Waiting, expired, accepted and withdrawn are
 * three facts about the row read at the moment somebody asks; nothing stores a state and
 * nothing sweeps one, which is why an expired invitation still reads as expired a month later
 * without anything having run.
 */
export default async function InvitePage() {
  const { locale } = await presentation();
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const [mayInvite, mayRead, mayHierarchy] = await gateAll([
    "authz.assignment.write", "authz.role.read", "tenancy.organization.read",
  ] as const);

  // **The verdict rather than `allowed`**, which ADM-SCH-07 paid for: `authz.assignment.write`
  // is financial class, so `allowed` is false for every password-only session -- and gating the
  // form on it would hide the step-up the form itself offers.
  const mayAsk = !["denied", "unreachable_level"].includes(gateVerdict(mayInvite));
  if (!mayAsk) {
    return (
      <Shell locale={locale} figures={null}>
        <Banner severity="info">{text(gateMessage(mayInvite))}</Banner>
      </Shell>
    );
  }

  const [roles, catalog, clubs, invitations] = await Promise.all([
    mayRead.allowed ? listRoles().catch(toNull) : Promise.resolve(null),
    mayRead.allowed ? readCatalog().catch(toNull) : Promise.resolve(null),
    mayHierarchy.allowed ? listLocations().catch(toNull) : Promise.resolve(null),
    mayRead.allowed ? listInvitations().catch(toNull) : Promise.resolve(null),
  ]);

  const waiting = invitations === null ? 0 : pendingCount(invitations.invitations);

  return (
    <Shell
      locale={locale}
      figures={invitations === null ? null : (
        <>{fill(locale, "invite.pendingCount", { count: waiting }, numbering)}</>
      )}
    >
      {roles === null || catalog === null ? (
        <Banner severity={mayRead.allowed ? "critical" : "info"}>
          {mayRead.allowed ? text("error.unexpected") : text(gateMessage(mayRead))}
        </Banner>
      ) : (
        <>
          {clubs === null ? (
            // **The clubs are MOD-004's and need their own permission**, so a reader who
            // cannot list them is offered the tenant-wide choice and told why the named one
            // is absent rather than shown an empty picker reading as "this tenant has no
            // clubs".
            <Banner severity="info">
              {mayHierarchy.allowed ? text("error.unexpected") : text(gateMessage(mayHierarchy))}
            </Banner>
          ) : null}
          <InviteForm
            roles={roles.map((role) => ({
              role_key: role.role_key,
              display_name: role.display_name,
              description: role.description,
              permissions: role.permissions,
            }))}
            clubs={(clubs ?? []).map((club) => ({
              location_id: club.location_id,
              location_name: club.location_name,
            }))}
            catalog={catalog.permissions.map((one) => ({
              name: one.name, action_class: one.action_class,
            }))}
            locale={locale}
            numbering={numbering}
          />
        </>
      )}

      <section className="ds-panel" aria-labelledby="pending-heading">
        <div className="ds-panel-head">
          <h2 id="pending-heading" className="ds-panel-title">
            {text("invite.pendingTitle")}
          </h2>
        </div>
        <div className="ds-panel-body stack">
          {invitations === null ? (
            <Banner severity={mayRead.allowed ? "critical" : "info"}>
              {mayRead.allowed ? text("error.unexpected") : text(gateMessage(mayRead))}
            </Banner>
          ) : invitations.invitations.length === 0 ? (
            <Banner severity="info">{text("invite.pendingEmpty")}</Banner>
          ) : (
            <DataGrid
              caption={text("invite.pendingTitle")}
              labelledBy="pending-heading"
              rows={invitations.invitations}
              rowKey={(row) => row.invitation_id}
              columns={[
                {
                  header: text("invite.colWho"),
                  kind: "text",
                  priority: 1,
                  // The canvas draws the address and nothing else: an invitation carries no
                  // name, because there is nobody to ask for one until they accept.
                  render: (row: Invitation) => (
                    <span className="data" dir="ltr">{row.email}</span>
                  ),
                },
                {
                  header: text("invite.colRole"),
                  kind: "text",
                  priority: 2,
                  render: (row: Invitation) => row.role_name,
                },
                {
                  header: text("invite.colClubs"),
                  kind: "text",
                  priority: 3,
                  render: (row: Invitation) => {
                    const where = clubNames(row.scopes, clubs ?? []);
                    return where.tenantWide
                      ? text("invite.everyClub")
                      : where.names.join(" · ");
                  },
                },
                {
                  // The canvas's "2d left" and "expired", both derived from the row.
                  header: text("invite.colState"),
                  kind: "status",
                  priority: 1,
                  render: (row: Invitation) => (
                    <>
                      {text(stateKey(row))}
                      {row.state === "pending" ? (
                        <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                          {fill(locale, "invite.daysLeft",
                            { count: row.days_left }, numbering)}
                        </div>
                      ) : null}
                    </>
                  ),
                },
                {
                  header: text("invite.resend"),
                  kind: "text",
                  priority: 1,
                  render: (row: Invitation) => (
                    <PendingActions
                      invitationId={row.invitation_id}
                      locale={locale}
                    />
                  ),
                },
              ]}
            />
          )}
          <ProseNote>{text("invite.listIsDerived")}</ProseNote>
          <ProseNote>{text("invite.nothingSent")}</ProseNote>
        </div>
      </section>
    </Shell>
  );
}

function Shell({
  locale, children, figures,
}: {
  locale: "en" | "ar";
  children: React.ReactNode;
  figures: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "invite.title")}
        {...(figures ? { figures } : {})}
        actions={<Link href="/staff">{t(locale, "invite.back")}</Link>}
      />
      {children}
    </div>
  );
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}
