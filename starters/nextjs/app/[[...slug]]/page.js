import { connection } from 'next/server';
import { notFound, permanentRedirect } from 'next/navigation';
import { loadWebsite } from '../../lib/entries.mjs';
import { liveResponse, requestPath } from '../../lib/live.mjs';
import { EntryIndex, LivePage, LoadError } from '../../lib/view.mjs';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export default async function Page({ params }) {
  await connection();
  const { slug } = await params;
  const path = requestPath(slug);
  let website;
  try {
    website = await loadWebsite();
  } catch (error) {
    return <LoadError error={error} />;
  }
  const decision = liveResponse(website.pages, path, website.redirects, website.reservedPaths);
  if (decision.kind === 'index') return <EntryIndex pages={website.pages} />;
  if (decision.kind === 'missing') notFound();
  if (decision.kind === 'redirect') permanentRedirect(decision.location);
  return <LivePage page={decision.page} pages={website.pages} />;
}
