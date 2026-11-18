import { setLocale, setTheme } from "@/app/actions";
import { LOCALES, t, type Locale } from "@/i18n/locale";
import type { Theme } from "@/lib/preferences";

/**
 * Language and theme, as two tiny forms.
 *
 * **Buttons in a form, not a `<select onChange>`.** The whole interface's direction depends on
 * this choice, so it has to work before any client bundle does; a `<select>` that needs an
 * `onChange` handler to do anything is the same dependency the sign-in form was just fixed to
 * remove. Each option is a submit button carrying its own value, which degrades to an ordinary
 * POST and re-renders the page in the new language.
 *
 * The current value is a button too, marked `aria-current` and disabled: a control that looks
 * pressable and does nothing is worse than one that says it is already selected.
 */
export function LocaleSwitch({ locale, theme }: { locale: Locale; theme?: Theme }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
      <form action={setLocale} style={group}>
        {/* A visible group name, because two unlabelled buttons reading "AR" and "EN" are a
            puzzle to a screen-reader user arriving at them out of context. */}
        <span className="muted" style={legend}>
          {t(locale, "nav.language")}
        </span>
        {LOCALES.map((option) => (
          <Choice
            key={option}
            name="locale"
            value={option}
            current={option === locale}
            label={option === "ar" ? "العربية" : "English"}
          />
        ))}
      </form>

      {theme ? (
        <form action={setTheme} style={group}>
          <span className="muted" style={legend}>
            {t(locale, "nav.theme")}
          </span>
          <Choice
            name="theme"
            value="light"
            current={theme === "light"}
            label={t(locale, "theme.light")}
          />
          <Choice
            name="theme"
            value="dark"
            current={theme === "dark"}
            label={t(locale, "theme.dark")}
          />
        </form>
      ) : null}
    </div>
  );
}

function Choice({
  name,
  value,
  current,
  label,
}: {
  name: string;
  value: string;
  current: boolean;
  label: string;
}) {
  return (
    <button
      type="submit"
      name={name}
      value={value}
      aria-current={current ? "true" : undefined}
      disabled={current}
      style={{
        minHeight: "44px",
        padding: "var(--space-1) var(--space-3)",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-button)",
        background: current ? "var(--color-surface-selected)" : "var(--color-surface-default)",
        color: "var(--color-text-primary)",
        fontFamily: "inherit",
        fontSize: "var(--type-label-size)",
        fontWeight: "var(--type-label-weight)",
        cursor: current ? "default" : "pointer",
      }}
    >
      {label}
    </button>
  );
}

const group: React.CSSProperties = {
  display: "flex",
  gap: "var(--space-1)",
  alignItems: "center",
};

const legend: React.CSSProperties = {
  fontSize: "var(--type-caption-size)",
  // `margin-inline-end`, never `margin-right`: the whole point of logical properties here is
  // that this row mirrors in Arabic without a single RTL-specific rule.
  marginInlineEnd: "var(--space-1)",
};
