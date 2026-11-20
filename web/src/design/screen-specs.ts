import generated from "@/design/screens.generated.json";

/**
 * Reading the extracted screen designs.
 *
 * The file is `screen-specs.ts` rather than `screens.ts` because `@/design/screens` resolves
 * to `screens.mjs` -- the generator -- under Vite's extension order, so the accessor silently
 * became the generator and every named import was undefined.
 *
 * `screens.generated.json` is produced by `screens.mjs` from
 * `veyro-product-experience-design/` and pinned by SHA-256. This is the only way a screen or a
 * test reaches into it, so the shape is in one place: the first version of the extraction
 * changed shape and every call site had to be found by grep.
 *
 * **A screen that cites a specification it cannot find should fail loudly.** `specFor` throws
 * on an unknown id rather than returning undefined, because the alternative is a page whose
 * comment claims ADM-CC-01 and whose test quietly asserts nothing.
 */

export type ScreenSection = {
  kind: string;
  title: string;
  file: string;
  text: string;
};

export type ScreenSpec = {
  id: string;
  surface: string;
  module: string;
  name: string;
  roles: string;
  arabic: string;
  arabic_reference: string | null;
  registry_status: string;
  registry_note: string;
  specified: boolean;
  sections: ScreenSection[];
};

export const COVERAGE: {
  v1_screens: number;
  specified: number;
  no_ui: number;
  unspecified: number;
  unspecified_ids: string[];
} = generated.coverage;

export const SCREENS: ScreenSpec[] = generated.screens;

export const SOURCES: { file: string; sha256: string; sections: number }[] = generated.sources;

/** The specification for one screen id, or an error naming the id that was not found. */
export function specFor(id: string): ScreenSpec {
  const found = SCREENS.find((screen) => screen.id === id);
  if (!found) throw new Error(`${id} is not in the extracted screen designs`);
  return found;
}

/** Every section's text for one screen, joined — what the design says about it, in full. */
export function specTextFor(id: string): string {
  return specFor(id).sections.map((section) => section.text).join("\n");
}
