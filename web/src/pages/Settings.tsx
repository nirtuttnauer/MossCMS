import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../components/ui/button';
import { Dialog } from '../components/ui/dialog';
import { confirmNavigation, useUnsavedChanges } from '../lib/unsaved';
import { WorkspaceLocales } from '../components/WorkspaceLocales';
import { gql, message, rest, type ContentType, type Me, type Project, type Provider } from '../lib/api';
type DeliveryToken = {
  id: string;
  name: string;
  scopes: string[];
  expiresAt: string;
};
export function Settings({ project, me, providers, types, onChanged }: { project: Project; me: Me; providers: Provider[]; types: ContentType[]; onChanged: () => void }) {
  const [hooks, setHooks] = useState<{
    endpoints: {
      id: string;
      url: string;
      enabled: boolean;
    }[];
    deliveries: {
      id: string;
      eventId: string;
      state: string;
      attempts: number;
      error?: string;
    }[];
  }>({ endpoints: [], deliveries: [] });
  const [hookSecret, setHookSecret] = useState('');
  const [tokens, setTokens] = useState<DeliveryToken[]>([]);
  const [audit, setAudit] = useState<unknown>([]);
  const [secret, setSecret] = useState('');
  const tokenHeading = useRef<HTMLHeadingElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let frame = 0;
    const focusTokens = () => {
      const section = new URLSearchParams(location.hash.split('?')[1]).get('section');
      const heading = section === 'delivery-tokens' ? tokenHeading : section === 'website-preview' ? previewHeading : null;
      if (!heading) return;
      frame = requestAnimationFrame(() => { heading.current?.scrollIntoView({ block: 'start' }); heading.current?.focus(); });
    };
    focusTokens();
    window.addEventListener('moss:navigationaccepted', focusTokens);
    return () => { cancelAnimationFrame(frame); window.removeEventListener('moss:navigationaccepted', focusTokens); };
  }, []);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState({ hooks: false, tokens: false, audit: false });
  const [pending, setPending] = useState('');
  const pendingRef = useRef(false);
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [confirmation, setConfirmation] = useState<{ kind: 'token' | 'webhook'; id: string; name: string } | null>(null);
  const feedback = useRef<HTMLParagraphElement>(null);
  useUnsavedChanges(Object.values(dirty).some(Boolean), 'Discard unsaved settings changes? Saved settings will be kept.');
  useEffect(() => { if (error && !confirmation) feedback.current?.focus(); }, [error, confirmation]);
  const markDirty = (key: string, value: boolean) => setDirty(old => ({ ...old, [key]: value }));
  async function load() {
    if (project.role !== 'admin') { setLoading(false); return; }
    setLoading(true);
    setError('');
    const results = await Promise.allSettled([
      rest<typeof hooks>('/api/webhooks'),
      rest<DeliveryToken[]>('/api/tokens'),
      gql<{ auditLog: unknown }>('{auditLog}'),
    ]);
    const [webhooks, deliveryTokens, history] = results;
    if (webhooks.status === 'fulfilled') setHooks(webhooks.value);
    if (deliveryTokens.status === 'fulfilled') setTokens(deliveryTokens.value);
    if (history.status === 'fulfilled') setAudit(history.value.auditLog);
    setLoaded(old => ({ hooks: old.hooks || webhooks.status === 'fulfilled', tokens: old.tokens || deliveryTokens.status === 'fulfilled', audit: old.audit || history.status === 'fulfilled' }));
    const labels = ['Publication webhooks', 'Delivery tokens', 'Audit history'];
    setError(results.flatMap((result, index) => result.status === 'rejected' ? [`${labels[index]}: ${message(result.reason)}`] : []).join(' '));
    setLoading(false);
  }
  useEffect(() => { void load(); }, []);
  async function perform(key: string, action: () => Promise<void>) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(key); setError(''); setNotice('');
    try { await action(); }
    catch (reason) { setError(message(reason)); }
    finally { pendingRef.current = false; setPending(''); }
  }
  async function projectAction(event: FormEvent<HTMLFormElement>, create: boolean) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    await perform(create ? 'create' : 'rename', async () => {
      await rest(create ? '/api/projects' : '/api/project', create ? 'POST' : 'PATCH', body);
      markDirty(create ? 'create' : 'rename', false);
      if (create) form.reset();
      setNotice(create ? 'Workspace created. Select it in the sidebar.' : 'Workspace renamed.');
      onChanged();
    });
  }
  async function savePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    await perform('preview', async () => {
      await rest('/api/project/preview', 'PATCH', body);
      markDirty('preview', false);
      setNotice('Website preview origin saved.'); onChanged();
    });
  }
  async function newWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    await perform('webhook', async () => {
      const result = await rest<{ secret: string }>('/api/webhooks', 'POST', body);
      setHookSecret(result.secret); form.reset(); markDirty('webhook', false); await load();
    });
  }
  async function newToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    await perform('token', async () => {
      const result = await rest<{ token: string }>('/api/tokens', 'POST', { name: form.get('name'), days: Number(form.get('days')), scopes: form.getAll('scopes') });
      setSecret(result.token); element.reset(); markDirty('token', false); await load();
    });
  }
  async function confirmAccessChange() {
    if (!confirmation) return;
    const target = confirmation;
    await perform('access', async () => {
      await rest(target.kind === 'token' ? `/api/tokens/${target.id}` : `/api/webhooks/${target.id}`, 'DELETE');
      setConfirmation(null);
      setNotice(target.kind === 'token' ? 'Delivery token revoked.' : 'Webhook disabled.');
      await load();
    });
  }
  async function linkProvider(id: string) {
    if (!confirmNavigation()) return;
    await perform(`provider:${id}`, async () => {
      const response = await rest<{ url: string }>(`/auth/oauth/${id}/link`, 'POST');
      window.location.assign(response.url);
    });
  }


 return <><div className="page-heading"><div><div className="eyebrow">WORKSPACE & ACCESS</div><h1>Settings</h1><p className="subtitle">Manage workspaces, sign-in providers, and frontend access.</p></div></div>{error && !confirmation && <p ref={feedback} tabIndex={-1} className="form-error" role="alert">{error} <Button disabled={loading || Boolean(pending)} variant="outline" onClick={load}>Retry loading settings</Button></p>}{notice && <p className="notice" role="status">{notice}</p>}{loading && project.role === 'admin' && <p role="status">Loading workspace settings…</p>}<section className="plain-card"><h2>Your account</h2><p>{me.user.name} · {me.user.email}</p><p>Connected providers: {me.providers.join(', ') || 'none'}</p><div className="inline-form">{providers.filter(p => !me.providers.includes(p.id)).map(p => <Button key={p.id} disabled={Boolean(pending)} variant="outline" onClick={() => linkProvider(p.id)}>Connect {p.name}</Button>)}</div>{!providers.length && <p>Your server operator can enable GitHub or an OpenID Connect sign-in provider.</p>}</section>{project.role === 'admin' && <section className="plain-card"><h2>Workspace</h2><form className="inline-form" onChange={event => markDirty('rename', new FormData(event.currentTarget).get('name') !== project.name)} onSubmit={e => projectAction(e, false)}><input disabled={Boolean(pending)} name="name" aria-label="Workspace name" defaultValue={project.name} required maxLength={100} /><Button disabled={Boolean(pending)} type="submit">{pending === 'rename' ? 'Renaming…' : 'Rename'}</Button></form><h3 ref={previewHeading} tabIndex={-1}>Website preview</h3><p>Set the trusted website origin. Editors can open saved drafts without publishing them.</p><form className="inline-form" onChange={event => markDirty('preview', new FormData(event.currentTarget).get('origin') !== (project.previewOrigin || ''))} onSubmit={savePreview}><input disabled={Boolean(pending)} name="origin" aria-label="Website preview origin" defaultValue={project.previewOrigin || ''} placeholder="https://example.com" maxLength={2048} /><Button disabled={Boolean(pending)} type="submit">{pending === 'preview' ? 'Saving…' : 'Save preview origin'}</Button></form></section>}<WorkspaceLocales project={project} onChanged={onChanged} /><section className="plain-card"><h2>Create another workspace</h2><form className="inline-form" onChange={event => markDirty('create', Boolean(new FormData(event.currentTarget).get('name')))} onSubmit={e => projectAction(e, true)}><input disabled={Boolean(pending)} name="name" aria-label="New workspace name" placeholder="Workspace name" required maxLength={100} /><Button disabled={Boolean(pending)} type="submit" variant="outline">{pending === 'create' ? 'Creating…' : 'Create workspace'}</Button></form></section>{project.role === 'admin' && <><section className="plain-card"><h2>Import & export</h2><p>Move schemas, content, and media between workspaces. Review transforms before importing.</p><a className="button button-outline" href="#migration">Open workspace migration</a></section><section className="plain-card"><h2 ref={tokenHeading} tabIndex={-1}>Delivery tokens</h2><p>Tokens read published content only. Choose the content types each frontend may access, or leave all unchecked to allow every type.</p><form className="editor-form" onChange={event => { const form = new FormData(event.currentTarget); markDirty('token', Boolean(form.get('name')) || form.get('days') !== '90' || form.getAll('scopes').length > 0); }} onSubmit={newToken}><div className="inline-form"><input disabled={Boolean(pending)} name="name" placeholder="Frontend name" aria-label="Token name" required maxLength={100} /><label>Expires after days<input disabled={Boolean(pending)} name="days" type="number" min={1} max={365} defaultValue={90} /></label></div><div className="inline-form">{types.map(t => <label className="checkbox-label" key={t.key}><input disabled={Boolean(pending)} type="checkbox" name="scopes" value={t.key} />{t.name}</label>)}</div><Button disabled={Boolean(pending) || loading} type="submit">{pending === 'token' ? 'Creating token…' : 'Create delivery token'}</Button></form>{secret && <div className="notice"><p>Save this token now. It will not be shown again.</p><input aria-label="New delivery token" readOnly value={secret} /><Button variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(secret); setNotice('Token copied.') } catch { setNotice('Select and copy the token above.') } }}>Copy</Button></div>}{!loaded.tokens && !loading && <p>Delivery tokens unavailable. Retry loading settings above.</p>}{tokens.map(t => <div className="member-row" key={t.id}><span>{t.name}</span><small>{t.scopes.join(', ') || 'All types'} · expires {new Date(t.expiresAt).toLocaleDateString()}</small><Button disabled={Boolean(pending)} variant="outline" onClick={() => { setError(''); setConfirmation({ kind: 'token', id: t.id, name: t.name }); }}>Revoke</Button></div>)}</section><section className="plain-card"><h2>Publication webhooks</h2><p>Receive signed public change events. Configure the receiver with the secret below. Disable and recreate an endpoint to rotate its secret.</p><form className="inline-form" onChange={event => markDirty('webhook', Boolean(new FormData(event.currentTarget).get('url')))} onSubmit={newWebhook}><input disabled={Boolean(pending)} name="url" type="url" required aria-label="Webhook endpoint" placeholder="https://website.example/api/moss-events" /><Button disabled={Boolean(pending) || loading} type="submit">{pending === 'webhook' ? 'Adding webhook…' : 'Add webhook'}</Button></form>{hookSecret && <div className="notice"><p>Copy this webhook secret now. It is shown once.</p><input aria-label="New webhook secret" value={hookSecret} readOnly /></div>}{!loaded.hooks && !loading && <p>Webhooks unavailable. Retry loading settings above.</p>}{hooks.endpoints.map(h=><div className="member-row" key={h.id}><span>{h.url} · {h.enabled?'Active':'Disabled'}</span>{h.enabled && <Button disabled={Boolean(pending)} variant="outline" onClick={() => { setError(''); setConfirmation({ kind: 'webhook', id: h.id, name: h.url }); }}>Disable webhook</Button>}</div>)}<Button disabled={loading || Boolean(pending)} variant="outline" onClick={load}>Refresh delivery history</Button>{hooks.deliveries.map(d=><p key={d.id}>Event {d.eventId}: {d.state} · {d.attempts} attempts {d.error && `· ${d.error}`}</p>)}</section><section className="plain-card"><h2>Audit history</h2>{loaded.audit ? <pre tabIndex={0} aria-label="Audit history">{JSON.stringify(audit, null, 2)}</pre> : !loading && <p>Audit history unavailable. Retry loading settings above.</p>}</section></>}{confirmation && <Dialog title={confirmation.kind === 'token' ? 'Revoke delivery token?' : 'Disable webhook?'} open onClose={() => { if (!pending) { setConfirmation(null); setError(''); } }}><p>{confirmation.kind === 'token' ? `Frontends using “${confirmation.name}” will lose access to published content. Create and configure a replacement token before revoking this one if they still need access.` : `“${confirmation.name}” will stop receiving publication events. You can create a new endpoint later.`}</p>{error && <p role="alert" className="form-error">{error}</p>}<div className="modal-actions"><Button disabled={Boolean(pending)} variant="outline" onClick={() => { setConfirmation(null); setError(''); }}>Cancel</Button><Button disabled={Boolean(pending)} onClick={confirmAccessChange}>{pending ? 'Updating access…' : confirmation.kind === 'token' ? 'Revoke token' : 'Disable webhook'}</Button></div></Dialog>}</>
}
