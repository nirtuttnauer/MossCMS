import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button } from '../components/ui/button';
import { Dialog } from '../components/ui/dialog';
import { message, rest } from '../lib/api';
type Member = {
  id: string;
  name: string;
  email: string;
  role: string;
};
type TeamData = {
  members: Member[];
  invitations: {
    id: string;
    email: string;
    role: string;
    expiresAt: string;
  }[];
};
export function Team({ role, onChanged }: { role: string; onChanged: () => void }) {
  const [team, setTeam] = useState<TeamData>({ members: [], invitations: [] });
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [remove, setRemove] = useState<Member | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const busyRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  async function load() {
    setLoading(true); setError('');
    try {
      setTeam(await rest<TeamData>('/api/team'));
      setLoaded(true);
    }
    catch (reason) {
      setError(message(reason));
    }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function perform(key: string, action: () => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(key); setError(''); setNotice('');
    try { await action(); }
    catch (reason) { setError(message(reason)); }
    finally { busyRef.current = false; setBusy(''); }
  }
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    await perform('invite', async () => {
      const result = await rest<{ url: string }>('/api/team/invitations', 'POST', body);
      setUrl(result.url); form.reset();
      setNotice('Invitation created. Share the link below.'); await load();
    });
  }
  async function change(member: Member, nextRole: string) {
    await perform(`role:${member.id}`, async () => {
      await rest(`/api/team/${member.id}`, 'PATCH', { role: nextRole });
      setNotice('Member role updated.'); await load(); onChanged();
    });
  }
  async function removeMember() {
    if (!remove) return;
    const member = remove;
    await perform('remove', async () => {
      await rest(`/api/team/${member.id}`, 'DELETE');
      setRemove(null); setNotice('Member access removed.'); await load(); onChanged();
    });
  }
  async function revoke(id: string) {
    await perform(`revoke:${id}`, async () => {
      await rest(`/api/team/invitations/${id}`, 'DELETE');
      setNotice('Invitation revoked.'); await load();
    });
  }


 return <><div className="page-heading"><div><div className="eyebrow">WORK TOGETHER</div><h1>Team</h1><p className="subtitle">Invite teammates and manage their access to this workspace.</p></div></div>{error && !remove && <p className="form-error" role="alert">{error} <Button disabled={loading || Boolean(busy)} variant="outline" onClick={load}>Retry loading team</Button></p>}{notice && <p className="notice" role="status">{notice}</p>}{loading && <p role="status">Loading team…</p>}<section className="plain-card"><h2>Members</h2><p>Administrators manage the workspace. Editors publish content. Readers can view drafts without editing.</p><div className="table-scroll"><table><thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{team.members.map(member => <tr key={member.id}><td>{member.name}</td><td>{member.email}</td><td>{role === 'admin' ? <select disabled={Boolean(busy) || loading} aria-label={`Role for ${member.name}`} value={member.role} onChange={e => change(member, e.target.value)}>{['admin', 'editor', 'reader'].map(r => <option key={r}>{r}</option>)}</select> : member.role}</td><td>{role === 'admin' && <button disabled={Boolean(busy) || loading} className="text-button muted" onClick={() => { setError(''); setRemove(member); }}>Remove</button>}</td></tr>)}</tbody></table></div></section>{role === 'admin' && <section className="plain-card"><h2>Invite a teammate</h2><form className="inline-form" onSubmit={invite}><input disabled={Boolean(busy)} type="email" name="email" required aria-label="Teammate email" placeholder="teammate@example.com" /><select disabled={Boolean(busy)} name="role" defaultValue="editor" aria-label="Invitation role"><option>reader</option><option>editor</option><option>admin</option></select><Button disabled={Boolean(busy) || loading} type="submit">{busy === 'invite' ? 'Creating invitation…' : 'Create invitation'}</Button></form>{url && <div className="notice"><p>Share this invitation with the intended teammate. It expires in seven days.</p><input aria-label="Invitation link" readOnly value={url} /><Button variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(url); setNotice('Invitation link copied.') } catch { setNotice('Select and copy the invitation link above.') } }}>Copy link</Button></div>}<h3>Pending invitations</h3>{team.invitations.length ? team.invitations.map(invitation => <div className="member-row" key={invitation.id}><span>{invitation.email} · {invitation.role}</span><small>Expires {new Date(invitation.expiresAt).toLocaleDateString()}</small><Button disabled={Boolean(busy) || loading} variant="outline" onClick={() => revoke(invitation.id)}>{busy === `revoke:${invitation.id}` ? 'Revoking…' : 'Revoke'}</Button></div>) : loaded ? <p>No pending invitations.</p> : !loading && <p>Invitations unavailable. Retry loading team above.</p>}</section>}{remove && <Dialog title="Remove team member?" open onClose={() => { if (!busy) { setRemove(null); setError(''); } }}><p>{remove.name} will lose access to this workspace. You can invite them again later.</p>{error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><Button disabled={Boolean(busy)} variant="outline" onClick={() => { setRemove(null); setError(''); }}>Cancel</Button><Button disabled={Boolean(busy)} onClick={removeMember}>{busy === 'remove' ? 'Removing access…' : 'Remove access'}</Button></div></Dialog>}</>
}
