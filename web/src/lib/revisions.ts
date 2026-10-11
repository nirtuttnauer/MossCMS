import type { Entry, Field } from './api'

type DiffItem = {
  key: string
  label: string
  type: string
  leftVal: unknown
  rightVal: unknown
  status: 'added' | 'removed' | 'changed' | 'unchanged'
  isRemovedField?: boolean
}

export function revisionValueIds(diffs: DiffItem[], type: 'asset' | 'reference'): string {
  return [...new Set(diffs
    .filter(diff => diff.type === type)
    .flatMap(diff => [diff.leftVal, diff.rightVal])
    .filter((value): value is string => typeof value === 'string' && Boolean(value)))].join(',')
}

function valuesEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a === null || a === undefined) return b === null || b === undefined
  if (b === null || b === undefined) return false
  return JSON.stringify(a) === JSON.stringify(b)
}

export function buildRevisionDiffs(
  fields: Field[],
  left: Pick<Entry, 'slug' | 'title' | 'data'>,
  right: Pick<Entry, 'slug' | 'title' | 'data'>,
): DiffItem[] {
  const { slug: leftSlug, title: leftTitle, data: leftData } = left
  const { slug: rightSlug, title: rightTitle, data: rightData } = right

  // Calculate field differences
  const diffs: DiffItem[] = []

  // 1. Slug diff
  diffs.push({
    key: '_slug',
    label: 'Slug',
    type: 'slug',
    leftVal: leftSlug,
    rightVal: rightSlug,
    status: valuesEqual(leftSlug, rightSlug) ? 'unchanged' : !leftSlug ? 'added' : !rightSlug ? 'removed' : 'changed',
  })

  // 2. Title diff
  diffs.push({
    key: '_title',
    label: 'Title',
    type: 'text',
    leftVal: leftTitle,
    rightVal: rightTitle,
    status: valuesEqual(leftTitle, rightTitle) ? 'unchanged' : !leftTitle ? 'added' : !rightTitle ? 'removed' : 'changed',
  })

  // Flatten nested values into labeled rows; array indexes make reordering visible.
  function addField(field: Field, left: unknown, right: unknown, path: string, label: string) {
    if (field.localized) {
      const a = left && typeof left === 'object' ? left as Record<string, unknown> : {}
      const b = right && typeof right === 'object' ? right as Record<string, unknown> : {}
      const locales = new Set([...Object.keys(a), ...Object.keys(b)])
      if (locales.size) { for (const locale of locales) addField({ ...field, localized: false }, a[locale], b[locale], `${path}.${locale}`, `${label} (${locale})`); return }
    }
    if (field.type === 'object' && (left && typeof left === 'object' || right && typeof right === 'object')) {
      const a = (left || {}) as Record<string, unknown>, b = (right || {}) as Record<string, unknown>
      const names = new Set([...(field.fields || []).map(child => child.name), ...Object.keys(a), ...Object.keys(b)])
      if (names.size) {
        const start = diffs.length
        for (const name of names) {
          const child = field.fields?.find(child => child.name === name)
          addField(child || { name, type: 'unknown' }, a[name], b[name], `${path}.${name}`, `${label} › ${child?.label || name}${child ? '' : ' (removed schema field)'}`)
        }
        // Empty objects need a presence row when their children cannot show the change.
        if ((left == null) !== (right == null) && diffs.slice(start).every(row => row.status === 'unchanged')) {
          diffs.splice(start, 0, { key: `${path}._presence`, label: `${label} presence`, type: 'text', leftVal: left == null ? undefined : 'Object present', rightVal: right == null ? undefined : 'Object present', status: left == null ? 'added' : 'removed' })
        }
        return
      }
    }
    if (field.type === 'list' && (Array.isArray(left) || Array.isArray(right))) {
      const a = Array.isArray(left) ? left : [], b = Array.isArray(right) ? right : []
      if (a.length || b.length) {
        for (let i = 0; i < Math.max(a.length, b.length); i++) addField(field.item || { name: '', type: 'text' }, a[i], b[i], `${path}[${i}]`, `${label} › Item ${i + 1}`)
        return
      }
    }
    diffs.push({ key: path, label, type: field.type, leftVal: left, rightVal: right,
      status: valuesEqual(left, right) ? 'unchanged' : left === undefined || left === null ? 'added' : right === undefined || right === null ? 'removed' : 'changed' })
  }
  for (const field of fields) addField(field, leftData[field.name], rightData[field.name], field.name, field.label || field.name)
  const schemaFieldNames = new Set(fields.map(field => field.name))
  for (const name of new Set([...Object.keys(leftData), ...Object.keys(rightData)])) {
    if (!schemaFieldNames.has(name)) addField({ name, type: 'unknown' }, leftData[name], rightData[name], name, `${name} (removed schema field)`)
  }

  return diffs
}
