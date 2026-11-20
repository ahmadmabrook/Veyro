import { redirect } from "next/navigation";

import { signOut } from "@/app/actions";
import { Alert, Button } from "@/components/controls";
import { formatInteger, t, type MessageKey } from "@/i18n/locale";
import { currentSession, gate, type GateAnswer } from "@/lib/api";
import { presentation } from "@/lib/preferences";

/**
 * The Admin landing page: what this session is, and what the gate says it may do.
 *
 * **Every control's visibility comes from `GET /authz/check`**, which asks the real evaluator
 * about the caller's own session. The alternative -- fetching a permission list and deciding in
 * the browser -- is MOD-014's "a grant is not a session" finding: `effective_permissions`
 * answers from role assignments alone and says nothing about the session's assurance level, so
 * a password-only session would render controls it cannot use.
 *
 * The three answers are rendered as three different things, because they are three different
 * facts: allowed, needs a stronger sign-in, or not reachable in this build at all. The last one
 * is the honest one -- `support.session.start` is `privileged`, which maps to AAL 3, which needs
 * a hardware factor MOD-007 cannot verify, so inviting a step-up would send somebody looking for
 * a key the product cannot check.
 */
export default async function HomePage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  // A small, representative set across the modules that are built, so the page shows the gate
  // working rather than asserting that it does. One read, one write, one access decision, one
  // financial action, one money read and one that this build cannot reach at all.
  const actions = [
    "people.person.read",
    "booking.booking.write",
    "access.decision.evaluate",
    "devices.command.unlock",
    "finance.ledger.read",
    "support.session.start",
  ] as const;
  const answers = await Promise.all(actions.map((action) => gate(action)));

  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-4)",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h1 style={{ margin: 0 }}>{text("home.title")}</h1>
        <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
          {/* **The link is rendered only when the gate allows the read.** A navigation item
              that leads to a 403 is a disclosure that the capability exists and a dead end
              for the person who clicks it. MOD-008 computes this per action; the page asks. */}
          <form action={signOut}>
            <Button type="submit">{text("nav.signOut")}</Button>
          </form>
        </div>
      </header>

      <section className="panel stack">
        <h2>{text("home.signedInAs")}</h2>
        {/* `.data` is mono and tabular, and switches family in Arabic so an identifier does not
            arrive in a proportional Arabic face. The id itself is Latin either way. */}
        <p className="data" style={{ margin: 0 }}>
          {session.identity_id}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          {text("home.assurance")}{" "}
          <span className="data">{formatInteger(Number(session.aal ?? 1), "latn")}</span>
        </p>
      </section>

      <section className="panel stack" aria-labelledby="permissions-heading">
        <h2 id="permissions-heading">{text("home.permissions")}</h2>
        {answers.every((answer) => !answer.allowed) ? (
          <Alert tone="info">{text("home.noPermissions")}</Alert>
        ) : null}
        {/* `aria-labelledby` rather than a `<caption>`: the caption said exactly what the
            heading two lines above it said, so a sighted reader saw the sentence twice and a
            screen-reader user heard it twice. A table still needs an accessible name -- it is
            what lets somebody jump between tables -- and pointing at the heading gives it one
            without repeating it. */}
        <table
          tabIndex={0}
          aria-labelledby="permissions-heading"
          style={{ width: "100%", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              <th scope="col" style={headCell}>
                {text("home.action")}
              </th>
              <th scope="col" style={headCell}>
                {text("home.gate")}
              </th>
            </tr>
          </thead>
          <tbody>
            {answers.map((answer) => (
              <tr key={answer.action}>
                <td style={cell}>
                  {/* A permission name is a Latin identifier inside what may be an RTL
                      paragraph, so it is isolated by `.data` + `dir="ltr"` rather than left to
                      the bidi algorithm, which would move the dots. */}
                  <span className="data" dir="ltr">
                    {answer.action}
                  </span>
                </td>
                <td style={cell}>{text(describe(answer))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

/** Hairline rules rather than fills, and `start` alignment so RTL mirrors without a rule. */
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
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border-subtle)",
};

/**
 * Four answers, four messages -- and the order matters.
 *
 * `reachable: false` is checked before `step_up_required`, because the gate sets both for an
 * AAL-3 action: it is true that a stronger sign-in is required and false that one is available.
 * Reading them the other way round would offer a step-up that can never succeed.
 */
function describe(answer: GateAnswer): MessageKey {
  if (answer.allowed) return "gate.allowed";
  if (!answer.reachable) return "gate.unreachable";
  if (answer.step_up_required) return "gate.stepUp";
  return "gate.denied";
}
