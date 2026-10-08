import { useEffect, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '../components/ui/button'
import { gql, message, rest, type Asset } from '../lib/api'

export function Assets({ role, onChanged }: { role: string; onChanged: () => void }) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  async function load() { try { setAssets((await gql<{ assets: Asset[] }>('{assets(first:100){id name mime size url}}')).assets) } catch (reason) { setError(message(reason)) } }
  useEffect(() => { void load() }, [])
  async function upload(file?: File) {
    if (!file) return
    setBusy(true); setError('')
    try { const form = new FormData(); form.append('file', file); await rest('/api/assets', 'POST', form); await load(); onChanged() }
    catch (reason) { setError(message(reason)) }
    finally { setBusy(false); if (input.current) input.current.value = '' }
  }
  return <><div className="page-heading"><div><div className="eyebrow">MEDIA LIBRARY</div><h1>Assets</h1><p className="subtitle">Upload media and attach it to content fields.</p></div>{role !== 'reader' && <><input ref={input} className="sr-only" type="file" aria-label="Upload asset" onChange={e => upload(e.target.files?.[0])} /><Button disabled={busy} onClick={() => input.current?.click()}><Upload size={16} />{busy ? 'Uploading…' : 'Upload asset'}</Button></>}</div>{error && <p className="form-error" role="alert">{error}</p>}<section className="plain-card"><p>Files up to 20 MiB. Downloads use links that expire after 15 minutes.</p><div className="table-scroll"><table><thead><tr><th>NAME</th><th>TYPE</th><th>SIZE</th><th /></tr></thead><tbody>{assets.map(a => <tr key={a.id}><td>{a.name}</td><td>{a.mime}</td><td>{(a.size / 1024).toFixed(1)} KiB</td><td><a href={a.url} target="_blank" rel="noreferrer" className="text-button">Download</a></td></tr>)}</tbody></table></div>{!assets.length && <p className="empty-state">No assets uploaded yet.</p>}</section></>
}
