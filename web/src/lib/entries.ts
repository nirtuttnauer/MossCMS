import type { Entry } from './api'

export type EntryPage = { nodes: Entry[]; total: number; endCursor: string | null; hasNextPage: boolean }

export type DuplicationSource = {
  id: string
  title: string
  version: number
  typeKey: string
  slug: string
  data: Record<string, unknown>
}

export const typeOrder = ['siteProject', 'sitePost', 'sitePage', 'siteSlide', 'siteProfile']
export const creationLabels: Record<string, string> = { siteProject: 'New project', sitePost: 'New blog post', sitePage: 'New page', siteSlide: 'New slide' }
export const timestamp = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
