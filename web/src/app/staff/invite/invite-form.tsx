"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { ChoiceChips } from "@/components/ds/choice-chips";
import { Field } from "@/components/ds/field";
import { fill, t, type Locale, type MessageKey, type Numbering } from "@/i18n/locale";
import { EXPIRY_DAYS, roleReach } from "@/lib/invitations";

import { sendInvitation } from "./invite-actions";
import { IDLE, type InviteState } from "./invite-state";

export type InviteRole = {
  role_key: string;
  display_name: string;
  description: string | null;
  permissions: string[];
};

export type InviteClub = { location_id: string; location_name: string };

/**
 * ADM-STF-03 · INVITE. ADR-0017.
 *
 * **Three fields, and a name is not one of them.** The canvas collects an address, a role
 * and the clubs, and its pending list draws `yasmin@nadi.jo` rather than a person -- so a
 * name field here would be one this app invented, and a copy of somebody's name stored in
 * the plane whose own authentication log deliberately records none. The identity's display
 * name is the invitee's own, typed where they set their password.
 *
 * **The canvas's three fields and the sentence under them.** "The link expires in 7 days.
 * Sales can see leads and members at those two clubs, sell memberships, and take payments. No
 * financial administration." — and two of those three are derived rather than typed: the clubs
 * are this form's own answer, and "no financial administration" is the catalogue's
 * `action_class`, which makes the canvas's claim checkable instead of a sentence somebody
 * wrote. The middle part is the role's own `description`, which `iam.roles` carries.
 *
 * **The link is rendered in place and said to be shown once**, which is the account page's
 * recovery codes exactly: only its digest is stored, so carrying the plaintext through a
 * redirect would mean writing a bearer credential somewhere a browser keeps things.
 *
 * **Nothing is sent**, and the screen says so rather than implying an email went out.
 */
