import { useEffect, useRef, useState } from 'react';
import { ApiError, draftReceiptQuery, entryFields, getContext, gql, message, saveDraftMutation, type Entry } from './api';
type Values = {
  typeKey: string;
  slug: string;
  data: Record<string, unknown>;
};
type Pending = {
  key: string;
  values: Record<string, unknown>;
  signature: string;
};
export function useDraftAutosave(
  initial: Entry | null,
  values: Values,
  enabled: boolean,
  valid: boolean,
  delay = 900,
  createOnSave = false,
) {
  const signature = JSON.stringify(values);
  const [entry, setEntry] = useState(initial);
  const [state, setState] = useState('Saved');
  const [error, setError] = useState('');
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [server, setServer] = useState<Entry | null>(null);
  const [online, setOnline] = useState(navigator.onLine);
  const [retry, setRetry] = useState(0);
  const initialContext = useRef(getContext());
  const acknowledged = useRef(initial);
  const saved = useRef(createOnSave && !initial ? '' : signature);
  const latest = useRef({ values, signature, valid });
  latest.current = { values, signature, valid };
  const active = useRef(true);
  const inFlight = useRef<Promise<Entry | null> | null>(null);
  const pending = useRef<Pending | null>(null);
  const blocked = useRef(false);
  const sameContext = () => JSON.stringify(getContext()) === JSON.stringify(initialContext.current);
  useEffect(() => {
    active.current = true;
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      active.current = false;
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  function accept(record: Entry, snapshot: Pending) {
    acknowledged.current = record;
    saved.current = snapshot.signature;
    pending.current = null;
    if (active.current && sameContext()) {
      setEntry(record);
      setError('');
      setValidationErrors({});
      setState('Saved');
    }
  }
  async function run(): Promise<Entry | null> {
    if (blocked.current) {
      throw new Error('Resolve the concurrent edit conflict before saving.');
    }
    while (pending.current || latest.current.signature !== saved.current) {
      if (!active.current || !sameContext()) {
        throw new Error('Editor workspace changed; delayed save cancelled.');
      }
      if (!navigator.onLine) {
        setState('Offline');
        throw new Error('Offline. Your edits remain in this editor.');
      }
      if (!pending.current) {
        if (!latest.current.valid) {
          setState('Incomplete');
          throw new Error('Complete the required fields and slug before saving.');
        }
        const record = acknowledged.current;
        pending.current = {
          key: crypto.randomUUID(),
          signature: latest.current.signature,
          values: {
            ...latest.current.values,
            id: record?.id,
            version: record?.version,
          },
        };
      }
      const snapshot = pending.current;
      setState('Saving');
      setError('');
      try {
        const result = await gql<{
          saveDraft: Entry;
        }>(saveDraftMutation, { ...snapshot.values, requestKey: snapshot.key }, initialContext.current);
        accept(result.saveDraft, snapshot);
      }
      catch (reason) {
        if (!active.current || !sameContext()) {
          throw reason;
        }
        if (reason instanceof ApiError && reason.uncertain) {
          try {
            const result = await gql<{
              draftReceipt: Entry | null;
            }>(draftReceiptQuery, { key: snapshot.key }, initialContext.current);
            if (result.draftReceipt) {
              accept(result.draftReceipt, snapshot);
              continue;
            }
          }
          catch {
            /* Retain the identical request key until reconciliation succeeds. */
          }
          setState('Uncertain');
          setError('Save outcome is unconfirmed. Check and retry; the same request key prevents duplicate entries.');
        }
        else {
          pending.current = null;
          blocked.current = Boolean(acknowledged.current)
            && reason instanceof ApiError
            && reason.code === 'CONFLICT'
            && !reason.fieldPath
            && !reason.fieldErrors;
          setState(blocked.current ? 'Conflict' : 'Error');
          setError(message(reason));
          setValidationErrors(reason instanceof ApiError ? reason.fieldErrors || {} : {});
        }
        throw reason;
      }
    }
    return acknowledged.current;
  }
  function flush(): Promise<Entry | null> {
    if (inFlight.current) {
      return inFlight.current.then(() => flush());
    }
    const promise = run();
    inFlight.current = promise;
    void promise.finally(() => {
      if (inFlight.current === promise) {
        inFlight.current = null;
      }
    }).catch(() => { });
    return promise;
  }
  useEffect(() => {
    if (state === 'Incomplete' && valid && signature === saved.current && !pending.current && !inFlight.current && !blocked.current) {
      setState('Saved');
      return;
    }
    if (!enabled || !online || blocked.current || signature === saved.current) {
      return;
    }
    if (!valid) {
      setState('Incomplete');
      return;
    }
    if (state === 'Uncertain' || state === 'Error') {
      return;
    }
    const timer = setTimeout(() => {
      void flush().catch(() => { });
    }, delay);
    return () => clearTimeout(timer);
  }, [signature, enabled, valid, online, retry]);
  async function compare() {
    const record = acknowledged.current;
    if (!record) {
      return;
    }
    try {
      const result = await gql<{
        entry: Entry;
      }>(`query($id:ID!){entry(id:$id){${entryFields}}}`, { id: record.id }, initialContext.current);
      setServer(result.entry);
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  function reload(): Entry | null {
    if (!server) {
      return null;
    }
    acknowledged.current = server;
    pending.current = null;
    blocked.current = false;
    setEntry(server);
    saved.current = JSON.stringify({ typeKey: server.typeKey, slug: server.slug, data: server.data });
    setServer(null);
    setError('');
    setState('Saved');
    return server;
  }
  return {
    entry,
    state: !online && signature !== saved.current
      ? 'Offline'
      : state === 'Saved' && signature !== saved.current ? 'Unsaved changes' : state,
    error,
    server,
    dirty: signature !== saved.current,
    validationErrors,
    flush,
    compare,
    reload,
    retry: () => {
      setState('Saving');
      setRetry(v => v + 1);
      void flush().catch(() => { });
    },
  };
}
