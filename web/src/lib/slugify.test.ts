import { describe, expect, it } from 'vitest'
import vectors from '../../../shared/slug-vectors.json'
import {
  SLUG_MAX_BYTES,
  SLUG_MAX_CHARS,
  STRIP_RANGES,
  allowsScripts,
  canonicalSlug,
  encodeWebsitePath,
  slugify,
} from './slugify'

describe('shared slug vectors', () => {
  it('uses the same limits and strip ranges as the server', () => {
    expect(vectors.limits).toEqual({ characters: SLUG_MAX_CHARS, utf8Bytes: SLUG_MAX_BYTES })
    expect(vectors.stripRanges.map(([start, end]) => [Number.parseInt(start, 16), Number.parseInt(end, 16)])).toEqual(STRIP_RANGES)
  })

  it.each(vectors.cases)('$id', (item) => {
    if (item.slug !== undefined) {
      expect(slugify(item.input)).toBe(item.slug)
      expect(canonicalSlug(item.input)).toBe(item.slug)
    } else {
      expect(item.error).toBe('invalid_slug')
      expect(() => slugify(item.input)).toThrow('invalid_slug')
    }
    if (item.encoded) expect(encodeURIComponent(item.slug ?? '')).toBe(item.encoded)
    if (item.websitePath) {
      const slug = item.websitePath.startsWith('/blog/') ? `blog/${item.slug}` : item.slug
      expect(encodeWebsitePath(`/${slug}`)).toBe(item.websitePath)
    }
  })

  it('strips every character in each bidi and zero-width range', () => {
    for (const [start, end] of STRIP_RANGES) {
      for (let code = start; code <= end; code++) {
        expect(slugify(`ab${String.fromCodePoint(code)}cd`)).toBe('abcd')
      }
    }
  })

  it('rejects a second non-Latin script and still accepts Hebrew with Latin', () => {
    expect(allowsScripts(new Set(['Hebrew', 'Arabic']))).toBe(false)
    expect(allowsScripts(new Set(['Latin', 'Hebrew']))).toBe(true)
    expect(allowsScripts(new Set(['Latin', 'Cyrillic']))).toBe(false)
    expect(allowsScripts(new Set(['Latin', 'Greek']))).toBe(false)
    expect(allowsScripts(new Set(['Cyrillic']))).toBe(true)
    expect(slugify('nextjs-מדריך')).toBe('nextjs-מדריך')
    expect(() => slugify('שלוםمرحبا')).toThrow('invalid_slug')
  })

  it('measures 600 UTF-8 bytes on the raw slug, before percent-encoding', () => {
    const exact = '一'.repeat(200)
    expect(new TextEncoder().encode(exact).length).toBe(600)
    expect(encodeURIComponent(exact).length).toBeGreaterThan(600)
    expect(slugify(exact)).toBe(exact)
    const over = `${exact}a`
    expect(new TextEncoder().encode(over).length).toBe(601)
    expect([...over].length).toBeLessThanOrEqual(220)
    expect(() => slugify(over)).toThrow('invalid_slug')
    expect(slugify('a'.repeat(220))).toBe('a'.repeat(220))
    expect(() => slugify('a'.repeat(221))).toThrow('invalid_slug')
  })
})
