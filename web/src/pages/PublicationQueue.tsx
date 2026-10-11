import { useEffect, useState } from 'react';
import { CalendarClock } from 'lucide-react';
import { Button } from '../components/ui/button';
import { gql, message, type Entry, type ContentType } from '../lib/api';
import { EntryEditor } from './EntryEditor';

const PUBLICATION_POLL_INTERVAL_MS = 15000;
const PUBLICATION_PAGE_SIZE = 25;

export function PublicationQueue({ types, role, onChanged }: {
  types: ContentType[];
  role: string;
  onChanged: () => void;
}) {
  const [filter, setFilter] = useState('upcoming');
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<{
    nodes: Entry[];
    total: number;
  }>({ nodes: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<Entry | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const time = (value?: string | null) => value ? new Date(value).toLocaleString() : 'Not scheduled';
  useEffect(() => {
    if (editor) {
      return;
    }
    let active = true;
    const load = () => {
      setLoading(true);
      return gql<{
        publicationQueue: typeof page;
      }>('query($failed:Boolean!,$overdue:Boolean!,$offset:Int!){publicationQueue(failed:$failed,overdue:$overdue,offset:$offset,first:25)}', { failed: filter === 'failed', overdue: filter === 'overdue', offset }).then(r => {
        if (active) {
          setPage(r.publicationQueue);
          setError('');
        }
      }).catch(e => {
        if (active) {
          setError(message(e));
        }
      }).finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    };
    void load();
    const timer = setInterval(load, PUBLICATION_POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [filter, offset, refresh, editor]);
  async function action(entry: Entry, name: 'retryPublication' | 'cancelSchedule') {
    setBusy(true);
    setError('');
    try {
      await gql(`mutation($id:ID!,$version:Int!){${name}(id:$id,version:$version){id}}`, { id: entry.id, version: entry.version });
      setNotice(name === 'retryPublication' ? 'Captured revision queued for retry.' : 'Schedule and failure cleared. Live content preserved.');
      setRefresh(r => r + 1);
      onChanged();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  if (editor && types.length) {
    return (
      <EntryEditor
        entry={editor}
        backLabel="Back to publications"
        types={types}
        initialType={editor.typeKey}
        editable={role !== 'reader'}
        role={role}
        onClose={() => setEditor(null)}
        onSaved={text => {
          setEditor(null);
          setNotice(text);
          setRefresh(r => r + 1);
          onChanged();
        }}
      />
    );
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">PUBLISHING QUEUE</div>
          <h1>Publications</h1>
          <p className="subtitle">All dates shown in {timezone}. Retries use the captured revision; edit and replace a schedule to include newer changes.</p>
        </div>
        <Button variant="outline" onClick={() => setRefresh(r => r + 1)}>Refresh queue</Button>
      </div>
      <label className="queue-filter">
        Queue<select value={filter} onChange={e => {
          setFilter(e.target.value);
          setOffset(0);
        }}>
          <option value="upcoming">Upcoming and due</option>
          <option value="overdue">Overdue</option>
          <option value="failed">Failed</option>
        </select>
      </label>
      {error && <p role="alert" className="form-error">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <section className="plain-card">
        {page.nodes.map(entry => (
          <article className="member-row" key={entry.id}>
            <div>
              <strong>{entry.title}</strong>
              <p>{entry.typeKey} · captured revision {entry.scheduledRevision} · {time(entry.scheduledAt || entry.scheduleError?.dueAt)} ({timezone})</p>
              {entry.scheduleError && (
                <p className="form-error">{entry.scheduleError.code}: {entry.scheduleError.message} · failed {time(entry.scheduleError.failedAt)}</p>
              )}
            </div>
            <Button variant="outline" onClick={() => setEditor(entry)}>{role === 'reader' ? 'View' : 'Edit / replace schedule'}</Button>
            {role !== 'reader' && (
              <>
                {entry.scheduleError && (
                  <Button disabled={busy} onClick={() => action(entry, 'retryPublication')}>Retry captured revision</Button>
                )}
                <Button variant="outline" disabled={busy} onClick={() => action(entry, 'cancelSchedule')}>{entry.scheduleError ? 'Resolve / discard failed schedule' : 'Cancel schedule'}</Button>
              </>
            )}
          </article>
        ))}
        {loading && !page.nodes.length && <p role="status">Loading publications…</p>}
        {!loading && !error && !page.nodes.length && (
          <div className="empty-content">
            <CalendarClock size={28} aria-hidden="true" />
            <h2>{filter === 'failed' ? 'No failed publications' : filter === 'overdue' ? 'No overdue publications' : 'Your queue is clear'}</h2>
            <p>{filter === 'upcoming' ? 'Schedule an entry from the content editor and it will appear here.' : 'Publications that need attention will appear here.'}</p>
            <a className="button button-outline" href="#content">Browse content</a>
          </div>
        )}
        <footer className="table-footer">
          <span>{page.total} publications</span>
          <div className="pagination">
            <Button variant="outline" disabled={!offset} onClick={() => setOffset(n => n - PUBLICATION_PAGE_SIZE)}>Previous</Button>
            <Button variant="outline" disabled={offset + PUBLICATION_PAGE_SIZE >= page.total} onClick={() => setOffset(n => n + PUBLICATION_PAGE_SIZE)}>Next</Button>
          </div>
        </footer>
      </section>
    </>
  );
}
