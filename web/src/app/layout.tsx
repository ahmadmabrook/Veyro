import type { Metadata } from "next";

import { LocaleSwitch } from "@/components/locale-switch";
import { t } from "@/i18n/locale";
import { presentation } from "@/lib/preferences";

import "./globals.css";

export const metadata: Metadata = {
  title: "Veyro",
  description: "Veyro gym management.",
};

/**
 * The root layout sets `lang`, `dir` and `data-theme` on `<html>`, which is what makes RTL and
 * the dark mapping work at all.
 *
 * **All three come from one place and none is a prop.** `dir` is derived from the locale by
 * `direction()`, so a component cannot be rendered LTR inside an Arabic document by passing the
 * wrong value -- and CSS logical properties (`inset-inline-start`, `margin-inline`) then mirror
 * the whole interface without a single RTL-specific rule. The theme is read from a cookie on
 * the server rather than detected in the browser, because detecting it in the browser is the
 * flash of the wrong theme.
 */
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { locale, dir, theme } = await presentation();

  return (
    <html lang={locale} dir={dir} data-theme={theme}>
      <body>
        {/* First focusable thing on every page: a keyboard user should not tab the whole nav. */}
        <a className="skip-link" href="#main">
          {t(locale, "app.skipToContent")}
        </a>
        {/* **In the layout, so every page has it.** The first version put the language and
            theme controls on the landing page and the sign-in page, which left a reader who
            followed a link to a zone with no way back to their own language -- and made the
            direction of the whole document depend on which page they happened to enter by. */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            padding: "var(--space-4) var(--space-4) 0",
          }}
        >
          <LocaleSwitch locale={locale} theme={theme} />
        </div>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
