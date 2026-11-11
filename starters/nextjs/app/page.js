import { connection } from 'next/server';
import { entryTitle, loadPublishedEntries } from '../lib/entries';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function formatPublishedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date);
}

function loadErrorMessage(error) {
  if (error?.code === 'MISSING_TOKEN') return 'Set MOSS_DELIVERY_TOKEN in the server environment.';
  if (error instanceof TypeError) return 'MossCMS could not be reached.';
  if (error instanceof Error && error.message) return error.message;
  return 'Published entries could not be loaded.';
}

export default async function HomePage() {
  await connection();
  try {
    const entries = await loadPublishedEntries();
    return (
      <main>
        <h1>Published entries</h1>
        {entries.length === 0 ? (
          <p className="status">No published entries.</p>
        ) : (
          <ul className="entries">
            {entries.map((entry) => (
              <li key={entry.id}>
                <article data-entry-id={entry.id}>
                  <h2>{entryTitle(entry)}</h2>
                  <p>
                    <span>{entry.typeKey}</span>
                    <span>{entry.slug}</span>
                    {entry.publishedAt ? (
                      <time dateTime={entry.publishedAt}>{formatPublishedAt(entry.publishedAt)}</time>
                    ) : null}
                  </p>
                </article>
              </li>
            ))}
          </ul>
        )}
      </main>
    );
  } catch (error) {
    return (
      <main>
        <h1>Published entries</h1>
        <p className="status" role="alert">
          {loadErrorMessage(error)}
        </p>
      </main>
    );
  }
}
