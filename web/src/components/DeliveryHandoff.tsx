import { useState } from 'react'
import { Button } from './ui/button'

export function DeliveryHandoff({ typeKey }: { typeKey: string }) {
  const [notice, setNotice] = useState('')
  const endpoint = new URL('/delivery/graphql', location.origin).href
  const query = `{ entries(typeKey: ${JSON.stringify(typeKey)}, first: 10) { nodes { id slug data } } }`
  const quote = (value: string) => "'" + value.replace(/'/g, "'\\''") + "'"
  const example = `export MOSS_DELIVERY_TOKEN='YOUR_DELIVERY_TOKEN'\ncurl ${quote(endpoint)} \\\n  -H "Authorization: Bearer $MOSS_DELIVERY_TOKEN" \\\n  -H 'Content-Type: application/json' \\\n  --data ${quote(JSON.stringify({ query }))}`
  return <section aria-label="Frontend connection"><h3>Connect your frontend</h3><p>Query published <code>{typeKey}</code> content from your frontend server. Replace the token placeholder with your saved delivery token; keep it out of browser code.</p><pre>{example}</pre><Button type="button" variant="outline" onClick={async () => { try { await navigator.clipboard.writeText(example); setNotice('Integration example copied.') } catch { setNotice('Select and copy the example above.') } }}>Copy integration example</Button>{notice && <p role="status">{notice}</p>}<p>API delivery is verified separately from website display. The example website uses its own workspace and five website types; it does not automatically render this type.</p><details><summary>Run the example website</summary><p>With the CMS running and normal sign-in enabled, run these commands from the repository root. Setup prompts for your administrator email and password.</p><pre>{`python3 example-site/scripts/setup_moss.py\ndocker compose --profile website up --build -d example-site`}</pre><p>Open the example website, select Example website in the CMS, edit a blog post, and publish it. Confirm that the edited text appears on the website.</p></details></section>
}
