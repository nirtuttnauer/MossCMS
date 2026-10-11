const caches = new Map();
const pending = new Map();
const CACHE_TTL_MS = 5000;
const STALE_TTL_MS = 600000;
const MAX_CACHE_ENTRIES = 10;
let epoch = 0;

export function invalidateWebsite() {
  epoch++;
  pending.clear();
  for (const cache of caches.values()) cache.expires = 0;
}

export async function cachedWebsite(key, load) {
  const cached = caches.get(key);
  if (cached && cached.expires > Date.now()) return structuredClone(cached.value);
  if (pending.has(key)) return structuredClone(await pending.get(key));

  const generation = epoch;
  const promise = load()
    .then(value => {
      // An invalidation must prevent an older in-flight load from refilling the cache.
      if (generation === epoch) {
        if (caches.size >= MAX_CACHE_ENTRIES && !caches.has(key)) {
          caches.delete(caches.keys().next().value);
        }
        caches.set(key, { value, expires: Date.now() + CACHE_TTL_MS, saved: Date.now() });
      }
      return value;
    })
    .catch(error => {
      if (cached && cached.saved > Date.now() - STALE_TTL_MS) {
        return { ...structuredClone(cached.value), stale: true };
      }
      throw error;
    })
    .finally(() => {
      // An older load must not remove the replacement started after invalidation.
      if (pending.get(key) === promise) pending.delete(key);
    });

  pending.set(key, promise);
  return structuredClone(await promise);
}
