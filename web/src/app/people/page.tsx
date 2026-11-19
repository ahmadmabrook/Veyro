import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { formatInteger, t, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { listDuplicateCandidates, type DuplicateCandidate } from "@/lib/people";
import { presentation } from "@/lib/preferences";

/**
 * The way into a person's record, and an honest statement that there is no search.
 *
 * **PPL-01 has no list route and that is deliberate on the server's side.** Paragraph 4218
 * puts a permission-aware search index with a mandatory query pre-filter in ENG-01, which is
 * not built, and MOD-014's own notes say a `LIKE` scan presented as search would be a read
 * path with no freshness contract and no pre-filter. So this page does not invent one: it says
 * so, and it offers the one place the module does find people by a value -- the duplicate
 * queue, which draws its candidates through the indexes.
 *
 * **The score is shown with its signals, never alone.** An operator asked to merge two records
 * is being asked to destroy one of them; `dedup.WEIGHTS` is the whole table and there is no
 * fuzzy matching anywhere in it, so every signal is a named exact match.
 */
export default async function PeoplePage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("people.duplicate.review");
  let candidates: DuplicateCandidate[] = [];
  let failed: MessageKey | null = null;
  if (may.allowed) {
    try {
      candidates = await listDuplicateCandidates();
    } catch (error) {
      failed = error instanceof ApiError && error.reason === "unreachable"
        ? "error.network"
        : "error.unexpected";
    }
  }

  return (
    <div className="stack" style={{ padding: "var(--space-6)", maxWidth: "960px" }}>
      <h1 style={{ margin: 0 }}>{text("people.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("people.lead")}
      </p>
      <section className="panel stack">
        <h2 id="duplicates-heading" style={{ margin: 0 }}>
          {text("people.duplicates")}
        </h2>
        {failed ? <Alert tone="error">{text(failed)}</Alert> : null}
        {!may.allowed ? (
          <Alert tone="info">
            {may.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Alert>
        ) : candidates.length === 0 ? (
          <Alert tone="info">{text("people.noDuplicates")}</Alert>
        ) : (
          <table
            aria-labelledby="duplicates-heading"
            style={{ width: "100%", borderCollapse: "collapse" }}
          >
            <thead>
              <tr>
                <th scope="col" style={headCell}>{text("people.score")}</th>
                <th scope="col" style={headCell}>{text("people.signals")}</th>
                <th scope="col" style={headCell}>{text("people.candidate")}</th>
                <th scope="col" style={headCell}>{text("people.detected")}</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr key={candidate.candidate_id}>
                  <td style={cell}>
                    <span className="data">{formatInteger(candidate.score, "latn")}</span>
                  </td>
                  <td style={cell}>
                    {/* **Never the score on its own.** A number with no reasons behind it is
                        not something to destroy a record on. */}
                    {candidate.signals.join(", ")}
                  </td>
                  <td style={cell} className="stack">
                    <Link href={`/people/${candidate.lower_person_id}`}>
                      {text("people.open")} 1
                    </Link>
                    <Link href={`/people/${candidate.higher_person_id}`}>
                      {text("people.open")} 2
                    </Link>
                  </td>
                  <td style={cell}>
                    <span className="data" dir="ltr">
                      {candidate.detected_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
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
