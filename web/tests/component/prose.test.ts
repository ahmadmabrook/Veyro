import { describe, expect, it } from "vitest";

import { segments } from "@/lib/prose";

/**
 * The registry's reasons carry Markdown, and the privacy board was printing it literally.
 *
 * They were written where `**` is emphasis and a backtick is a column name -- in a Python
 * module a developer reads -- so a page rendering them as plain text shows
 * `**who pays.** The account is...`, which is punctuation nobody wrote for a reader, in the
 * one block whose job is to be read by somebody who is not a developer.
 *
 * Stripping the markers was the worse of the two fixes: the emphasis is each reason's summary
 * phrase, so throwing it away loses the part a skimming reader needs most.
 */

describe("segments", () => {
  it("keeps the emphasis as emphasis rather than as asterisks", () => {
    expect(segments("**who pays.** The account is the party")).toEqual([
      { kind: "strong", value: "who pays." },
      { kind: "text", value: " The account is the party" },
    ]);
  });

  it("recognises a backticked column name", () => {
    expect(segments("beside it carries `rendered_subject` and more")).toEqual([
      { kind: "text", value: "beside it carries " },
      { kind: "code", value: "rendered_subject" },
      { kind: "text", value: " and more" },
    ]);
  });

  it("handles several of both in one sentence", () => {
    const parts = segments("**a.** see `x` then **b.** and `y`");
    expect(parts.map((p) => p.kind)).toEqual([
      "strong", "text", "code", "text", "strong", "text", "code",
    ]);
  });

  it("leaves an unmatched delimiter as literal text", () => {
    // Not a Markdown parser and must not become one: anything it does not recognise as a
    // pair stays exactly as written rather than being guessed at.
    expect(segments("a ** dangling marker")).toEqual([
      { kind: "text", value: "a ** dangling marker" },
    ]);
    expect(segments("a ` dangling tick")).toEqual([
      { kind: "text", value: "a ` dangling tick" },
    ]);
  });

  it("returns plain text unchanged, as one segment", () => {
    expect(segments("insert-only decision; no UPDATE grant on this column")).toEqual([
      { kind: "text", value: "insert-only decision; no UPDATE grant on this column" },
    ]);
  });

  it("returns nothing for an empty string rather than one empty segment", () => {
    expect(segments("")).toEqual([]);
  });
});
