/**
 * The three per-viewer preferences the server has to know before it renders a byte: locale,
 * direction and theme.
 *
 * They are cookies rather than client state because all three change the *first* paint. A
 * locale read in the browser means an English document that becomes Arabic, with `dir` flipping
 * under the reader; a theme read in the browser is the flash of the wrong one. The server has
 * to emit `lang`, `dir` and `data-theme` correctly on `<html>`, so it has to know them before
 * React runs.
 *
 * **Every read here fails soft and every write fails closed.** A stale or hand-edited cookie
 * falls back to the default rather than making every page 500 -- `asLocale` is right to throw
 * at an API boundary and wrong in a layout. A *write* takes only a value from the closed set,
 * because a cookie this app later echoes into an attribute on `<html>` is an injection sink if
 * anything but a known token can reach it.
 */

import { cookies } from "next/headers";

import { DEFAULT_LOCALE, LOCALES, asLocale, direction, type Direction, type Locale } from "@/i18n/locale";

export const LOCALE_COOKIE = "veyro_locale";
export const THEME_COOKIE = "veyro_theme";

export type Theme = "light" | "dark";
export const THEMES: readonly Theme[] = ["light", "dark"] as const;

/** A year: a preference, not a session. Not httpOnly -- nothing secret, and no reader needs it. */
const A_YEAR = 60 * 60 * 24 * 365;

export function safeLocale(value: string | undefined): Locale {
  try {
    return asLocale(value);
  } catch {
    return DEFAULT_LOCALE;
  }
}

export function safeTheme(value: string | undefined): Theme {
  return value === "dark" ? "dark" : "light";
}

export type Presentation = { locale: Locale; dir: Direction; theme: Theme };

/** What the layout needs, read once. */
export async function presentation(): Promise<Presentation> {
  const jar = await cookies();
  const locale = safeLocale(jar.get(LOCALE_COOKIE)?.value);
  return { locale, dir: direction(locale), theme: safeTheme(jar.get(THEME_COOKIE)?.value) };
}

/** Narrow an untrusted string to a locale, or refuse. Used by the write path only. */
export function parseLocaleStrict(value: unknown): Locale | null {
  return LOCALES.includes(value as Locale) ? (value as Locale) : null;
}

export function parseThemeStrict(value: unknown): Theme | null {
  return THEMES.includes(value as Theme) ? (value as Theme) : null;
}

export const PREFERENCE_MAX_AGE = A_YEAR;
