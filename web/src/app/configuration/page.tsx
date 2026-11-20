import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  evaluateFlags,
  flagReason,
  isUnset,
  listDefinitions,
  readResolved,
  type ConfigDefinition,
  type FlagDecision,
  type ResolvedValue,
} from "@/lib/configuration";
import { presentation } from "@/lib/preferences";

/**
 * What this tenant has configured, and what its feature flags say.
 *
 * **Three things on this page are answers with a reason attached, and the reason is the point.**
 *
 *   * A resolved value carries the scope it came from. `default` means nobody set it, which is
 *     a different fact from a tenant that published the same value on purpose -- and the two
 *     are indistinguishable if only the value is rendered. The version is `null` in exactly
 *     that case, because there is no published version behind a default.
 *   * A flag's variant carries why. `off` could be a kill switch somebody engaged, a flag
 *     nobody enabled, or a targeting rule that deliberately sent this subject to the control
 *     arm, and an operator in an incident needs to know which. A kill switch outranks every
 *     rule, which is what makes it the one worth marking.
 *   * A rule's id is not a reason. `rule:0f3a…` tells a reader nothing; "a targeting rule
 *     matched" is the answer, and the id stays in the data for somebody debugging.
 *
 * **A flag is evaluated per subject, and there is no route that lists flags without evaluating
 * them.** So this board is "what these flags say for one subject" rather than "what flags
 * exist", which the page says rather than leaving somebody to infer that a flag they cannot
 * see is absent. The subject defaults to the reader's own identity -- derived, not accepted --
 * and a link may name another.
 */
export default async function ConfigurationPage({
  searchParams,
}: {
  searchParams: Promise<{ subject?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const [mayConfig, mayFlags] = await Promise.all([
    gate("config.definition.read"),
    gate("config.flag.read"),
  ]);

  const params = await searchParams;
  // **Derived unless a link names one.** A subject is what a rollout bucket is computed from,
  // so "the flags say off" is only meaningful beside whose flags they are.
  const subject = params.subject?.trim() || session.identity_id;

  const [definitions, resolved, flags] = await Promise.all([
    mayConfig.allowed ? listDefinitions().catch(toNull) : null,
    mayConfig.allowed ? readResolved().catch(toNull) : null,
    mayFlags.allowed ? evaluateFlags(subject).catch(toNull) : null,
  ]);

  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{text("config.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("config.lead")}
      </p>

      <section className="panel stack">
        <h2 id="config-heading" style={{ margin: 0 }}>
          {text("config.registry")}
        </h2>
        {!mayConfig.allowed ? (
          <Alert tone="info">
            {mayConfig.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : definitions === null || resolved === null ? (
          <Alert tone="error">{text("error.unexpected")}</Alert>
        ) : definitions.length === 0 ? (
          <Alert tone="info">{text("config.noDefinitions")}</Alert>
        ) : (
          <>
            <table
              tabIndex={0}
              aria-labelledby="config-heading"
              style={{ width: "100%", borderCollapse: "collapse" }}
            >
              <thead>
                <tr>
                  <th scope="col" style={headCell}>{text("config.key")}</th>
                  <th scope="col" style={headCell}>{text("config.value")}</th>
                  <th scope="col" style={headCell}>{text("config.scope")}</th>
                  <th scope="col" style={headCell}>{text("config.owner")}</th>
                </tr>
              </thead>
              <tbody>
                {definitions.map((definition) => (
                  <Row
                    key={definition.definition_id}
                    definition={definition}
                    resolved={resolved[definition.config_key]}
                    locale={locale}
                  />
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ margin: 0 }}>
              {text("config.unsetExplained")}
            </p>
          </>
        )}
      </section>

      <section className="panel stack">
        <h2 id="flags-heading" style={{ margin: 0 }}>
          {text("config.flags")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("config.flagsLead")}{" "}
          <span className="data" dir="ltr">
            {subject}
          </span>
        </p>
        {!mayFlags.allowed ? (
          <Alert tone="info">
            {mayFlags.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : flags === null ? (
          <Alert tone="error">{text("error.unexpected")}</Alert>
        ) : Object.keys(flags).length === 0 ? (
          <Alert tone="info">{text("config.noFlags")}</Alert>
        ) : (
          <>
            <table
              tabIndex={0}
              aria-labelledby="flags-heading"
              style={{ width: "100%", borderCollapse: "collapse" }}
            >
              <thead>
                <tr>
                  <th scope="col" style={headCell}>{text("config.flag")}</th>
                  <th scope="col" style={headCell}>{text("config.variant")}</th>
                  <th scope="col" style={headCell}>{text("config.why")}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(flags).map(([key, decision]) => (
                  <FlagRow key={key} flagKey={key} decision={decision} locale={locale} />
                ))}
              </tbody>
            </table>
            {Object.values(flags).some(
              (decision) => flagReason(decision) === "kill_switch",
            ) ? (
              <Alert tone="error">{text("config.killSwitchEngaged")}</Alert>
            ) : null}
            <p className="muted" style={{ margin: 0 }}>
              {text("config.noFlagList")}
            </p>
          </>
        )}
      </section>
    </div>
  );
}

function Row({
  definition,
  resolved,
  locale,
}: {
  definition: ConfigDefinition;
  resolved: ResolvedValue | undefined;
  locale: Locale;
}) {
  const text = (key: MessageKey) => t(locale, key);
  // A definition with no resolved entry cannot happen -- `/config/resolved` is built from the
  // same registry -- but rendering `undefined` as a value would be the one answer that is
  // always wrong, so it says so instead.
  if (resolved === undefined) {
    return (
      <tr>
        <td style={cell}>
          <span className="data" dir="ltr">
            {definition.config_key}
          </span>
        </td>
        <td style={cell} colSpan={3}>
          <span className="muted">{text("error.unexpected")}</span>
        </td>
      </tr>
    );
  }
  return (
    <tr>
      <td style={cell}>
        <span className="data" dir="ltr">
          {definition.config_key}
        </span>
        {definition.description !== null ? (
          <div className="muted" style={{ fontSize: "var(--type-label-size)" }}>
            {definition.description}
          </div>
        ) : null}
      </td>
      <td style={cell}>
        <span className="data" dir="ltr">
          {JSON.stringify(resolved.value)}
        </span>
      </td>
      <td style={cell}>
        {isUnset(resolved) ? (
          <span className="muted">{text("config.unset")}</span>
        ) : (
          <>
            {resolved.scope_type}
            {resolved.version !== null ? (
              <span className="muted">
                {" · v"}
                <span className="data">{formatInteger(resolved.version, "latn")}</span>
              </span>
            ) : null}
          </>
        )}
      </td>
      <td style={cell}>
        <span className="data" dir="ltr">
          {definition.owner_module}
        </span>
      </td>
    </tr>
  );
}

function FlagRow({
  flagKey,
  decision,
  locale,
}: {
  flagKey: string;
  decision: FlagDecision;
  locale: Locale;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const reason = flagReason(decision);
  const label: Record<ReturnType<typeof flagReason>, MessageKey> = {
    kill_switch: "config.reason.killSwitch",
    disabled: "config.reason.disabled",
    rule: "config.reason.rule",
    default: "config.reason.default",
  };
  return (
    <tr>
      <td style={cell}>
        <span className="data" dir="ltr">
          {flagKey}
        </span>
      </td>
      <td style={cell}>
        <span className="data" dir="ltr">
          {decision.variant}
        </span>
      </td>
      <td style={cell}>{text(label[reason])}</td>
    </tr>
  );
}

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
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
