// Visual editing for the Markdown subset MossCMS already renders.
// Unsupported source returns null and must be left byte-for-byte unchanged.

const INFO = /^[A-Za-z0-9_-]+$/
const ASSET = /^[A-Za-z0-9_-]+$/
const HREF = /^(https?:\/\/|mailto:)[^\s<>]+$/

function parseInlines(text) {
  if (text.includes('<') || text.includes('>') || text.includes('\\')) return null
  const inlines = []
  let index = 0
  let buffer = ''
  const flush = () => {
    if (buffer) inlines.push({ type: 'text', text: buffer })
    buffer = ''
  }
  while (index < text.length) {
    if (text.startsWith('**', index)) {
      const end = text.indexOf('**', index + 2)
      const inner = end === -1 ? '' : text.slice(index + 2, end)
      if (end !== -1 && inner && !/[*`[\]]/.test(inner) && !inner.includes('\n')) {
        flush()
        inlines.push({ type: 'strong', text: inner })
        index = end + 2
        continue
      }
    }
    if (text[index] === '*' && !text.startsWith('**', index)) {
      const end = text.indexOf('*', index + 1)
      const inner = end === -1 ? '' : text.slice(index + 1, end)
      if (end !== -1 && inner && !/[*`[\]]/.test(inner) && !inner.includes('\n')) {
        flush()
        inlines.push({ type: 'em', text: inner })
        index = end + 1
        continue
      }
    }
    if (text[index] === '`') {
      const end = text.indexOf('`', index + 1)
      const inner = end === -1 ? '' : text.slice(index + 1, end)
      if (end !== -1 && inner && !inner.includes('`') && !inner.includes('\n')) {
        flush()
        inlines.push({ type: 'code', text: inner })
        index = end + 1
        continue
      }
    }
    if (text.startsWith('![', index)) {
      const image = readImage(text, index)
      if (!image) return null
      flush()
      inlines.push(image.node)
      index = image.next
      continue
    }
    if (text[index] === '[') {
      const link = readLink(text, index)
      if (!link) return null
      flush()
      inlines.push(link.node)
      index = link.next
      continue
    }
    buffer += text[index]
    index += 1
  }
  flush()
  return inlines
}

function readImage(text, index) {
  if (!text.startsWith('![', index)) return null
  const altEnd = text.indexOf('](asset:', index + 2)
  if (altEnd === -1) return null
  const alt = text.slice(index + 2, altEnd)
  if (!alt || /[\[\]]/.test(alt)) return null
  const idEnd = text.indexOf(')', altEnd + 8)
  if (idEnd === -1) return null
  const assetId = text.slice(altEnd + 8, idEnd)
  if (!ASSET.test(assetId)) return null
  return { node: { type: 'image', alt, assetId }, next: idEnd + 1 }
}

function readLink(text, index) {
  const labelEnd = text.indexOf('](', index + 1)
  if (labelEnd === -1) return null
  const label = text.slice(index + 1, labelEnd)
  if (!label || /[\[\]]/.test(label)) return null
  const hrefEnd = text.indexOf(')', labelEnd + 2)
  if (hrefEnd === -1) return null
  const href = text.slice(labelEnd + 2, hrefEnd)
  if (!HREF.test(href)) return null
  return { node: { type: 'link', text: label, href }, next: hrefEnd + 1 }
}

function structural(line) {
  return line.startsWith('```') || line.startsWith('#') || line.startsWith('- ') || line.startsWith('>') || line.startsWith(':::') || /^\d+\. /.test(line) || /^!\[[^\]]*\]\(asset:[A-Za-z0-9_-]+\)$/.test(line)
}

