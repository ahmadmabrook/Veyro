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
    "nav.label": "Sections",
    "nav.overview": "Overview",
    "nav.organization": "Organization",
    "nav.access": "Doors",
    "org.title": "Organization",
    "org.lead": "The hierarchy every other surface is scoped by: who the company is, which brands it trades under, where it operates and which entity invoices.",
    "org.none": "No organization has been created in this tenant yet.",
    "org.country": "Country",
    "org.brands": "Brands",
    "org.noBrands": "No brands yet. A brand is what a site trades under, and a location has to belong to one.",
    "org.locations": "Sites",
    "org.noLocations": "No sites under this brand yet.",
    "org.timezone": "Timezone",
    "org.entities": "Who invoices",
    "org.noEntities": "No legal entity yet. An invoice is numbered per entity, so the first one has to exist before anything can be billed.",
    "org.taxNumber": "Tax number",
    "org.noTaxNumber": "None recorded",
    "org.orphans": "Not reachable from an organization",
    "org.orphansDetail": "These rows name a parent this read did not return. Shown rather than dropped, because a site that vanishes from the only page listing sites is worse than one that looks wrong.",
    "login.title": "Sign in",
    "login.tenant": "Tenant ID",
    "login.identifier": "Email or phone",
    "login.password": "Password",
    "login.submit": "Sign in",
    "login.working": "Signing in…",
    "login.failed": "Those details were not accepted.",
    "login.challenge": "This sign-in needs a recovery code.",
    "login.tooMany": "Too many attempts. Try again shortly.",
    "login.recovery": "Recovery code",
    "login.recoveryHint": "This device has not been seen before, so one recovery code is needed.",
    "login.continue": "Continue",
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
    "nav.back": "Back",
    "access.title": "Doors",
    "access.empty": "No access zones have been declared yet.",
    "access.zone": "Zone",
    "access.risk": "Risk",
    "access.risk.standard": "Standard",
    "access.risk.high_risk": "High risk",
    "access.readers": "Readers",
    "access.policy": "Policy",
    "access.noPolicy": "No live policy — this zone decides nothing",
    "access.policyVersion": "Version",
    "access.offlineCeiling": "Offline authorization lasts at most",
    "access.hours": "hours",
    "access.occupancy": "Inside now",
    "access.confidence.measured": "Both directions are read",
    "access.confidence.advisory": "Advisory only",
    "access.points": "Access points",
    "access.direction.entry": "Entry",
    "access.direction.exit": "Exit",
    "access.direction.both": "Entry and exit",
    "access.decidesNothing": "Records only; never decides",
    "access.gaps": "What this zone cannot do",
    "access.decisions": "Recent decisions",
    "access.noDecisions": "Nothing has been presented at this zone yet.",
    "access.granted": "Admitted",
    "access.refused": "Refused",
    "access.shownToMember": "Shown to the member",
    "access.fullReason": "Full reason",
    "access.reasonWithheld": "Withheld — needs the full-reason permission",
    "access.when": "When",
    "access.terms.opens": "Open",
    "access.terms.entitlement": "Needs an entitlement",
    "access.terms.balance": "Maximum balance",
    "access.terms.age": "Minimum age",
    "access.terms.passback": "One entry every",
    "access.terms.capacity": "Capacity",
    "access.terms.seconds": "seconds",
    "access.terms.years": "years",
    "access.terms.none": "Not restricted",
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
    "nav.label": "الأقسام",
    "nav.overview": "نظرة عامة",
    "nav.organization": "المؤسسة",
    "nav.access": "الأبواب",
    "org.title": "المؤسسة",
    "org.lead": "التسلسل الذي تُنسب إليه كل الشاشات الأخرى: من هي الشركة، وبأي علامات تعمل، وأين، وأي كيان يُصدر الفواتير.",
    "org.none": "لم تُنشأ أي مؤسسة في هذا المستأجر بعد.",
    "org.country": "الدولة",
    "org.brands": "العلامات",
    "org.noBrands": "لا توجد علامات بعد. العلامة هي ما يعمل الموقع تحته، ويجب أن ينتمي كل موقع إلى واحدة.",
    "org.locations": "المواقع",
    "org.noLocations": "لا توجد مواقع تحت هذه العلامة بعد.",
    "org.timezone": "المنطقة الزمنية",
    "org.entities": "من يُصدر الفواتير",
    "org.noEntities": "لا يوجد كيان قانوني بعد. تُرقَّم الفاتورة لكل كيان، لذا يجب وجود الأول قبل أي فاتورة.",
    "org.taxNumber": "الرقم الضريبي",
    "org.noTaxNumber": "غير مُسجَّل",
    "org.orphans": "غير قابل للوصول من مؤسسة",
    "org.orphansDetail": "تشير هذه الصفوف إلى أصل لم تُرجعه هذه القراءة. تُعرض بدلاً من حذفها، لأن اختفاء موقع من الصفحة الوحيدة التي تسرد المواقع أسوأ من ظهوره خاطئاً.",
    "login.title": "تسجيل الدخول",
    "login.tenant": "معرّف المستأجر",
    "login.identifier": "البريد الإلكتروني أو الهاتف",
    "login.password": "كلمة المرور",
    "login.submit": "تسجيل الدخول",
    "login.working": "جارٍ تسجيل الدخول…",
    "login.failed": "لم تُقبل هذه البيانات.",
    "login.challenge": "يحتاج تسجيل الدخول هذا إلى رمز استرداد.",
    "login.tooMany": "محاولات كثيرة جدًا. حاول بعد قليل.",
    "login.recovery": "رمز الاسترداد",
    "login.recoveryHint": "لم يسبق أن شوهد هذا الجهاز، لذا يلزم رمز استرداد واحد.",
    "login.continue": "متابعة",
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
    "nav.back": "رجوع",
    "access.title": "الأبواب",
    "access.empty": "لم تُعرَّف أي مناطق وصول بعد.",
    "access.zone": "المنطقة",
    "access.risk": "المخاطر",
    "access.risk.standard": "عادية",
    "access.risk.high_risk": "عالية المخاطر",
    "access.readers": "القارئات",
    "access.policy": "السياسة",
    "access.noPolicy": "لا توجد سياسة سارية — هذه المنطقة لا تقرّر شيئًا",
    "access.policyVersion": "الإصدار",
    "access.offlineCeiling": "التفويض دون اتصال يدوم على الأكثر",
    "access.hours": "ساعات",
    "access.occupancy": "بالداخل الآن",
    "access.confidence.measured": "يُقرأ الاتجاهان كلاهما",
    "access.confidence.advisory": "استرشادي فقط",
    "access.points": "نقاط الوصول",
    "access.direction.entry": "دخول",
    "access.direction.exit": "خروج",
    "access.direction.both": "دخول وخروج",
    "access.decidesNothing": "تسجيل فقط؛ لا تقرّر أبدًا",
    "access.gaps": "ما لا تستطيع هذه المنطقة فعله",
    "access.decisions": "أحدث القرارات",
    "access.noDecisions": "لم يُقدَّم أي اعتماد في هذه المنطقة بعد.",
    "access.granted": "سُمح بالدخول",
    "access.refused": "رُفض",
    "access.shownToMember": "ما عُرض على العضو",
    "access.fullReason": "السبب الكامل",
    "access.reasonWithheld": "محجوب — يتطلب صلاحية السبب الكامل",
    "access.when": "الوقت",
    "access.terms.opens": "ساعات العمل",
    "access.terms.entitlement": "يتطلب استحقاقًا",
    "access.terms.balance": "أقصى رصيد مستحق",
    "access.terms.age": "الحد الأدنى للعمر",
    "access.terms.passback": "دخول واحد كل",
    "access.terms.capacity": "السعة",
    "access.terms.seconds": "ثانية",
    "access.terms.years": "سنة",
    "access.terms.none": "غير مقيَّد",
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
