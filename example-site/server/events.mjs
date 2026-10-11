import { createHmac, timingSafeEqual } from 'node:crypto';
import { invalidateWebsite } from './cache.mjs';
import { readBody } from './request-body.mjs';

const clients = new Set();
const seen = new Map();
const MAX_CLIENTS = 100;
const MAX_EVENT_BYTES = 8192;
const MAX_SEEN_EVENTS = 10000;
const EVENT_TTL_MS = 600000;
const HEARTBEAT_MS = 15000;
const SIGNATURE_MAX_AGE_SECONDS = 300;
let generation = 0;

export function verifyEvent(body, headers, environment) {
  const secret = environment.MOSS_WEBHOOK_SECRET;
  const workspace = environment.SITE_MOSS_WORKSPACE_ID;
  const timestamp = headers['x-moss-timestamp'];
  const signature = headers['x-moss-signature'];
  if (
    !secret || !workspace ||
    !/^\d{10}$/.test(timestamp || '') ||
    Math.abs(Date.now() / 1000 - Number(timestamp)) > SIGNATURE_MAX_AGE_SECONDS ||
    !/^sha256=[a-f0-9]{64}$/.test(signature || '')
  ) return null;

  const expected = createHmac('sha256', secret).update(timestamp + '.').update(body).digest('hex');
  if (!timingSafeEqual(Buffer.from(expected), Buffer.from(signature.slice(7)))) return null;
  try {
    const event = JSON.parse(body);
    return (
      event.workspaceId === workspace &&
      event.id === headers['x-moss-event-id'] &&
      typeof event.id === 'string' && event.id.length <= 100 &&
      ['published', 'unpublished', 'trashed'].includes(event.event)
    ) ? event : null;
  } catch {
    return null;
  }
}

export function eventMiddleware(environment) {
  return async (request, response, next) => {
    const path = request.url?.split('?')[0];
    if (path === '/api/events') {
      if (request.method !== 'GET') {
        response.writeHead(405);
        response.end();
        return;
      }
      if (clients.size >= MAX_CLIENTS) {
        response.writeHead(429);
        response.end();
        return;
      }
      response.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-store',
        'X-Accel-Buffering': 'no',
      });
      response.write(`data: ${generation}\n\n`);
      clients.add(response);
      const heartbeat = setInterval(() => response.write(': keepalive\n\n'), HEARTBEAT_MS);
      response.on('close', () => {
        clearInterval(heartbeat);
        clients.delete(response);
      });
      return;
    }
    if (path !== '/api/moss-events') return next();
    response.setHeader('Cache-Control', 'no-store');
    if (request.method !== 'POST') {
      response.writeHead(405);
      response.end();
      return;
    }
    try {
      const event = verifyEvent(await readBody(request, MAX_EVENT_BYTES), request.headers, environment);
      if (!event) {
        response.writeHead(403);
        response.end();
        return;
      }
      const now = Date.now();
      for (const [id, expires] of seen) {
        if (expires < now) seen.delete(id);
      }
      if (!seen.has(event.id)) {
        if (seen.size >= MAX_SEEN_EVENTS) seen.delete(seen.keys().next().value);
        seen.set(event.id, now + EVENT_TTL_MS);
        invalidateWebsite();
        generation++;
        for (const client of clients) client.write(`data: ${generation}\n\n`);
      }
      response.writeHead(204);
      response.end();
    } catch {
      response.writeHead(400);
      response.end();
    }
  };
}