export function InviteForm({
  roles, clubs, catalog, locale, numbering,
}: {
  roles: readonly InviteRole[];
  clubs: readonly InviteClub[];
  catalog: readonly { name: string; action_class: string }[];
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [state, send, sending] = useActionState<InviteState, FormData>(
    sendInvitation, IDLE);
  const [roleKey, setRoleKey] = useState("");
  const [tenantWide, setTenantWide] = useState(false);

  if (state.message === "sent" && state.made !== null) {
    return <MadeLink made={state.made} locale={locale} numbering={numbering} />;
  }

  const role = roles.find((one) => one.role_key === roleKey) ?? null;

  return (
    <form action={send} className="stack">
      {/* **The control is a child and carries `aria-required`, not the shell's `required`.**
          A native constraint refuses the submit itself, with the browser's own bubble in the
          browser's own language -- so `invite.emailNeeded`, which the design draws, would be
          a branch nothing could render. ADM-MEM-10's phone field is the precedent and its
          comment says the same thing; the browser test here is what found this one. `type`
          is `text` for the same reason: `type="email"` validates the format natively and
          blocks a malformed address before the form's own answer can be given. */}
      <Field
        id="invite-email" name="email" label={text("invite.email")}
        required rarer="optional"
        {...(state.missing.email ? {
          message: { kind: "error" as const, text: text("invite.emailNeeded") },
        } : {})}
      >
        <input
          id="invite-email" name="email" type="text" inputMode="email" dir="ltr"
          aria-required="true" autoComplete="off" className="ds-field-input data"
          aria-invalid={state.missing.email ? true : undefined}
          defaultValue={state.echo.email ?? ""}
        />
      </Field>
      <Field
        id="invite-role" name="role_key" type="select" label={text("invite.role")}
        required rarer="optional"
        {...(state.missing.role ? {
          message: { kind: "error" as const, text: text("invite.roleNeeded") },
        } : {})}
      >
        <select
          id="invite-role" name="role_key" className="ds-field-input"
          value={roleKey} onChange={(event) => setRoleKey(event.target.value)}
        >
          <option value="">{text("invite.roleChoose")}</option>
          {roles.map((one) => (
            <option key={one.role_key} value={one.role_key}>{one.display_name}</option>
          ))}
        </select>
      </Field>

      {/* **The clubs, and the tenant-wide case as its own choice.** The service refuses the
          two together -- the wider one already covers the narrower -- so the form offers one
          or the other rather than letting a reader build a pair the server rejects. */}
      <ChoiceChips
        name="tenant_wide_choice"
        legend={text("invite.where")}
        single
        options={[
          { value: "clubs", label: text("invite.whereClubs") },
          { value: "tenant", label: text("invite.whereTenant") },
        ]}
        defaultSelected={["clubs"]}
        onChange={(values) => setTenantWide(values[0] === "tenant")}
      />
      <input type="hidden" name="tenant_wide" value={tenantWide ? "on" : "off"} />
      {tenantWide ? (
        <Banner severity="attention">{text("invite.whereTenantMeans")}</Banner>
      ) : (
        <ChoiceChips
          name="clubs"
          legend={text("invite.clubs")}
          options={clubs.map((one) => ({
            value: one.location_id, label: one.location_name,
          }))}
          {...(state.missing.clubs ? { note: (
            <span className="field-message field-message-error">
              {text("invite.clubsNeeded")}
            </span>
          ) } : {})}
        />
      )}

      <Reach role={role} catalog={catalog} locale={locale} numbering={numbering} />

      {state.error === null ? null : (
        <Banner severity={state.error === "invite.needsStepUp" ? "info" : "critical"}>
          {text(state.error)}
          {state.error === "invite.needsStepUp" ? (
            <>
              {" "}
              <Link
                href={"/step-up?for=financial&action=authz.assignment.write"
                  + "&next=%2Fstaff%2Finvite"}
              >
                {text("invite.raise")}
              </Link>
            </>
          ) : null}
        </Banner>
      )}

      <div className="row">
        <Button type="submit" variant="primary" size="lg"
          state={sending ? "loading" : "default"}
          label={text("invite.send")} />
        <Link href="/staff">{text("invite.back")}</Link>
      </div>
    </form>
  );
}

/**
 * The canvas's sentence, as the facts it is made of.
 *
 * **Absent until a role is chosen**, because a sentence about no role is a sentence about
 * nothing — and the expiry is stated whatever is chosen, since it is the one fact that does
 * not depend on it.
 */
function Reach({
  role, catalog, locale, numbering,
}: {
  role: InviteRole | null;
  catalog: readonly { name: string; action_class: string }[];
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel">
      <div className="ds-panel-body stack">
        <p style={{ margin: 0 }}>
          {fill(locale, "invite.expiresIn", { count: EXPIRY_DAYS }, numbering)}
        </p>
        {role === null ? (
          <p className="muted" style={{ margin: 0 }}>{text("invite.chooseRoleFirst")}</p>
        ) : (
          <RoleReach role={role} catalog={catalog} locale={locale}
            numbering={numbering} />
        )}
      </div>
    </section>
  );
}

function RoleReach({
  role, catalog, locale, numbering,
}: {
  role: InviteRole;
  catalog: readonly { name: string; action_class: string }[];
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  // The catalogue is the server's and arrives with the page; the count is what makes "no
  // financial administration" a claim about the role rather than a sentence somebody typed.
  const reach = roleReach(role, [...catalog]);
  return (
    <>
      {reach.description === null ? (
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "invite.grantsCount", { count: reach.permissions }, numbering)}
        </p>
      ) : (
        <p style={{ margin: 0 }}>{reach.description}</p>
      )}
      <p style={{ margin: 0 }}>
        {reach.financial === 0
          ? text("invite.noFinancial")
          : fill(locale, "invite.someFinancial",
            { count: reach.financial }, numbering)}
      </p>
    </>
  );
}

/**
 * The link, once.
 *
 * **It is not a success message with a link in it; it is the link.** Nothing sends the
 * invitation, so this is the only way it reaches the person -- and a reader who assumed it
 * could be fetched again would copy nothing down. The account page's recovery codes say the
 * same thing for the same reason.
 */
function MadeLink({
  made, locale, numbering,
}: {
  made: { token: string; email: string; expires_at: string; note: string };
  locale: Locale;
  numbering: Numbering;
}) {
  const text = (key: MessageKey) => t(locale, key);
  return (
    <section className="ds-panel">
      <div className="ds-panel-head">
        <h2 className="ds-panel-title">{text("invite.madeTitle")}</h2>
      </div>
      <div className="ds-panel-body stack">
        <p style={{ margin: 0 }}>
          {fill(locale, "invite.madeFor", { email: made.email })}
        </p>
        <Banner severity="attention">{text("invite.shownOnce")}</Banner>
        <p className="data" dir="ltr" style={{
          margin: 0, wordBreak: "break-all",
          background: "var(--color-surface-sunken)",
          padding: "var(--space-3)", borderRadius: "var(--radius-button)",
        }}>
          {made.token}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          {fill(locale, "invite.expiresOn", {
            on: made.expires_at.slice(0, 10),
          })}
          {" "}
          {fill(locale, "invite.daysStated", { count: EXPIRY_DAYS }, numbering)}
        </p>
        <Banner severity="attention">{text("invite.nothingSent")}</Banner>
        <p style={{ margin: 0 }}>
          <Link href="/staff/invite">{text("invite.another")}</Link>
          {" · "}
          <Link href="/staff">{text("invite.back")}</Link>
        </p>
      </div>
    </section>
  );
}
