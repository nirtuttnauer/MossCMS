import casefoldTable from '../../../shared/casefold.json'
import scriptTable from '../../../shared/unicode-scripts.json'

/** Character length stays the column width. Bytes are NFC UTF-8 before percent-encoding. */
export const SLUG_MAX_CHARS = 220
export const SLUG_MAX_BYTES = 600
/** U+200B–U+200F, U+202A–U+202E, U+2066–U+2069, and U+FEFF. Stripped before NFC. */
export const STRIP_RANGES: ReadonlyArray<readonly [number, number]> = [
  [0x200b, 0x200f],
  [0x202a, 0x202e],
  [0x2066, 0x2069],
  [0xfeff, 0xfeff],
]

const STRIP = new Set<number>(STRIP_RANGES.flatMap(([start, end]) => {
  const codes: number[] = []
  for (let code = start; code <= end; code++) codes.push(code)
  return codes
}))
const FOLDS = casefoldTable.folds as Record<string, string>
const RANGES = scriptTable.ranges as [number, number, string][]
const KEPT = /^(?:\p{L}|\p{M}|\p{N})$/u

export function scriptOf(character: string): string | null {
  const code = character.codePointAt(0) ?? 0
  let low = 0
  let high = RANGES.length
  while (low < high) {
    const mid = (low + high) >> 1
    const [start, end, name] = RANGES[mid]
    if (code < start) high = mid
    else if (code > end) low = mid + 1
    else return name
  }
  return null
}

export function scriptsOf(slug: string): Set<string> {
  const found = new Set<string>()
  for (const character of slug) {
    if (character === '-') continue
    const script = scriptOf(character)
    if (script) found.add(script)
  }
  return found
}

/** Latin plus at most one other script. Latin with Cyrillic or Greek is rejected. */
export function allowsScripts(scripts: Set<string>): boolean {
  const others = [...scripts].filter(script => script !== 'Latin')
  if (others.length > 1) return false
  if (scripts.has('Latin') && others.some(script => script === 'Cyrillic' || script === 'Greek')) return false
  return true
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).length
}

function codePointLength(value: string): number {
  let count = 0
  for (const _character of value) count += 1
  return count
}

function casefold(value: string): string {
  let folded = ''
  for (const character of value) {
    folded += FOLDS[character.codePointAt(0)!.toString(16)] ?? character
  }
  return folded
}

function decodeOnce(value: string): string | null {
  if (/%25/i.test(value) || /%(?![0-9A-Fa-f]{2})/.test(value)) return null
  if (!value.includes('%')) return value
  try {
    return decodeURIComponent(value)
  } catch {
    return null
  }
}

function normalize(value: string): string | null {
  const decoded = decodeOnce(value)
  if (decoded === null) return null
  let stripped = ''
  for (const character of decoded) {
    if (!STRIP.has(character.codePointAt(0)!)) stripped += character
  }
  const folded = casefold(stripped.normalize('NFC'))
  let mapped = ''
  for (const character of folded) mapped += KEPT.test(character) ? character : '-'
  return mapped.replace(/-+/g, '-').replace(/^-|-$/g, '')
}

/** Normalize without applying the length or script limits. */
export function canonicalSlug(value: string): string {
  return normalize(value) ?? ''
}

export function slugify(value: string): string {
  const slug = normalize(value)
  if (
    slug === null
    || !slug
    || codePointLength(slug) > SLUG_MAX_CHARS
    || utf8Bytes(slug) > SLUG_MAX_BYTES
    || !allowsScripts(scriptsOf(slug))
  ) {
    throw new Error('invalid_slug')
  }
  return slug
}

/** RFC 3986 percent-encoding with uppercase hex, the same case as MOSS-031. */
export function encodeWebsitePath(path: string): string {
  if (!path) return path
  return path.split('/').map(segment => encodeURIComponent(segment)).join('/')
}
