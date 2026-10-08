import { useState, type FormEvent } from 'react'
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
      if (!invite || !signingIn) location.hash = 'content'
      else setSigningIn(false)
      onSuccess()
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  return <div className="auth-shell"><div className="auth-brand"><div className="brand-mark"><span /></div>MossCMS</div><form className="auth-card" onSubmit={submit}><span className="eyebrow">YOUR CONTENT. YOUR SERVER.</span><h1>{title}</h1><p>{!initialized ? 'Set up the first administrator account.' : reset ? 'Use the email associated with this recovery link.' : invite ? 'Accept your invitation using the invited email address.' : 'Sign in to manage content and your team.'}</p>{(!initialized || (invite && !signingIn && !me)) && <label>Name<input name="name" required maxLength={100} autoComplete="name" /></label>}<label>Email<input name="email" type="email" required defaultValue={me?.user.email} autoComplete="email" /></label>{!(invite && me && !signingIn) && <label>{reset ? 'New password' : 'Password'}<input name="password" type="password" required minLength={!initialized || reset || (invite && !signingIn) ? 12 : 1} maxLength={128} autoComplete={reset || !initialized || invite ? 'new-password' : 'current-password'} /></label>}{!initialized && <label>Setup token<input name="token" type="password" required /><small>Find MOSS_SETUP_TOKEN in the server’s .env configuration.</small></label>}{error && <p className="form-error" role="alert">{error}</p>}<Button disabled={busy} type="submit">{busy ? 'Please wait…' : title === 'Welcome back' ? 'Sign in' : invite ? 'Accept invitation' : reset ? 'Set password' : 'Create administrator'}</Button>{invite && !me && <button className="text-button" type="button" onClick={() => setSigningIn(!signingIn)}>{signingIn ? 'Return to invitation' : 'Already have an account? Sign in first'}</button>}{initialized && !reset && providers.map(provider => <a className="button button-outline oauth-button" key={provider.id} href={`/auth/oauth/${provider.id}/start${invite ? `?invite=${encodeURIComponent(token)}` : ''}`}>Continue with {provider.name}</a>)}{initialized && !invite && !reset && <p className="auth-note">For password recovery, ask your server operator for a recovery link.</p>}</form></div>
}
