import { useEffect, useState, type FormEvent } from 'react'
import { Button } from './ui/button'
import { message, rest, type Project } from '../lib/api'
import { LOCALE_PATTERN } from '../lib/locales'
import { useUnsavedChanges } from '../lib/unsaved'

export function WorkspaceLocales({ project, onChanged }: {
  project: Project & { defaultLocale?: string; locales?: string[] }
  onChanged: () => void
}) {
  const [defaultLocale, setDefaultLocale] = useState(project.defaultLocale || 'en')
  const [locales, setLocales] = useState((project.locales || ['en']).join(', '))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saved, setSaved] = useState({ defaultLocale, locales })
  useUnsavedChanges(project.role === 'admin' && (busy || defaultLocale !== saved.defaultLocale || locales !== saved.locales), 'Discard unsaved locale changes? Saved settings will be kept.')
  const configuredLocales = (project.locales || ['en']).join(', ')
  useEffect(() => {
    setDefaultLocale(project.defaultLocale || 'en')
    setLocales(configuredLocales)
    setSaved({ defaultLocale: project.defaultLocale || 'en', locales: configuredLocales })
  }, [project.defaultLocale, configuredLocales])
  if (project.role !== 'admin') return null
  async function save(event: FormEvent) {
    event.preventDefault()
    const suggestions = locales.split(',').map(value => value.trim())
    if (
      !suggestions.length ||
      suggestions.some(value => !LOCALE_PATTERN.test(value)) ||
      !LOCALE_PATTERN.test(defaultLocale) ||
      new Set(suggestions).size !== suggestions.length ||
      !suggestions.includes(defaultLocale)
    ) {
      setError('Use unique locale codes separated by commas, including the default locale. Examples: en, he, fr-CA.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await rest(`/api/projects/${encodeURIComponent(project.id)}`, 'PATCH', {
        defaultLocale,
        locales: suggestions,
      })
      setSaved({ defaultLocale, locales })
      setNotice('Locale defaults saved. Existing translations are preserved.')
      onChanged()
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="plain-card">
      <h2>Authoring locales</h2>
      <p>Choose the language for new localized fields. Suggestions help editors add translations; removing a suggestion keeps all existing translations.</p>
      <form className="editor-form" onSubmit={save}>
        <label>
          Default locale
          <input
            value={defaultLocale}
            onChange={event => setDefaultLocale(event.target.value)}
            required
            maxLength={16}
            autoCapitalize="none"
          />
        </label>
        <label>
          Suggested locales
          <input
            value={locales}
            onChange={event => setLocales(event.target.value)}
            required
            aria-describedby="locale-guidance"
          />
        </label>
        <small id="locale-guidance">Comma-separated codes, for example en, he, fr-CA. The default must be included.</small>
        {error && <p className="form-error" role="alert">{error}</p>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <Button type="submit" disabled={busy}>
          {busy ? 'Saving locales…' : 'Save locales'}
        </Button>
      </form>
    </section>
  )
}
