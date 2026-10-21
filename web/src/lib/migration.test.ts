import { expect, test } from 'vitest'
import { buildPipeline } from './migration'

test('pipeline serialization retains operation order, optional type, and typed defaults', () => {
  expect(buildPipeline([{ op: 'default', path: ' enabled ', typeKey: ' article ', argument: 'false' }, { op: 'convert', path: 'count', typeKey: '', argument: 'number' }], '{}')).toEqual({ schemas: {}, steps: [{ op: 'default', path: 'enabled', typeKey: 'article', value: false }, { op: 'convert', path: 'count', to: 'number' }] })
  expect(() => buildPipeline([{ op: 'default', path: 'title', typeKey: '', argument: 'unquoted' }], '{}')).toThrow('Step 1: default value must be JSON')
})
