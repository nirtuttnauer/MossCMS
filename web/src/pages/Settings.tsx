import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '../components/ui/button';
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
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function load() {
    if (project.role !== 'admin')
      return;
    try {
      setHooks(await rest('/api/webhooks'));
      setTokens(await rest<DeliveryToken[]>('/api/tokens'));
      setAudit((await gql<{
        auditLog: unknown;
      }>('{auditLog}')).auditLog);
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  useEffect(() => { void load(); }, []);
  async function projectAction(event: FormEvent<HTMLFormElement>, create: boolean) {
    event.preventDefault();
    setError('');
    try {
      await rest(create ? '/api/projects' : '/api/project', create ? 'POST' : 'PATCH', Object.fromEntries(new FormData(event.currentTarget)));
      setNotice(create ? 'Workspace created. Select it in the sidebar.' : 'Workspace renamed.');
      onChanged();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function savePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    try {
      await rest('/api/project/preview', 'PATCH', Object.fromEntries(new FormData(event.currentTarget)));
      setNotice('Website preview origin saved.');
      onChanged();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function newWebhook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setHookSecret('');
    try {
      const result = await rest<{
        secret: string;
      }>('/api/webhooks', 'POST', Object.fromEntries(new FormData(event.currentTarget)));
      setHookSecret(result.secret);
      await load();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function disableWebhook(id: string) {
    try {
      await rest(`/api/webhooks/${id}`, 'DELETE');
      await load();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function newToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const form = new FormData(event.currentTarget);
    try {
      const result = await rest<{
        token: string;
      }>('/api/tokens', 'POST', { name: form.get('name'), days: Number(form.get('days')), scopes: form.getAll('scopes') });
      setSecret(result.token);
      await load();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function revoke(id: string) {
    try {
      await rest(`/api/tokens/${id}`, 'DELETE');
      await load();
      setNotice('Delivery token revoked.');
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function linkProvider(id: string) {
    try {
      const response = await rest<{
        url: string;
      }>(`/auth/oauth/${id}/link`, 'POST');
      window.location.assign(response.url);
    }
    catch (reason) {
      setError(message(reason));
    }
  }


 return <><div className="page-heading"><div><div className="eyebrow">WORKSPACE & ACCESS</div><h1>Settings</h1><p className="subtitle">Manage workspaces, sign-in providers, and frontend access.</p></div></div>{error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}<section className="plain-card"><h2>Your account</h2><p>{me.user.name} · {me.user.email}</p><p>Connected providers: {me.providers.join(', ') || 'none'}</p><div className="inline-form">{providers.filter(p => !me.providers.includes(p.id)).map(p => <Button key={p.id} variant="outline" onClick={() => linkProvider(p.id)}>Connect {p.name}</Button>)}</div>{!providers.length && <p>Your server operator can enable GitHub or an OpenID Connect sign-in provider.</p>}</section>{project.role === 'admin' && <section className="plain-card"><h2>Workspace</h2><form className="inline-form" onSubmit={e => projectAction(e, false)}><input name="name" aria-label="Workspace name" defaultValue={project.name} required maxLength={100} /><Button type="submit">Rename</Button></form><h3>Website preview</h3><p>Set the trusted website origin. Editors can open saved drafts without publishing them.</p><form className="inline-form" onSubmit={savePreview}><input name="origin" aria-label="Website preview origin" defaultValue={project.previewOrigin || ''} placeholder="https://example.com" maxLength={2048} /><Button type="submit">Save preview origin</Button></form></section>}<WorkspaceLocales project={project} onChanged={onChanged} /><section className="plain-card"><h2>Create another workspace</h2><form className="inline-form" onSubmit={e => projectAction(e, true)}><input name="name" aria-label="New workspace name" placeholder="Workspace name" required maxLength={100} /><Button type="submit" variant="outline">Create workspace</Button></form></section>{project.role === 'admin' && <><section className="plain-card"><h2>Delivery tokens</h2><p>Tokens read published content only. Choose the content types each frontend may access, or leave all unchecked to allow every type.</p><form className="editor-form" onSubmit={newToken}><div className="inline-form"><input name="name" placeholder="Frontend name" aria-label="Token name" required maxLength={100} /><label>Expires after days<input name="days" type="number" min={1} max={365} defaultValue={90} /></label></div><div className="inline-form">{types.map(t => <label className="checkbox-label" key={t.key}><input type="checkbox" name="scopes" value={t.key} />{t.name}</label>)}</div><Button type="submit">Create delivery token</Button></form>{secret && <div className="notice"><p>Save this token now. It will not be shown again.</p><input aria-label="New delivery token" readOnly value={secret} /><Button variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(secret); setNotice('Token copied.') } catch { setNotice('Select and copy the token above.') } }}>Copy</Button></div>}{tokens.map(t => <div className="member-row" key={t.id}><span>{t.name}</span><small>{t.scopes.join(', ') || 'All types'} · expires {new Date(t.expiresAt).toLocaleDateString()}</small><Button variant="outline" onClick={() => revoke(t.id)}>Revoke</Button></div>)}</section><section className="plain-card"><h2>Publication webhooks</h2><p>Receive signed public change events. Configure the receiver with the secret below. Disable and recreate an endpoint to rotate its secret.</p><form className="inline-form" onSubmit={newWebhook}><input name="url" type="url" required aria-label="Webhook endpoint" placeholder="https://website.example/api/moss-events" /><Button type="submit">Add webhook</Button></form>{hookSecret && <div className="notice"><p>Copy this webhook secret now. It is shown once.</p><input aria-label="New webhook secret" value={hookSecret} readOnly /></div>}{hooks.endpoints.map(h=><div className="member-row" key={h.id}><span>{h.url} · {h.enabled?'Active':'Disabled'}</span>{h.enabled && <Button variant="outline" onClick={()=>disableWebhook(h.id)}>Disable webhook</Button>}</div>)}<Button variant="outline" onClick={load}>Refresh delivery history</Button>{hooks.deliveries.map(d=><p key={d.id}>Event {d.eventId}: {d.state} · {d.attempts} attempts {d.error && `· ${d.error}`}</p>)}</section><section className="plain-card"><h2>Audit history</h2><pre>{JSON.stringify(audit, null, 2)}</pre></section></>}</>
}
