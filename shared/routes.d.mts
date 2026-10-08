type Page = {slug:string;kind?:string;aliases?:string[]}
export function pagePath(page:Page):string
export function routeSlug(path:string):string|null
export function routePage<T extends Page>(pages:T[],path:string):T|undefined
