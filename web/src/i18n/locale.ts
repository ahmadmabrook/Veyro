/**
 * Locale, direction and the tenant's numeral setting, as the React layer sees them.
 *
 * The rules themselves live in `conventions.mjs`, which is proven byte-identical to
 * `backend/app/l10n/conventions.py`. This file is the typed surface over it plus the message
 * catalogue -- it adds no formatting of its own, because a second implementation is the thing
 * the parity test exists to prevent.
 */

import {
  direction as rawDirection,
  formatInteger as rawFormatInteger,
  formatMoney as rawFormatMoney,
  isolate as rawIsolate,
  parseLocale,
} from "./conventions.mjs";

export type Locale = "ar" | "en";
export type Direction = "rtl" | "ltr";
/** Latin or Arabic-Indic. **A tenant setting, chosen once** -- never derived from the locale. */
export type Numbering = "latn" | "arab";
export type Script = "latin" | "arabic";

export const LOCALES: readonly Locale[] = ["ar", "en"] as const;
export const DEFAULT_LOCALE: Locale = "en";

export function asLocale(value: unknown): Locale {
  return parseLocale(value) as Locale;
}

/** `ar` is RTL. Derived, never accepted from a caller. */
export function direction(locale: Locale): Direction {
  return rawDirection(locale) as Direction;
}

/** Which script a locale sets type in, which decides how a type token resolves. */
export function script(locale: Locale): Script {
  return locale === "ar" ? "arabic" : "latin";
}

export function formatMoney(
  amountMinor: number,
  currency: string,
  numbering: Numbering,
  locale: Locale,
): string {
  return rawFormatMoney(amountMinor, currency, numbering, locale) as string;
}

export function formatInteger(
  value: number,
  numbering: Numbering,
  grouping = true,
): string {
  return rawFormatInteger(value, numbering, grouping) as string;
}

/**
 * Wrap a run so it cannot re-order the text around it.
 *
 * Mandatory for money, phone numbers, member IDs, card last-four, times and Latin names in
 * Arabic text -- "without it JOD jumps to the wrong side of its amount, a money-ambiguity
 * defect, not a typographic one."
 */
export function isolate(text: string, dir: "ltr" | "rtl" | "auto"): string {
  return rawIsolate(text, dir) as string;
}

/**
 * The message catalogue.
 *
 * **Arabic is not optional and there is no fallback to English.** The foundations' own reason:
 * "quietly sending English to somebody who asked for Arabic is worse than refusing" is
 * MOD-013's rule for notifications, and the same holds on a screen -- a half-translated
 * interface is one a reader cannot trust. `t` throws for a missing key rather than returning
 * the key, so a gap fails a test instead of shipping as English text in an Arabic build.
 */
const MESSAGES = {
  en: {
    "app.name": "Veyro",
    "app.skipToContent": "Skip to content",
    "login.title": "Sign in",
    "login.tenant": "Tenant ID",
    "login.identifier": "Email or phone",
    "login.password": "Password",
    "login.submit": "Sign in",
    "login.working": "Signing in…",
    "login.failed": "Those details were not accepted.",
    "login.challenge": "This sign-in needs a recovery code.",
    "login.tooMany": "Too many attempts. Try again shortly.",
    "login.tenantHint": "The tenant this sign-in belongs to.",
    "login.required": "This field is required.",
    "nav.signOut": "Sign out",
    "nav.language": "Language",
    "nav.theme": "Theme",
    "theme.light": "Light",
    "theme.dark": "Dark",
    "home.title": "Veyro Admin",
    "home.signedInAs": "Signed in as",
    "home.assurance": "Assurance level",
    "home.permissions": "What this session may do",
    "home.noPermissions": "This session holds no permissions yet.",
    "home.action": "Action",
    "home.gate": "Gate",
    "gate.allowed": "Allowed",
    "gate.stepUp": "Needs a stronger sign-in",
    "gate.unreachable": "Not available in this build",
    "gate.denied": "Not permitted",
    "error.network": "The server could not be reached.",
    "error.unexpected": "Something went wrong.",
    "state.loading": "Loading…",
    "state.empty": "Nothing to show.",
  },
  ar: {
    "app.name": "فيرو",
    "app.skipToContent": "تخطَّ إلى المحتوى",
    "login.title": "تسجيل الدخول",
    "login.tenant": "معرّف المستأجر",
    "login.identifier": "البريد الإلكتروني أو الهاتف",
    "login.password": "كلمة المرور",
    "login.submit": "تسجيل الدخول",
    "login.working": "جارٍ تسجيل الدخول…",
    "login.failed": "لم تُقبل هذه البيانات.",
    "login.challenge": "يحتاج تسجيل الدخول هذا إلى رمز استرداد.",
    "login.tooMany": "محاولات كثيرة جدًا. حاول بعد قليل.",
    "login.tenantHint": "المستأجر الذي يتبع له تسجيل الدخول.",
    "login.required": "هذا الحقل مطلوب.",
    "nav.signOut": "تسجيل الخروج",
    "nav.language": "اللغة",
    "nav.theme": "المظهر",
    "theme.light": "فاتح",
    "theme.dark": "داكن",
    "home.title": "إدارة فيرو",
    "home.signedInAs": "مسجَّل الدخول باسم",
    "home.assurance": "مستوى التحقق",
    "home.permissions": "ما يمكن لهذه الجلسة فعله",
    "home.noPermissions": "لا تملك هذه الجلسة أي صلاحيات بعد.",
    "home.action": "الإجراء",
    "home.gate": "البوابة",
    "gate.allowed": "مسموح",
    "gate.stepUp": "يتطلب تسجيل دخول أقوى",
    "gate.unreachable": "غير متاح في هذه النسخة",
    "gate.denied": "غير مسموح",
    "error.network": "تعذّر الوصول إلى الخادم.",
    "error.unexpected": "حدث خطأ ما.",
    "state.loading": "جارٍ التحميل…",
    "state.empty": "لا يوجد ما يُعرض.",
  },
} as const;

export type MessageKey = keyof (typeof MESSAGES)["en"];

export class MissingMessageError extends Error {}

/** Look up a message. Throws on a missing key rather than falling back to the other locale. */
export function t(locale: Locale, key: MessageKey): string {
  const catalogue = MESSAGES[locale];
  const value = catalogue[key];
  if (value === undefined) {
    throw new MissingMessageError(`no ${locale} message for ${key}`);
  }
  return value;
}

/** Every key, so a test can assert both catalogues cover the same set. */
export const MESSAGE_KEYS = Object.keys(MESSAGES.en) as MessageKey[];
export { MESSAGES };
