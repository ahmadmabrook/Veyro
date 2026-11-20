/**
 * Icon — §15, and the three rules that make it a component rather than a glyph.
 *
 * > 1.5px stroke on a 24px grid, optically corrected at 16px rather than scaled. Sizes:
 * > 16 / 20 / 24 / 32. **Icons never carry meaning alone — every status icon ships with its
 * > label, so an icon-only status is a defect, not a density choice.**
 * >
 * > MIRRORS IN RTL — arrows · chevrons · back / forward · indent · send · reply · trend
 * > direction · progress · list-to-detail affordance
 * > NEVER MIRRORS — clock · search · checkmark · media play · QR · logos · numerals ·
 * > dumbbell · barcode · brand marks
 *
 * **`aria-hidden` always, and there is no prop to change it.** The rule above is absolute:
 * an icon is never the only carrier of meaning, so it is never in the accessibility tree.
 * Every call site pairs it with text -- a rail item's label, a button's label, a status's
 * word. A component that could be made accessible would be a component somebody uses alone.
 *
 * **Mirroring is per icon and declared here**, which is the icon manifest the compliance
 * ledger has carried as unresolved. The design folder ships no manifest, so this is the two
 * lists above turned into data: `MIRRORS` holds the directional ones and everything else is
 * fixed. A new icon joins one list or the other at the moment it is drawn.
 *
 * **The canvases draw geometric Unicode glyphs** -- `◈ ◷ ◱ ◍ ◎ ◐ ◫ ◧ ◨ ◊ ⚙` -- which is an
 * HTML prototype standing in for an icon set it cannot ship. The specification is the 24px
 * grid and the 1.5px stroke, and that is what these are; copying the glyphs would be copying
 * the prototype's limitation rather than the design.
 */

export const ICON_SIZES = [16, 20, 24, 32] as const;
export type IconSize = (typeof ICON_SIZES)[number];

/** The directional set from §15. Everything not here is fixed under `dir="rtl"`. */
const MIRRORS = new Set([
  "chevron-down",
  "chevron-end",
  "arrow-end",
  "arrow-start",
  "send",
  "reply",
  "trend-up",
  "trend-down",
  "indent",
]);

/**
 * The paths, all on a 24 grid.
 *
 * Geometric and plain on purpose: the design's own marks are geometric, and a decorative
 * icon set would fight the one thing §15 asks for, which is that an icon reads at 16px.
 */
const PATHS: Record<string, string> = {
  // OPERATE
  "command-center": "M12 3 L21 12 L12 21 L3 12 Z M12 8.5 L15.5 12 L12 15.5 L8.5 12 Z",
  scheduling: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18 Z M12 7v5l3.5 2",
  "front-desk": "M3 7h18v10H3z M3 12h8 M7 7v10",
  // PEOPLE
  members: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18 Z M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7 Z",
  leads: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18 Z M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10 Z",
  staff: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18 Z M12 3v18",
  permissions: "M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z M9 12l2 2 4-4",
  // MONEY
  payments: "M3 6h18v12H3z M3 10h18 M7 14h4",
  "point-of-sale": "M3 5h18v14H3z M9 5v14",
  reports: "M4 20V10 M10 20V4 M16 20v-7 M20 20V7",
  // DELIVER
  coaching: "M12 3 L19 7.5 v9 L12 21 L5 16.5 v-9 Z",
  automations: "M12 3 L21 12 L12 21 L3 12 Z M7 12h10",
  messages: "M4 5h16v11H9l-5 4z",
  integrations: "M8 4h8v5h5v8H3V9h5z M12 9v8",
  // SYSTEM
  doors: "M5 3h11v18H5z M12.5 12.5h.01 M19 3v18",
  devices: "M7 3h10v18H7z M10 19.5h4",
  organization: "M12 3v5 M6 21v-6a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v6 M12 8v4",
  configuration: "M4 7h16 M4 12h16 M4 17h16 M9 5v4 M15 10v4 M7 15v4",
  privacy: "M6 10V8a6 6 0 0 1 12 0v2 M4 10h16v11H4z",
  operations: "M3 12h4l2.5-6 4 13 2.5-7H21",
  account: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 Z M4.5 20a7.5 7.5 0 0 1 15 0",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18 Z M9.5 9.5a2.5 2.5 0 1 1 3 2.5v1.5 M12 17h.01",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6 Z M12 2.5v3 M12 18.5v3 M2.5 12h3 M18.5 12h3 M5.3 5.3l2.1 2.1 M16.6 16.6l2.1 2.1 M18.7 5.3l-2.1 2.1 M7.4 16.6l-2.1 2.1",
  // Directional
  "chevron-down": "M7 10l5 5 5-5",
  "chevron-end": "M9 5l7 7-7 7",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14 Z M16.5 16.5L21 21",
  tasks: "M4 7l2.5 2.5L11 5 M4 17l2.5 2.5L11 13 M14 7h6 M14 17h6",
  alerts: "M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6 Z M10 19a2 2 0 0 0 4 0",
};

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  size = 20,
}: {
  name: IconName;
  /** 16, 20, 24 or 32. Nothing else: "optically corrected at 16px rather than scaled". */
  size?: IconSize;
}) {
  const path = PATHS[name];
  if (path === undefined) throw new Error(`no icon named ${name}`);
  return (
    <svg
      className="ds-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      // Never in the accessibility tree. §15 is absolute: an icon never carries meaning
      // alone, so every call site pairs it with text and this is decoration.
      aria-hidden="true"
      focusable="false"
      data-mirrors={MIRRORS.has(name) ? "true" : "false"}
    >
      <path d={path} />
    </svg>
  );
}

/** Whether an icon turns around under `dir="rtl"`. Exported so a test can assert the lists. */
export function mirrors(name: string): boolean {
  return MIRRORS.has(name);
}

export const ICON_NAMES = Object.keys(PATHS) as IconName[];
