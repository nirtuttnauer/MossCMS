export type Inline =
  | { type: 'text'; text: string }
  | { type: 'strong'; text: string }
  | { type: 'em'; text: string }
  | { type: 'code'; text: string }
  | { type: 'link'; text: string; href: string }
  | { type: 'image'; alt: string; assetId: string }

export type Block =
  | { type: 'heading'; level: number; inlines: Inline[] }
  | { type: 'paragraph'; inlines: Inline[] }
  | { type: 'bullet'; items: Inline[][] }
  | { type: 'ordered'; items: Inline[][] }
  | { type: 'code'; info: string; text: string }
  | { type: 'image'; alt: string; assetId: string }

export type RichText = { blocks: Block[] }

export function parseRichText(source: string): RichText | null
export function serializeRichText(document: RichText): string
export function formatRichText(source: string, action: string, payload?: { alt?: string; assetId?: string }): string | null
