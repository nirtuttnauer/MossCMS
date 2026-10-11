import { ApiError, deleteEntryMutation, entryByIdQuery, getContext, gql, message, type Entry } from './api'

export type TrashOutcome = 'pending' | 'done' | 'failed' | 'uncertain' | 'not_attempted'
export type TrashItemResult = { outcome: TrashOutcome; reason?: string; version?: number }
export type TrashResult = { total: number; results: Record<string, TrashItemResult> }

export async function trashEntry(
  entry: Entry,
  reconcileFirst = false,
  context = getContext(),
): Promise<TrashItemResult> {
  if (reconcileFirst) {
    try {
      const { entry: current } = await gql<{ entry: Entry | null }>(entryByIdQuery, { id: entry.id }, context)
      if (!current) {
        return { outcome: 'failed', reason: 'Entry unavailable. Check your workspace access before retrying.' }
      }
      if (current.status === 'deleted') {
        return { outcome: 'done' }
      }
      entry = current
    } catch (reason) {
      return { outcome: 'uncertain', reason: `Cannot confirm current status. ${message(reason)}` }
    }
  }
  try {
    await gql(deleteEntryMutation, { id: entry.id, version: entry.version }, context)
    return { outcome: 'done' }
  } catch (reason) {
    const uncertain = reason instanceof ApiError
      && (reason.uncertain || ['NETWORK', 'TIMEOUT'].includes(reason.code))
    const conflict = reason instanceof ApiError && reason.code === 'CONFLICT'
    if (uncertain || conflict) {
      try {
        const { entry: current } = await gql<{ entry: Entry | null }>(entryByIdQuery, { id: entry.id }, context)
        if (current?.status === 'deleted') {
          return { outcome: 'done' }
        }
        if (current) {
          return { outcome: 'failed', reason: message(reason), version: current.version }
        }
      } catch {
        /* Keep an unconfirmed operation distinct from a confirmed failure. */
      }
    }
    return { outcome: uncertain ? 'uncertain' : 'failed', reason: message(reason), version: entry.version }
  }
}
