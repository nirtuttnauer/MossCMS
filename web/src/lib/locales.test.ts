import { describe, expect, it } from 'vitest'
import { LOCALE_PATTERN } from './locales'
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
