const CAPABILITIES: Record<string, string[]> = {
  reader: ['read'],
  author: ['read', 'create', 'edit', 'media'],
  editor: ['read', 'create', 'edit', 'publish', 'schedule', 'review', 'media'],
  publisher: ['read', 'create', 'edit', 'publish', 'schedule', 'review', 'media'],
  admin: ['read', 'create', 'edit', 'publish', 'schedule', 'review', 'media', 'schema', 'team'],
}

export function can(role: string, capability: string) {
  return (CAPABILITIES[role] || []).includes(capability)
}
