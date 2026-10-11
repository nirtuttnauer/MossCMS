export async function readBody(request, maxBytes) {
  const parts = [];
  let size = 0;
  for await (const chunk of request) {
    size += Buffer.byteLength(chunk);
    if (size > maxBytes) throw new Error('Too large');
    parts.push(Buffer.from(chunk));
  }
  return Buffer.concat(parts);
}
