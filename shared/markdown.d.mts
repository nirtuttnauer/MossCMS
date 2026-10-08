export type MarkdownAsset = {id:string; mime:string; url:string}
export function markdownUrl(assets?: MarkdownAsset[]): (raw:string,key:string)=>string
