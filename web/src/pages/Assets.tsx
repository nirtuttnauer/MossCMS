import { useEffect, useRef, useState } from 'react';
import { assetPageQuery } from '../components/AssetPicker';
import { FolderOpen, Search, Upload } from 'lucide-react';
import { Button } from '../components/ui/button';
import { can } from '../lib/access';
import { gql, message, rest, type Asset } from '../lib/api';
export function Assets({ role, onChanged }: { role: string; onChanged: () => void }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [search, setSearch] = useState(''), [cursors, setCursors] = useState<(string | null)[]>([null]), [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    async function load() {
      try {
        const result = await gql<{
          assetPage: { nodes: Asset[]; endCursor: string | null };
        }>(assetPageQuery, { search, imagesOnly: false, after: cursors[cursors.length - 1] });
        if (active) {
          setAssets(result.assetPage.nodes);
          setNext(result.assetPage.endCursor);
        }
      } catch (reason) {
        if (active) setError(message(reason));
      } finally {
        if (active) setLoading(false);
      }
    }
    const timer = search ? setTimeout(() => { void load(); }, 200) : undefined;
    if (!search) void load();
    return () => { active = false; clearTimeout(timer); };
  }, [search, cursors, refresh]);
  async function upload(file?: File) {
    if (!file)
      return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      await rest('/api/assets', 'POST', form);
      setRefresh(value => value + 1);
      onChanged();
    }
    catch (reason) {
      setError(message(reason));
    }
    finally {
      setBusy(false);
      if (input.current)
        input.current.value = '';
    }
  }


 return <><div className="page-heading"><div><div className="eyebrow">MEDIA LIBRARY</div><h1>Assets</h1><p className="subtitle">Upload media and attach it to content fields.</p></div>{can(role, 'media') && <><input ref={input} hidden type="file" aria-label="Upload asset" onChange={e => upload(e.target.files?.[0])} /><Button disabled={busy} onClick={() => input.current?.click()}><Upload size={16} />{busy ? 'Uploading…' : 'Upload asset'}</Button></>}</div>{error && <p className="form-error" role="alert">{error} <Button variant="outline" onClick={() => setRefresh(value => value + 1)}>Retry assets</Button></p>}<section className="plain-card" aria-label="Media library" aria-busy={loading}><p>Files up to 20 MiB. Downloads use links that expire after 15 minutes.</p><label className="library-search">Search assets<input value={search} onChange={e=>{setSearch(e.target.value);setCursors([null])}} /></label>{assets.length > 0 && <><div className="table-scroll"><table><thead><tr><th>NAME</th><th>TYPE</th><th>SIZE</th><th>DOWNLOAD</th></tr></thead><tbody>{assets.map(a => <tr key={a.id}><td><div className="asset-name">{a.variants?.[0] && <img src={a.variants[0].url} alt="" width={64} height={48} loading="lazy" />} {a.name}</div></td><td>{a.mime}</td><td>{(a.size / 1024).toFixed(1)} KiB</td><td><a href={a.url} target="_blank" rel="noreferrer" className="text-button">Download</a></td></tr>)}</tbody></table></div><div className="pagination"><Button variant="outline" disabled={loading || cursors.length===1} onClick={()=>setCursors(c=>c.slice(0,-1))}>Previous</Button><Button variant="outline" disabled={loading || !next} onClick={()=>setCursors(c=>[...c,next])}>Next</Button></div></>}{loading && <p role="status">Loading assets…</p>}{!loading && !assets.length && !error && <div className="empty-content"><FolderOpen size={28} aria-hidden="true" /><h2>{search ? "No matching assets" : "A home for your media"}</h2><p>{search ? "Try a different filename or clear your search." : "Upload your first image or document to use it in your content."}</p>{search ? <Button variant="outline" onClick={() => { setSearch(''); setCursors([null]) }}><Search size={16} aria-hidden="true" />Clear search</Button> : role !== 'reader' && <Button variant="outline" disabled={busy} onClick={() => input.current?.click()}><Upload size={16} aria-hidden="true" />Upload asset</Button>}</div>}</section></>
}
