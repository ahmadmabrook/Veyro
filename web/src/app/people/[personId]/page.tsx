import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert } from "@/components/controls";
import { MembershipPanels } from "@/components/membership-panels";
import { Withheld } from "@/components/withheld";
import { formatInteger, t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import {
  isWithheld,
  readMember360,
  splitSections,
  type Member360,
  type Note,
  type Person,
} from "@/lib/people";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * Member 360: the composed view, with every section's provenance and every mask marked.
 *
 * **This is the one surface in the build where `Decision.mask` reaches a reader**, and the
 * rendering is the point. MOD-008 computed `masked_fields` on every allowed decision and from
 * MOD-008 to MOD-013 nothing read it; MOD-014 applies it, and a page that dropped a masked
 * value would undo that in the place it matters -- an empty cell is indistinguishable from
 * "there was nothing here", which is the one reading that is always wrong.
 *
 * So a withheld value is **marked, with its reason**, and the two reasons have different
 * remedies: an identity field needs a stronger sign-in (which this app cannot yet offer -- see
 * the gap below), and a health field cannot be read by anybody in this build, because
 * `member.health.read` is `biometric_sensitive`, which maps to assurance level 3, which needs a
 * hardware authenticator MOD-007 cannot verify.
 *
 * **The absent sections say which module is missing.** Paragraph 816 makes the 360 a
 * composition rather than a stored row, and seven of its areas belong to modules this
 * repository does not have. Rendering those as empty lists would read as "none", which is the
 * difference between "this member has no outstanding balance" and "nothing here knows".
 */
export default async function Member360Page({
  params,
}: {
  params: Promise<{ personId: string }>;
}) {
  const { personId } = await params;
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("people.person.read");
  if (!may.allowed) {
    return (
      <Shell locale={locale}>
        <Alert tone="info">
          {may.reachable ? text("gate.denied") : text("gate.unreachable")}
        </Alert>
      </Shell>
    );
  }

  let record: Member360;
  try {
    record = await readMember360(personId);
  } catch (error) {
    // **A malformed id in the URL is "no such person", not "something went wrong".** The
    // route shape-checks the id and answers 422 `bad_person_id`; rendering that as an
    // unexpected error tells the reader the product is broken when what happened is that
    // they followed a bad link. 404 and 422 are the same fact to somebody reading a page.
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      return (
        <Shell locale={locale}>
          <Alert tone="info">{text("member.notFound")}</Alert>
        </Shell>
      );
    }
    return (
      <Shell locale={locale}>
        <Alert tone="error">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Alert>
      </Shell>
    );
  }

  const { available, unavailable } = splitSections(record.sections);

  return (
    <Shell locale={locale}>
      <IdentityPanel person={record.person} locale={locale} />

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("member.profile")}</h2>
        {record.member_profile === null ? (
          <Alert tone="info">{text("member.noProfile")}</Alert>
        ) : (
          <dl className="facts">
            <Row label={text("member.lifecycle")}>{record.member_profile.lifecycle_state}</Row>
            <Row label={text("member.number")}>
              <span className="data" dir="ltr">
                {record.member_profile.member_number ?? "—"}
              </span>
            </Row>
            <Row label={text("member.joined")}>
              {record.member_profile.joined_on ?? "—"}
            </Row>
          </dl>
        )}
        {record.staff_profile === null ? (
          <p className="muted" style={{ margin: 0 }}>{text("member.noStaff")}</p>
        ) : (
          <dl className="facts">
            <Row label={text("member.staff")}>
              {record.staff_profile.job_title ?? record.staff_profile.employment_state}
            </Row>
          </dl>
        )}
      </section>

      {/* MOD-017, composed rather than joined. The projection above cannot read these
          tables -- paragraph 1300 bars a cross-domain read and its `sections` block says so --
          but a surface can call both modules through both gates, which is where the member's
          agreement belongs: beside the person it is with. */}
      <MembershipPanels personId={personId} locale={locale} />

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("member.notes")}</h2>
        {record.notes.length === 0 ? (
          <Alert tone="info">{text("member.noNotes")}</Alert>
        ) : (
          <ul className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {record.notes.map((note) => (
              <li key={note.note_id}>
                <NoteBody note={note} locale={locale} />
                <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                  {note.note_class}
                  {" · "}
                  <span className="data" dir="ltr">
                    {utcStamp(note.recorded_at)}
                  </span>
                  {note.withdrawn_at ? ` · ${text("member.noteWithdrawn")}` : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("member.timeline")}</h2>
        {record.timeline.length === 0 ? (
          <Alert tone="info">{text("member.noTimeline")}</Alert>
        ) : (
          <ol className="stack" style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
            {record.timeline.map((entry) => (
              <li key={entry.entry_id}>
                {isWithheld(entry.summary) ? (
                  <Withheld locale={locale} reason="member.withheldHealth" />
                ) : (
                  entry.summary
                )}
                <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                  <span className="data" dir="ltr">
                    {entry.event_type} · {utcStamp(entry.occurred_at)}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel stack">
        <h2 style={{ margin: 0 }}>{text("member.sections")}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("member.consents")}:{" "}
          <span className="data">{formatInteger(record.consent_record_count, "latn")}</span>
        </p>
        <dl className="facts">
          {available.map(([name, source]) => (
            <Row key={name} label={name}>
              <span className="muted">{source}</span>
            </Row>
          ))}
        </dl>
        <h3 style={{ margin: 0 }}>{text("member.unavailable")}</h3>
        {/* **Named, not omitted.** A section rendered as an empty list reads as "none".
            And the heading used to say "Not in this build", which was true of every entry
            when it was written and false of four of them by the time somebody looked: the
            modules behind membership, bookings, attendance and finance have all been built
            since. Two reasons live in this list now, and the line below is what tells them
            apart -- a reader who takes "this projection does not read it" for "the product
            does not have it" has been told the wrong thing about their own build. */}
        <p className="muted" style={{ margin: 0 }}>
          {text("member.unavailableWhy")}
        </p>
        <dl className="facts">
          {unavailable.map(([name, why]) => (
            <Row key={name} label={name}>
              <span className="muted">{why}</span>
            </Row>
          ))}
        </dl>
      </section>
    </Shell>
  );
}

function IdentityPanel({ person, locale }: { person: Person; locale: Locale }) {
  const text = (key: MessageKey) => t(locale, key);
  // **The remedy, where the refusal is.** An identity field is withheld because this session is
  // assurance level 1 and `member.identity.read` is a financial action -- which is a thing the
  // reader can fix, unlike the health class, where nobody in this build can. Naming the remedy
  // and not offering it is the dead end MOD-007's review records one layer down.
  const identityWithheld =
    isWithheld(person.legal_name)
    || isWithheld(person.preferred_name)
    || isWithheld(person.date_of_birth);
  return (
    <section className="panel stack">
      <h2 style={{ margin: 0 }}>{text("member.identity")}</h2>
      <dl className="facts">
        <Row label={text("member.legalName")}>
          {isWithheld(person.legal_name) ? (
            <Withheld locale={locale} reason="member.withheldIdentity" />
          ) : (
            person.legal_name
          )}
        </Row>
        <Row label={text("member.preferredName")}>
          {person.preferred_name === null ? (
            "—"
          ) : isWithheld(person.preferred_name) ? (
            <Withheld locale={locale} reason="member.withheldIdentity" />
          ) : (
            person.preferred_name
          )}
        </Row>
        <Row label={text("member.dateOfBirth")}>
          {person.date_of_birth === null ? (
            "—"
          ) : isWithheld(person.date_of_birth) ? (
            <Withheld locale={locale} reason="member.withheldIdentity" />
          ) : (
            <span className="data" dir="ltr">
              {person.date_of_birth}
            </span>
          )}
        </Row>
      </dl>
      {/* **An unknown birth date is not a minor**, which is MOD-014's own uncomfortable and
          correct direction: treating every undated person as one would make a guardian
          relationship mandatory before anybody could read the record of a member who never
          gave a birthday, which is most leads. */}
      {identityWithheld ? (
        <p style={{ margin: 0 }}>
          <Link
            href={`/step-up?for=financial&next=${encodeURIComponent(`/people/${person.person_id}`)}`}
          >
            {text("member.raiseSession")}
          </Link>
        </p>
      ) : null}
      <p className="muted" style={{ margin: 0 }}>
        {person.is_minor ? text("member.minor") : text("member.notMinor")}
      </p>

      <h3 style={{ margin: 0 }}>{text("member.contacts")}</h3>
      {person.contact_points.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{text("member.noContacts")}</p>
      ) : (
        <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
          {person.contact_points.map((contact) => (
            <li key={contact.contact_point_id}>
              {isWithheld(contact.value_raw) ? (
                <Withheld locale={locale} reason="member.withheldIdentity" />
              ) : (
                <span className="data" dir="ltr">
                  {contact.value_raw}
                </span>
              )}
              {" — "}
              {contact.kind}
              {contact.is_primary ? ` · ${text("member.primary")}` : null}
              {" · "}
              {/* **A verification is recorded, not performed**: nothing here sends a code or
                  reads a reply, so the row says a named actor asserted it at a time. */}
              <span className="muted">
                {contact.verified_at ? text("member.verified") : text("member.unverified")}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3 style={{ margin: 0 }}>{text("member.tags")}</h3>
      {person.tags.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{text("member.noTags")}</p>
      ) : (
        <p style={{ margin: 0 }}>
          {person.tags.map((tag) => tag.display_name).join(", ")}
        </p>
      )}

      <h3 style={{ margin: 0 }}>{text("member.customFields")}</h3>
      {person.custom_fields.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{text("member.noCustomFields")}</p>
      ) : (
        <dl className="facts">
          {person.custom_fields.map((field) => (
            <Row key={field.field_key} label={field.display_name}>
              {field.redacted || isWithheld(field.value) ? (
                <Withheld
                  locale={locale}
                  reason={
                    field.sensitivity === "health" || field.sensitivity === "biometric"
                      ? "member.withheldHealth"
                      : "member.withheldIdentity"
                  }
                />
              ) : (
                field.value
              )}
            </Row>
          ))}
        </dl>
      )}

      <h3 style={{ margin: 0 }}>{text("member.relationships")}</h3>
      {person.relationships.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{text("member.noRelationships")}</p>
      ) : (
        <ul style={{ margin: 0, paddingInlineStart: "var(--space-5)" }}>
          {person.relationships.map((relationship) => (
            <li key={relationship.relationship_id}>
              {relationship.kind}
              {" · "}
              <span className="data" dir="ltr">
                {relationship.started_on ?? "—"} → {relationship.ended_on ?? "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NoteBody({ note, locale }: { note: Note; locale: Locale }) {
  if (note.redacted || isWithheld(note.body)) {
    return (
      <Withheld
        locale={locale}
        reason={
          note.visibility_class === "health" || note.visibility_class === "biometric"
            ? "member.withheldHealth"
            : "member.withheldIdentity"
        }
      />
    );
  }
  return <span>{note.body}</span>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="muted">{label}</dt>
      <dd style={{ margin: 0 }}>{children}</dd>
    </>
  );
}

function Shell({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{t(locale, "member.title")}</h1>
      {children}
    </div>
  );
}

