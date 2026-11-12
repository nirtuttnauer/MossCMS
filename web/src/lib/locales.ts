export const LOCALE_PATTERN = /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/

export type LocaleDirection = 'ltr' | 'rtl' | 'auto'

/** ISO 15924 codes of scripts written right to left. */
const RTL_SCRIPTS = new Set([
  'Adlm', 'Arab', 'Aran', 'Armi', 'Avst', 'Chrs', 'Cprt', 'Elym', 'Hatr', 'Hebr', 'Hung', 'Khar', 'Lydi',
  'Mand', 'Mani', 'Mend', 'Merc', 'Mero', 'Narb', 'Nbat', 'Nkoo', 'Orkh', 'Ougr', 'Palm', 'Phli', 'Phlp',
  'Phnx', 'Prti', 'Rohg', 'Samr', 'Sarb', 'Sogd', 'Sogo', 'Syrc', 'Thaa', 'Yezi',
])

/** Script codes that do not name one writing direction: inherited, common, unwritten, unknown, and private use. */
const UNDETERMINED_SCRIPT = /^(Zinh|Zyyy|Zxxx|Zzzz|Qa[a-b][a-z])$/

/** Languages whose default script is written right to left, used when the locale names no script. */
const RTL_LANGUAGES = new Set([
  'ar', 'arc', 'bal', 'bqi', 'ckb', 'dv', 'fa', 'glk', 'haz', 'he', 'iw', 'jrb', 'ji', 'khw', 'ks', 'lad',
  'lrc', 'mzn', 'nqo', 'prs', 'ps', 'rhg', 'sam', 'sd', 'sdh', 'skr', 'syr', 'ug', 'ur', 'yi',
])

function titleCase(subtag: string): string {
  return subtag.charAt(0).toUpperCase() + subtag.slice(1).toLowerCase()
}

function scriptDirection(script: string): LocaleDirection {
  if (RTL_SCRIPTS.has(script)) return 'rtl'
  return UNDETERMINED_SCRIPT.test(script) ? 'auto' : 'ltr'
}

/** The likely script of a locale from CLDR data through `Intl.Locale`, or undefined when the runtime does not know one. */
function likelyScript(locale: string, language: string): string | undefined {
  for (const tag of [locale, language]) {
    try {
      const script = new Intl.Locale(tag).maximize().script
      if (script) return script
    } catch (error) {
      // RangeError for a tag Intl.Locale rejects, such as a malformed region; the bare language is tried next.
      void error
    }
  }
  return undefined
}

/**
 * Writing direction for a locale key. An explicit script subtag decides first (`he-Latn` is ltr, `ms-Arab`
 * is rtl). Without one, a language whose default script is right to left is rtl, and other languages take
 * the direction of their CLDR likely script (`pa-PK` is rtl, `fr` is ltr). A locale whose script cannot be
 * determined is `auto`, so the browser chooses from the text.
 */
export function localeDirection(locale: string): LocaleDirection {
  const [language = '', ...rest] = locale.toLowerCase().split(/[-_]/)
  const script = rest.find(subtag => /^[a-z]{4}$/.test(subtag))
  if (script) return scriptDirection(titleCase(script))
  if (RTL_LANGUAGES.has(language)) return 'rtl'
  const likely = likelyScript(locale, language)
  return likely ? scriptDirection(likely) : 'auto'
}

/** Direction and language for a localized value. No locale key keeps the browser's automatic direction. */
export function localeValueProps(locale?: string): { dir: LocaleDirection; lang?: string } {
  if (!locale || !LOCALE_PATTERN.test(locale)) return { dir: locale ? localeDirection(locale) : 'auto' }
  return { dir: localeDirection(locale), lang: locale }
}
