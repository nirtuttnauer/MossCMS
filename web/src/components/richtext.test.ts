import { expect, test } from 'vitest'
import { formatRichText, parseRichText, serializeRichText } from '../../../shared/richtext.mjs'

const corpus = [
  'Hello **world** and *emphasis*.\n',
  '## A heading\n\nA paragraph with a [link](https://example.com) and `code`.\n',
  '- One\n- Two\n\n1. First\n2. Second\n',
  '```\nconst value = 1\n```\n\n![Cover](asset:image)\n',
  'Line one\nLine two\n',
  'Hello world!\n',
]

test.each(corpus)('supported markdown round-trips %#', source => {
  const parsed = parseRichText(source)
  expect(parsed).not.toBeNull()
  expect(serializeRichText(parsed!)).toBe(source)
  expect(serializeRichText(parseRichText(serializeRichText(parsed!))!)).toBe(source)
})

test('formatting commands preserve the supported structure', () => {
  expect(formatRichText('Hello', 'bold')).toBe('**Hello**\n')
  expect(formatRichText('Hello', 'heading')).toBe('## Hello\n')
  expect(formatRichText('Hello', 'bullet')).toBe('- Hello\n')
  expect(formatRichText('Hello', 'image', { alt: '[A]\\B]', assetId: 'image' })).toBe('Hello\n\n![AB](asset:image)\n')
})

test.each([
  '<div>html</div>',
  '> a blockquote',
  '#### too deep',
  ':::warning\nraw directive\n',
  '```\nunclosed',
])('unsupported markdown is not representable: %s', source => {
  expect(parseRichText(source)).toBeNull()
  expect(formatRichText(source, 'bold')).toBeNull()
})
