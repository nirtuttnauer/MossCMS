import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import { markdownUrl, type MarkdownAsset } from '../../../shared/markdown.mjs'
import '../../../shared/markdown.css'
export function Markdown({text,assets=[]}:{text:string;assets?:MarkdownAsset[]}) {
  return <div className="markdown-content"><ReactMarkdown skipHtml remarkPlugins={[remarkBreaks]} urlTransform={markdownUrl(assets)} components={{img:({src,alt}) => src ? <img src={src} alt={alt || ''} loading="lazy" /> : <span role="img" aria-label={alt || 'Unavailable image'}>[Image unavailable: {alt}]</span>}}>{text}</ReactMarkdown></div>
}
