import { useEffect, useState } from 'react'
import { Markdown } from './Markdown'
import type { MarkdownAsset } from '../../../shared/markdown.mjs'
export type ImageField = {asset?:string;alt?:string;focalX?:number;focalY?:number;fit?:'cover'|'contain';caption?:string}
export type ImageAsset = MarkdownAsset & {width?:number;height?:number;variants?:{width:number;height:number;url:string}[]}
export function ContentImage({image,assets=[],priority=false}:{image?:ImageField;assets?:ImageAsset[];priority?:boolean}) {
  const asset=assets.find(a=>a.id===image?.asset),variants=asset?.variants || [],source=variants[variants.length-1]?.url
  const [broken,setBroken]=useState(false)
  useEffect(()=>setBroken(false),[source])
  if(!image || !asset || !source || broken || !['image/jpeg','image/png','image/webp'].includes(asset.mime))return null
  const focal=(value?:number)=>Number.isFinite(value)?Math.max(0,Math.min(100,value!)):50
  return <figure className="content-image"><img src={source} srcSet={variants.map(v=>`${v.url} ${v.width}w`).join(', ')} sizes="(max-width: 700px) 100vw, 760px" width={asset.width || variants[variants.length-1].width} height={asset.height || variants[variants.length-1].height} alt={image.alt || ''} loading={priority?'eager':'lazy'} decoding="async" onError={()=>setBroken(true)} style={{objectFit:image.fit==='contain'?'contain':'cover',objectPosition:`${focal(image.focalX)}% ${focal(image.focalY)}%`}} />{image.caption && <figcaption><Markdown text={image.caption} assets={assets} /></figcaption>}</figure>
}
