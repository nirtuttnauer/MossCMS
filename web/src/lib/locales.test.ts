import { describe, expect, it } from 'vitest'
import { LOCALE_PATTERN, localeDirection, localeValueProps } from './locales'
import { validateEntry } from './validation'

describe('locale codes', () => {
  it.each(['en', 'eng', 'he', 'fr-CA', 'en-12', 'eng-Ab12CD34'])('accepts %j repeatedly', locale => {
    expect(LOCALE_PATTERN.test(locale)).toBe(true)
    expect(LOCALE_PATTERN.test(locale)).toBe(true)
  })

  it.each(['', ' ', ' en', 'en ', 'en\t', 'e', 'engl', 'EN', 'En', 'en-A', 'en-ABCDEFGHI', 'en--US', 'en-US-CA', 'en_US', 'en-A!'])('rejects %j', locale => {
    expect(LOCALE_PATTERN.test(locale)).toBe(false)
  })

  it('validates raw locale keys before checking required translations', () => {
    const fields = [{ name: 'title', type: 'text', localized: true, required: true }]
    expect(validateEntry(fields, { title: { ' fr-CA ': null } }, 'post')).toEqual({
      'data.title': 'title needs at least one valid locale.',
    })
    expect(validateEntry(fields, { title: { 'fr-CA': null } }, 'post')).toEqual({
      'data.title.fr-CA': 'title (fr-CA) is required.',
    })
  })
})

describe('locale value direction', () => {
  it.each(['he', 'ar', 'he-IL', 'ar-EG', 'ar-SA', 'he-Latn'])('locks %s to rtl with that lang', locale => {
    expect(LOCALE_PATTERN.test(locale)).toBe(true)
    expect(localeDirection(locale)).toBe('rtl')
    expect(localeValueProps(locale)).toEqual({ dir: 'rtl', lang: locale })
  })

  it.each(['en', 'eng', 'fr', 'fr-CA', 'pt-BR', 'en-12', 'de-DE', 'en-he', 'arc', 'heb'])('locks %s to ltr with that lang', locale => {
    expect(LOCALE_PATTERN.test(locale)).toBe(true)
    expect(localeDirection(locale)).toBe('ltr')
    expect(localeValueProps(locale)).toEqual({ dir: 'ltr', lang: locale })
  })

  it('keeps automatic direction when a value has no locale key', () => {
    expect(localeValueProps()).toEqual({ dir: 'auto' })
    expect(localeValueProps('')).toEqual({ dir: 'auto' })
  })

  it('still chooses a direction for a key the locale pattern rejects, without a lang', () => {
    expect(localeValueProps('he-ABCDEFGHI')).toEqual({ dir: 'rtl' })
    expect(localeValueProps('EN')).toEqual({ dir: 'ltr' })
  })
})
