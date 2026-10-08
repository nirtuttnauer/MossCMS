import { useId, useRef, useState } from 'react'
import { Button } from './ui/button'
import { Markdown } from './Markdown'
import type { Asset } from '../lib/api'
export function MarkdownInput({label,value,onChange,required,assets}:{label:string;value:string;onChange:(value:string)=>void;required?:boolean;assets:Asset[]}) {
  const id=useId(), input=useRef<HTMLTextAreaElement>(null)
  const [preview,setPreview]=useState(false), [image,setImage]=useState(''), [alt,setAlt]=useState('')
  function insert(before:string,after='',placeholder='text',replaceSelection=false) {
    const start=input.current?.selectionStart ?? value.length, end=input.current?.selectionEnd ?? start
    const selection=replaceSelection?placeholder:value.slice(start,end)||placeholder
    onChange(value.slice(0,start)+before+selection+after+value.slice(end))
    requestAnimationFrame(()=>{input.current?.focus();input.current?.setSelectionRange(start+before.length,start+before.length+selection.length)})
  }
  return <section><label htmlFor={id}>{label}{required?' *':''}</label>
    <div className="markdown-toolbar" role="toolbar" aria-label={`${label} formatting`}>
      {[['Heading','## ',''],['Bold','**','**'],['Italic','*','*'],['Bullet list','- ',''],['Numbered list','1. ',''],['Link','[','](https://example.com)'],['Code block','\n```\n','\n```\n']].map(([name,before,after])=><Button type="button" variant="outline" key={name} onClick={()=>{setPreview(false);insert(before,after)}}>{name}</Button>)}
      <Button type="button" variant="outline" aria-pressed={preview} onClick={()=>setPreview(v=>!v)}>{preview?'Edit Markdown':'Preview Markdown'}</Button>
    </div>
    <textarea id={id} ref={input} rows={8} value={value} required={required} onChange={e=>onChange(e.target.value)} hidden={preview} />
    {preview && <div className="markdown-preview"><Markdown text={value} assets={assets} /></div>}
    <div className="inline-form"><label>Image asset<select value={image} onChange={e=>setImage(e.target.value)}><option value="">Choose image…</option>{assets.filter(a=>a.mime.startsWith('image/')).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>Image alt text<input value={alt} onChange={e=>setAlt(e.target.value)} /></label><Button type="button" variant="outline" disabled={!image || !alt.trim()} onClick={()=>{setPreview(false);insert(`![${alt.replace(/[\[\]\\]/g,'')}](`,')',`asset:${image}`,true)}}>Insert image</Button></div>
    <small>Markdown is saved as text. Images use durable asset IDs; HTML is disabled.</small>
  </section>
}
