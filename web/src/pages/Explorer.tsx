import { useState, type FormEvent } from 'react'
import { Button } from '../components/ui/button'
import { gql, message, type ContentType } from '../lib/api'
import { DeliveryHandoff } from '../components/DeliveryHandoff'

export function Explorer({ types }: { types: ContentType[] }) {
  const [query, setQuery] = useState('{ entries(first: 5) { nodes { id slug status data } total endCursor hasNextPage } }')
  const [variables, setVariables] = useState('{}')
  const [token, setToken] = useState('')
  const [output, setOutput] = useState('Run a query to see its result.')
  const [busy, setBusy] = useState(false)
  const [handoffType, setHandoffType] = useState('')
  const selectedType = types.find(type => type.key === handoffType) || types[0]

  async function run(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      let result
      if (token) {
        const response = await fetch('/delivery/graphql', {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ query, variables: JSON.parse(variables) }),
        })
        result = await response.json()
      } else {
        result = await gql(query, JSON.parse(variables))
      }
      setOutput(JSON.stringify(result, null, 2))
    } catch (reason) {
      setOutput(message(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">QUERY YOUR CONTENT</div>
          <h1>API explorer</h1>
          <p className="subtitle">Try editorial queries or use a delivery token to preview frontend access.</p>
        </div>
      </div>
      <section className="plain-card">
        <p>
          Generated typed queries: {types.map(t => (
            <code key={t.key}>allCms{t.key[0].toUpperCase() + t.key.slice(1)} </code>
          ))}
        </p>
        <form className="editor-form" onSubmit={run}>
          <label>
            Query
            <textarea
              className="code-input"
              rows={10}
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </label>
          <label>
            Variables
            <textarea
              className="code-input"
              rows={4}
              value={variables}
              onChange={e => setVariables(e.target.value)}
            />
          </label>
          <label>
            Delivery token (optional)
            <input
              type="password"
              value={token}
              autoComplete="off"
              onChange={e => setToken(e.target.value)}
            />
          </label>
          <Button disabled={busy} type="submit">{busy ? 'Running…' : 'Run query'}</Button>
        </form>
        <h2>Result</h2>
        <pre role="status">{output}</pre>
      </section>
      {selectedType && <section className="plain-card">{types.length > 1 && <label>Integration content type<select value={selectedType.key} onChange={event => setHandoffType(event.target.value)}>{types.map(type => <option key={type.key} value={type.key}>{type.name}</option>)}</select></label>}<DeliveryHandoff typeKey={selectedType.key} /></section>}
    </>
  )
}
