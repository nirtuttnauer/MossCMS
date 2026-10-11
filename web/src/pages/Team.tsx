import { useEffect, useState, type FormEvent } from 'react';
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
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      setTeam(await rest<TeamData>('/api/team'));
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  useEffect(() => { void load(); }, []);
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const body = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await rest<{
        url: string;
      }>('/api/team/invitations', 'POST', body);
      setUrl(result.url);
      await load();
    }
    catch (reason) {
      setError(message(reason));
    }
    finally {
      setBusy(false);
    }
  }
  async function change(member: Member, nextRole: string) {
    try {
      await rest(`/api/team/${member.id}`, 'PATCH', { role: nextRole });
      setNotice('Member role updated.');
      await load();
      onChanged();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function removeMember() {
    try {
      await rest(`/api/team/${remove!.id}`, 'DELETE');
      setRemove(null);
      setNotice('Member access removed.');
      await load();
      onChanged();
    }
    catch (reason) {
      setError(message(reason));
    }
  }
  async function revoke(id: string) {
    try {
      await rest(`/api/team/invitations/${id}`, 'DELETE');
      await load();
    }
    catch (reason) {
      setError(message(reason));
    }
  }


 return <><div className="page-heading"><div><div className="eyebrow">WORK TOGETHER</div><h1>Team</h1><p className="subtitle">Invite teammates and manage their access to this workspace.</p></div></div>{error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}<section className="plain-card"><h2>Members</h2><p>Administrators manage the workspace. Editors publish content. Readers can view drafts without editing.</p><div className="table-scroll"><table><thead><tr><th>NAME</th><th>EMAIL</th><th>ROLE</th><th /></tr></thead><tbody>{team.members.map(member => <tr key={member.id}><td>{member.name}</td><td>{member.email}</td><td>{role === 'admin' ? <select aria-label={`Role for ${member.name}`} value={member.role} onChange={e => change(member, e.target.value)}>{['admin', 'editor', 'reader'].map(r => <option key={r}>{r}</option>)}</select> : member.role}</td><td>{role === 'admin' && <button className="text-button muted" onClick={() => setRemove(member)}>Remove</button>}</td></tr>)}</tbody></table></div></section>{role === 'admin' && <section className="plain-card"><h2>Invite a teammate</h2><form className="inline-form" onSubmit={invite}><input type="email" name="email" required aria-label="Teammate email" placeholder="teammate@example.com" /><select name="role" defaultValue="editor" aria-label="Invitation role"><option>reader</option><option>editor</option><option>admin</option></select><Button disabled={busy} type="submit">Create invitation</Button></form>{url && <div className="notice"><p>Share this invitation with the intended teammate. It expires in seven days.</p><input aria-label="Invitation link" readOnly value={url} /><Button variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(url); setNotice('Invitation link copied.') } catch { setNotice('Select and copy the invitation link above.') } }}>Copy link</Button></div>}<h3>Pending invitations</h3>{team.invitations.length ? team.invitations.map(invitation => <div className="member-row" key={invitation.id}><span>{invitation.email} · {invitation.role}</span><small>Expires {new Date(invitation.expiresAt).toLocaleDateString()}</small><Button variant="outline" onClick={() => revoke(invitation.id)}>Revoke</Button></div>) : <p>No pending invitations.</p>}</section>}{remove && <Dialog title="Remove team member?" open onClose={() => setRemove(null)}><p>{remove.name} will lose access to this workspace. You can invite them again later.</p>{error && <p className="form-error">{error}</p>}<div className="modal-actions"><Button variant="outline" onClick={() => setRemove(null)}>Cancel</Button><Button onClick={removeMember}>Remove access</Button></div></Dialog>}</>
}
