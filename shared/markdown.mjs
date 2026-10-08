// Both frontends use this URL policy. Raw HTML is disabled by the renderers.
export function markdownUrl(assets = []) {
  return (raw, key) => {
    if (key === 'src' && raw.startsWith('asset:')) {
      raw = assets.find(asset => asset.id === raw.slice(6) && ['image/jpeg','image/png','image/webp'].includes(asset.mime))?.url || '';
    }
    if (!raw || /[\u0000-\u0020\u007f]/.test(raw)) return '';
    try {
      const url = new URL(raw, 'https://markdown.invalid');
      return (key === 'src' ? ['https:', 'http:'] : ['https:', 'http:', 'mailto:']).includes(url.protocol) ? raw : '';
    } catch { return '' }
  };
}
