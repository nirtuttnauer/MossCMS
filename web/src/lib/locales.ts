export const LOCALE_PATTERN = /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/

const RTL_LANGUAGES = new Set(['ar', 'he'])

function localeLanguage(locale: string): string {
  return locale.split('-')[0]?.toLowerCase() ?? ''
}

/** Hebrew and Arabic, including an allowed region suffix, read right to left. Other locale keys read left to right. */
export function localeDirection(locale: string): 'ltr' | 'rtl' {
  return RTL_LANGUAGES.has(localeLanguage(locale)) ? 'rtl' : 'ltr'
}

/** Direction and language for a localized value. No locale key keeps the browser's automatic direction. */
export function localeValueProps(locale?: string): { dir: 'ltr' | 'rtl' | 'auto'; lang?: string } {
  if (!locale || !LOCALE_PATTERN.test(locale)) return { dir: locale ? localeDirection(locale) : 'auto' }
  return { dir: localeDirection(locale), lang: locale }
}