export function parseRichText(source) {
  if (typeof source !== 'string' || source.includes('\r') || source.includes('\0')) return null
  if (source === '') return { blocks: [] }
  const lines = source.endsWith('\n') ? source.slice(0, -1).split('\n') : source.split('\n')
  const blocks = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (line === '') {
      index += 1
      continue
    }
    if (line.startsWith('    ') || line.startsWith('\t') || line.startsWith('>') || line.startsWith(':::') || line.startsWith('####')) return null
    if (line.startsWith('```')) {
      const info = line.slice(3).trim()
      if (info && !INFO.test(info)) return null
      const body = []
      index += 1
      let closed = false
      while (index < lines.length) {
        if (lines[index] === '```') {
          closed = true
          index += 1
          break
        }
        body.push(lines[index])
        index += 1
      }
      if (!closed) return null
      blocks.push({ type: 'code', info, text: body.join('\n') })
      continue
    }
    const heading = /^(#{1,3}) (.*)$/.exec(line)
    if (heading) {
      const inlines = parseInlines(heading[2])
      if (!inlines) return null
      blocks.push({ type: 'heading', level: heading[1].length, inlines })
      index += 1
      continue
    }
    if (line.startsWith('- ')) {
      const items = []
      while (index < lines.length && lines[index].startsWith('- ')) {
        const inlines = parseInlines(lines[index].slice(2))
        if (!inlines) return null
        items.push(inlines)
        index += 1
      }
      blocks.push({ type: 'bullet', items })
      continue
    }
    if (/^\d+\. /.test(line)) {
      const items = []
      let number = 1
      while (index < lines.length && lines[index].startsWith(`${number}. `)) {
        const inlines = parseInlines(lines[index].slice(`${number}. `.length))
        if (!inlines) return null
        items.push(inlines)
        index += 1
        number += 1
      }
      if (index < lines.length && /^\d+\. /.test(lines[index])) return null
      blocks.push({ type: 'ordered', items })
      continue
    }
    if (/^!\[[^\]]*\]\(asset:[A-Za-z0-9_-]+\)$/.test(line)) {
      const image = readImage(line, 0)
      if (!image || image.next !== line.length) return null
      blocks.push({ type: 'image', alt: image.node.alt, assetId: image.node.assetId })
      index += 1
      continue
    }
    const paragraph = []
    while (index < lines.length && lines[index] !== '' && !structural(lines[index])) {
      paragraph.push(lines[index])
      index += 1
    }
    if (!paragraph.length) return null
    const inlines = parseInlines(paragraph.join('\n'))
    if (!inlines) return null
    blocks.push({ type: 'paragraph', inlines })
  }
  return { blocks }
}

function serializeInlines(inlines) {
  return inlines.map(node => {
    if (node.type === 'text') return node.text
    if (node.type === 'strong') return `**${node.text}**`
    if (node.type === 'em') return `*${node.text}*`
    if (node.type === 'code') return `\`${node.text}\``
    if (node.type === 'link') return `[${node.text}](${node.href})`
    if (node.type === 'image') return `![${node.alt}](asset:${node.assetId})`
    return ''
  }).join('')
}

export function serializeRichText(document) {
  if (!document.blocks.length) return ''
  const body = document.blocks.map(block => {
    if (block.type === 'heading') return `${'#'.repeat(block.level)} ${serializeInlines(block.inlines)}`
    if (block.type === 'paragraph') return serializeInlines(block.inlines)
    if (block.type === 'bullet') return block.items.map(item => `- ${serializeInlines(item)}`).join('\n')
    if (block.type === 'ordered') return block.items.map((item, index) => `${index + 1}. ${serializeInlines(item)}`).join('\n')
    if (block.type === 'code') return `\`\`\`${block.info || ''}\n${block.text}\n\`\`\``
    if (block.type === 'image') return `![${block.alt}](asset:${block.assetId})`
    return ''
  }).join('\n\n')
  return `${body}\n`
}

function plainText(inlines) {
  return inlines.map(node => node.text || node.alt || '').join('')
}

function wrap(inlines, type) {
  const text = plainText(inlines)
  if (!text) return [{ type, text: 'text', ...(type === 'link' ? { href: 'https://example.com' } : {}) }]
  const already = inlines.length === 1 && inlines[0].type === type
  if (already) return [{ type: 'text', text }]
  if (type === 'link') return [{ type: 'link', text, href: 'https://example.com' }]
  return [{ type, text }]
}

export function formatRichText(source, action, payload = {}) {
  const document = parseRichText(source)
  if (!document) return null
  if (!document.blocks.length) document.blocks.push({ type: 'paragraph', inlines: [{ type: 'text', text: '' }] })
  const block = document.blocks[0]
  if (action === 'heading') {
    const inlines = block.type === 'paragraph' || block.type === 'heading' ? block.inlines : [{ type: 'text', text: plainText(block.inlines || []) || 'text' }]
    document.blocks[0] = { type: 'heading', level: 2, inlines: inlines.length ? inlines : [{ type: 'text', text: 'text' }] }
  } else if (action === 'bold' || action === 'italic' || action === 'link') {
    const kind = action === 'bold' ? 'strong' : action === 'italic' ? 'em' : 'link'
    if (block.type === 'paragraph' || block.type === 'heading') block.inlines = wrap(block.inlines, kind)
    else return null
  } else if (action === 'bullet' || action === 'ordered') {
    const items = block.type === 'paragraph' || block.type === 'heading' ? [block.inlines] : block.items || [[{ type: 'text', text: 'text' }]]
    document.blocks[0] = { type: action === 'bullet' ? 'bullet' : 'ordered', items }
  } else if (action === 'code') {
    const text = block.type === 'code' ? block.text : plainText(block.inlines || block.items?.flat() || []) || 'text'
    document.blocks[0] = { type: 'code', info: '', text }
  } else if (action === 'image') {
    const alt = String(payload.alt || '').replace(/[\[\]\\]/g, '').trim()
    if (!alt || !ASSET.test(payload.assetId || '')) return null
    document.blocks.push({ type: 'image', alt, assetId: payload.assetId })
  } else return null
  const next = serializeRichText(document)
  return parseRichText(next) ? next : null
}
