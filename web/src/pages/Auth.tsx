import { useState, type FormEvent } from 'react'
import { ArrowRight, LockKeyhole } from 'lucide-react'
import { Button } from '../components/ui/button'
import { message, rest, type Me, type Provider } from '../lib/api'

export function Auth({ initialized, providers, onSuccess, me }: { initialized: boolean; providers: Provider[]; onSuccess: () => void; me: Me | null }) {
  const hash = location.hash.slice(1)
  const invite = hash.startsWith('invite/')
  const reset = hash.startsWith('reset/')
  const token = invite || reset ? hash.split('/')[1] : ''
  const [error, setError] = useState(new URLSearchParams(hash.split('?')[1]).get('error') || '')
  const [busy, setBusy] = useState(false)
  const [signingIn, setSigningIn] = useState(false)
  const title = !initialized ? 'Create your workspace' : reset ? 'Reset your password' : invite && !signingIn ? 'Join your team' : 'Welcome back'
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const form = Object.fromEntries(new FormData(event.currentTarget))
    try {
      const path = !initialized ? '/auth/setup' : (invite && !signingIn) || reset ? '/auth/accept' : '/auth/login'
      await rest(path, 'POST', { ...form, token: token || form.token, name: form.name || me?.user.name || 'Member', password: form.password || 'existing-account' })
      if (invite && signingIn) setSigningIn(false)
      else if (!['content', 'overview', 'publications', 'types', 'assets', 'team', 'explorer', 'settings'].includes(hash.split('?')[0])) location.hash = 'content'
      onSuccess()
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  return <main className="auth-shell auth-login">
    <aside className="auth-artwork" aria-label="About MossCMS">
      <img className="auth-artwork-image" src="/brand/moss-arch-v2.webp" alt="" />
      <div className="auth-artwork-copy">
        <span className="eyebrow">ROOM TO GROW</span>
        <h2>Your content.<br />Your server.</h2>
      </div>
      <div className="auth-artwork-footer"><span>MossCMS</span><span>Rooted in your control.</span></div>
    </aside>
    <div className="auth-panel">
      <header className="auth-brand"><img className="brand-mark" src="/brand/moss-symbol-v2.png" alt="" width="48" height="48" /><span>Moss<span className="brand-light">CMS</span></span></header>
      <form className="auth-card" onSubmit={submit} aria-labelledby="auth-title" aria-busy={busy}>
        <div className="auth-heading">
          <span className="eyebrow">{!initialized ? 'GET STARTED' : reset ? 'ACCOUNT RECOVERY' : invite && !signingIn ? 'YOUR INVITATION' : 'YOUR WORKSPACE AWAITS'}</span>
          <h1 id="auth-title">{title}</h1>
          <p>{!initialized ? 'Set up the first administrator account.' : reset ? 'Use the email associated with this recovery link.' : invite && !signingIn ? 'Accept your invitation using the invited email address.' : 'Sign in to manage content and your team.'}</p>
        </div>
        {(!initialized || (invite && !signingIn && !me)) && <label>Name<input name="name" required maxLength={100} autoComplete="name" /></label>}
        <label>Email<input name="email" type="email" required defaultValue={me?.user.email} autoComplete="email" placeholder="you@example.com" /></label>
        {!(invite && me && !signingIn) && <label>{reset ? 'New password' : 'Password'}<input name="password" type="password" required minLength={!initialized || reset || (invite && !signingIn) ? 12 : 1} maxLength={128} autoComplete={reset || !initialized || invite ? 'new-password' : 'current-password'} /></label>}
        {!initialized && <label>Setup token<input name="token" type="password" required /><small>Find MOSS_SETUP_TOKEN in the server’s .env configuration.</small></label>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <Button disabled={busy} type="submit">{busy ? 'Please wait…' : title === 'Welcome back' ? 'Sign in' : invite ? 'Accept invitation' : reset ? 'Set password' : 'Create administrator'}{!busy && <ArrowRight size={17} aria-hidden="true" />}</Button>
        {invite && !me && <button className="text-button" type="button" onClick={() => setSigningIn(!signingIn)}>{signingIn ? 'Return to invitation' : 'Already have an account? Sign in first'}</button>}
        {initialized && !reset && providers.length > 0 && <div className="auth-divider"><span>or continue with</span></div>}
        {initialized && !reset && providers.map(provider => <a className="button button-outline oauth-button" key={provider.id} href={`/auth/oauth/${provider.id}/start${invite ? `?invite=${encodeURIComponent(token)}` : ''}`}>Continue with {provider.name}</a>)}
        {initialized && !invite && !reset && <p className="auth-note">Need help signing in?<br />Ask your server operator for a password recovery link.</p>}
      </form>
      <footer className="auth-panel-footer"><LockKeyhole size={14} aria-hidden="true" />Self-hosted. Yours to manage.</footer>
    </div>
  </main>
}
