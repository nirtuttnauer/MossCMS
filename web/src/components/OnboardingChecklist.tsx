import { useState, useEffect, useId, useRef, type FormEvent } from 'react'
import { Check, CheckCircle2, ArrowRight, ShieldAlert, Sparkles, X } from 'lucide-react'
import { Button } from './ui/button'
import { getContext, gql, rest, message, REQUEST_TIMEOUT_MS, saveContentTypeMutation, type ContentType, type Project } from '../lib/api'
import { toSchema, TYPE_TEMPLATES } from '../lib/fields'
import { contentHash, readContentRoute } from '../lib/navigation'
import { Dialog } from './ui/dialog'
import { DeliveryHandoff } from './DeliveryHandoff'

type Overview = { total: number; published: number; drafts: number; scheduled: number; types: number; assets: number; members: number }

type Props = {
  compact?: boolean
  project: Project
  userId: string
  role: string
  types: ContentType[]
  overview: Overview | null
  onChanged: () => void
}


function getStorage(key: string): string | null {
  try { return window.localStorage?.getItem(key) ?? null } catch { return null }
}
function setStorage(key: string, val: string) {
  try { window.localStorage?.setItem(key, val) } catch {}
}
function removeStorage(key: string) {
  try { window.localStorage?.removeItem(key) } catch {}
}

export function OnboardingChecklist({ compact = false, project, userId, role, types, overview, onChanged }: Props) {
  const dismissKey = `moss-onboarding-dismissed-${userId}-${project.id}`
  const verifyKey = `moss-onboarding-verified-${userId}-${project.id}`
  const generation = useRef(0)
  const summaryId = useId()

  const [dismissed, setDismissed] = useState<boolean>(() => getStorage(dismissKey) === 'true')
  const [verified, setVerified] = useState<boolean>(() => getStorage(verifyKey) === 'true')
  const [tokenInput, setTokenInput] = useState('')
  const [testStatus, setTestStatus] = useState<{ loading: boolean; error?: string; success?: string }>({ loading: false })
  const [creatingTemplate, setCreatingTemplate] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [starterType, setStarterType] = useState(() => getStorage(verifyKey + '-type') || '')
  const [openingDraft, setOpeningDraft] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [newToken, setNewToken] = useState('')
  const [tokenNotice, setTokenNotice] = useState('')
  const nextType = types.find(type => type.key === starterType) || types[0]
  const newEntryHref = contentHash({ ...readContentRoute(), workspace: project.id, type: nextType?.key || '', entry: 'new', field: '', seoSnapshot: '' })

  // Re-sync dismissal and verified status when project changes
  useEffect(() => {
    generation.current += 1
    setDismissed(getStorage(dismissKey) === 'true')
    setVerified(getStorage(verifyKey) === 'true')
    setTokenInput('')
    setTestStatus({ loading: false })
    setError('')
    setStarterType(getStorage(verifyKey + '-type') || '')
    setOpeningDraft(false)
    setExpanded(false)
    setNewToken('')
    setTokenNotice('')
    return () => { generation.current += 1 }
  }, [dismissKey, verifyKey])

  const step1Done = types.length > 0
  const step2Done = (overview?.total ?? 0) > 0
  // Draft saves NEVER satisfy the publish step
  const step3Done = (overview?.published ?? 0) > 0
  const step4Done = verified

  const completedCount = (step1Done ? 1 : 0) + (step2Done ? 1 : 0) + (step3Done ? 1 : 0) + (step4Done ? 1 : 0)
  const allDone = completedCount === 4
  useEffect(() => { if (allDone && !expanded && !newToken) document.getElementById(summaryId)?.focus() }, [allDone, expanded, newToken, summaryId])

  // Single actionable next step
  const activeStep = !step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : !step4Done ? 4 : 5

  const handleDismiss = () => {
    setStorage(dismissKey, 'true')
    setDismissed(true)
  }

  const handleResume = () => {
    removeStorage(dismissKey)
    setDismissed(false)
    setExpanded(true)
  }

  const handleCreateTemplate = async (templateName: string) => {
    if (role !== 'admin' || types.length) return
    const current = generation.current
    const fields = TYPE_TEMPLATES[templateName]
    if (!fields) return
    setCreatingTemplate(templateName)
    setError('')
    try {
      await gql(
        saveContentTypeMutation,
        {
          key: templateName.toLowerCase(),
          name: templateName,
          fields: toSchema(fields),
          version: null,
          migration: {},
        }
      )
      if (generation.current === current) { setStarterType(templateName.toLowerCase()); onChanged() }
    } catch (reason) {
      if (generation.current === current) setError(message(reason))
    } finally {
      if (generation.current === current) setCreatingTemplate(null)
    }
  }

  const openDraft = async () => {
    const current = generation.current
    setOpeningDraft(true)
    setError('')
    try {
      const result = await gql<{ entries: { nodes: { id: string; typeKey: string }[] } }>('{entries(status:"draft",first:2){nodes{id typeKey}}}')
      if (generation.current !== current) return
      const drafts = result.entries.nodes
      if (!drafts.length) throw new Error('No unpublished draft is available. Open Content to choose an entry.')
      location.hash = contentHash({ ...readContentRoute(), workspace: project.id, type: drafts.length === 1 ? drafts[0].typeKey : '', entry: drafts.length === 1 ? drafts[0].id : '', status: drafts.length === 1 ? '' : 'draft', search: '', field: '', seoSnapshot: '' })
    } catch (reason) {
      if (generation.current === current) setError(message(reason))
    } finally {
      if (generation.current === current) setOpeningDraft(false)
    }
  }

  const verifyDelivery = async (cleanToken: string, current: number) => {
    const context = getContext()
    if (!cleanToken) {
      setTestStatus({ loading: false, error: 'Enter a delivery token to test.' })
      return
    }

    setTestStatus({ loading: true })
    try {
      // Never put token in URL or logs. Send via Authorization Bearer header.
      const res = await fetch('/delivery/graphql', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${cleanToken}`,
        },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        body: JSON.stringify({
          query: '{ entries(first: 1) { nodes { id slug } } }',
        }),
      })
      if (generation.current !== current) return

      if (!res.ok) {
        const errJson = await res.json().catch(() => null)
        const errMsg = errJson?.detail || `HTTP ${res.status}: Delivery query rejected.`
        setTestStatus({ loading: false, error: errMsg })
        return
      }

      const json = await res.json()
      if (generation.current !== current) return
      if (json.errors && json.errors.length > 0) {
        setTestStatus({
          loading: false,
          error: json.errors.map((e: { message: string }) => e.message).join('; '),
        })
        return
      }

      const delivered = json.data?.entries?.nodes?.[0]
      if (!delivered?.id) {
        setTestStatus({
          loading: false,
          error: 'No published entry was returned. Publish an entry and check that the token permits its content type.',
        })
        return
      }
      const editorial = await gql<{ entry: { id: string; isLive: boolean; typeKey?: string } | null }>(
        'query($id:ID!){entry(id:$id){id isLive typeKey}}', { id: delivered.id }, context
      )
      if (generation.current !== current) return
      if (!editorial.entry?.isLive) throw new Error('Use a delivery token for this workspace and a currently published entry.')
      if (editorial.entry.typeKey) { setStarterType(editorial.entry.typeKey); setStorage(verifyKey + '-type', editorial.entry.typeKey) }

      // Successful verification
      setStorage(verifyKey, 'true')
      setVerified(true)
      setTokenInput('')
      setTestStatus({
        loading: false,
        success: 'Verified! Delivery endpoint returned published entries securely.',
      })
      onChanged()
    } catch (reason) {
      if (generation.current !== current) return
      setTestStatus({
        loading: false,
        error: `Connection error: ${reason instanceof Error ? reason.message : 'failed to reach delivery endpoint'}`,
      })
    }
  }

  const handleTestDelivery = (e: FormEvent) => {
    e.preventDefault()
    return verifyDelivery(tokenInput.trim(), generation.current)
  }

  const createAndVerify = async () => {
    if (role !== 'admin' || !nextType || testStatus.loading) return
    const current = generation.current
    setTestStatus({ loading: true })
    try {
      const result = await rest<{ token: string }>('/api/tokens', 'POST', { name: `${nextType.name} frontend`, days: 90, scopes: [nextType.key] })
      if (generation.current !== current) return
      setNewToken(result.token)
      setTokenNotice('')
      await verifyDelivery(result.token, current)
    } catch (reason) {
      if (generation.current === current) setTestStatus({ loading: false, error: message(reason) })
    }
  }

  const tokenDialog = newToken && <Dialog title="Save your delivery token" open onClose={() => setNewToken('')}><p>This token reads only {nextType?.name} content and expires in 90 days. Copy it to your frontend server’s private environment before closing; it will not be shown again.</p><label>New delivery token<input type="password" readOnly value={newToken} autoComplete="off" /></label><Button type="button" onClick={async () => { try { await navigator.clipboard.writeText(newToken); setTokenNotice('Token copied.') } catch { setTokenNotice('Select and copy the token above.') } }}>Copy token</Button>{tokenNotice && <p role="status">{tokenNotice}</p>}{testStatus.error && <p role="alert">{testStatus.error}</p>}<Button type="button" variant="outline" onClick={() => setNewToken('')}>I saved this token</Button></Dialog>

  if (dismissed || (allDone || compact) && !expanded) {
    return (
      <div className="onboarding-resumer" aria-label="Onboarding checklist">
        <Button
          id={summaryId}
          type="button"
          variant="outline"
          onClick={handleResume}
          aria-label="Resume getting started guide"
        >
          <Sparkles size={14} className="mr-1" />
          {allDone ? 'Workspace ready! — Connection details' : `Setup checklist (${completedCount}/4)`}
        </Button>
        {allDone && <><p className="notice" role="status">Delivery verified: published content is available through the API. <span>Verified securely</span></p><Button type="button" variant="ghost" onClick={() => { removeStorage(verifyKey); removeStorage(dismissKey); setVerified(false); setDismissed(false) }}>Test another token</Button></>}
        {tokenDialog}
      </div>
    )
  }

  return (
    <section
      className="onboarding-card plain-card"
      aria-labelledby="onboarding-heading"
      data-testid="onboarding-checklist"
    >
      <div className="onboarding-header">
        <div>
          <div className="eyebrow">
            <Sparkles size={13} aria-hidden="true" />
            <span>GETTING STARTED</span>
          </div>
          <h2 id="onboarding-heading">
            {allDone ? 'Workspace ready!' : 'First published entry checklist'}
          </h2>
          <p className="subtitle">
            {allDone
              ? 'You completed the path from content modeling to live delivery verification.'
              : `Follow these 4 steps to set up and verify content delivery in ${project.name}.`}
          </p>
        </div>
        <div className="onboarding-actions">
          <span className="onboarding-badge" aria-label={`Progress: ${completedCount} of 4 steps completed`}>
            {completedCount} / 4 completed
          </span>
          <Button
            type="button"
            variant="ghost"
              onClick={handleDismiss}
            aria-label="Dismiss checklist"
            title="Dismiss checklist"
          >
            <X size={16} />
          </Button>
        </div>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <ol className="onboarding-steps" role="list">
        {/* Step 1: Content Type */}
        <li
          className={`onboarding-step ${step1Done ? 'done' : activeStep === 1 ? 'active' : 'upcoming'}`}
          aria-current={activeStep === 1 ? 'step' : undefined}
        >
          <div className="step-indicator" aria-hidden="true">
            {step1Done ? <CheckCircle2 size={20} className="step-icon-done" /> : <span className="step-num">1</span>}
          </div>
          <div className="step-content">
            <div className="step-title-row">
              <h3>Choose or define a content type</h3>
              {step1Done && <span className="step-status done">Completed ({types.length} defined)</span>}
            </div>
            <p>
              Content types define the schema and fields for your entries. Existing types satisfy this step.
            </p>
            {!step1Done && (
              <div className="step-actions">
                {role !== 'admin' ? (
                  <p className="step-role-note">
                    <ShieldAlert size={14} /> {role === 'reader' ? 'Readers cannot create content types.' : 'Editors cannot create content types.'} Ask an administrator to define a type.
                  </p>
                ) : (
                  <>
                    <div className="template-buttons" role="group" aria-label="Starter templates">
                      <span className="text-sm muted">Quick start:</span>
                      {Object.keys(TYPE_TEMPLATES).map(tmpl => (
                        <Button
                          key={tmpl}
                          type="button"
                          variant="outline"
                                          disabled={Boolean(creatingTemplate)}
                          onClick={() => handleCreateTemplate(tmpl)}
                        >
                          {creatingTemplate === tmpl ? `Creating ${tmpl}…` : `Add ${tmpl}`}
                        </Button>
                      ))}
                    </div>
                    <div className="custom-action">
                      <a href="#types" className="button button-outline button-sm">
                        Design custom type <ArrowRight size={14} />
                      </a>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </li>

        {/* Step 2: Create Entry */}
        <li
          className={`onboarding-step ${step2Done ? 'done' : activeStep === 2 ? 'active' : 'upcoming'}`}
          aria-current={activeStep === 2 ? 'step' : undefined}
        >
          <div className="step-indicator" aria-hidden="true">
            {step2Done ? <CheckCircle2 size={20} className="step-icon-done" /> : <span className="step-num">2</span>}
          </div>
          <div className="step-content">
            <div className="step-title-row">
              <h3>Draft your first entry</h3>
              {step2Done && <span className="step-status done">Completed ({overview?.total} entries)</span>}
            </div>
            <p>
              Create an entry with your structured content. You can write, preview, and autosave drafts safely.
            </p>
            {!step2Done && activeStep === 2 && (
              <div className="step-actions">
                {role === 'reader' ? (
                  <p className="step-role-note">
                    <ShieldAlert size={14} /> Readers cannot create entries.
                  </p>
                ) : (
                  <>
                    {types.length > 1 && <label>Content type<select value={nextType?.key || ''} onChange={event => setStarterType(event.target.value)}>{types.map(type => <option key={type.key} value={type.key}>{type.name}</option>)}</select></label>}
                    <a href={newEntryHref} className="button button-sm">Create your first {nextType?.name || 'entry'} <ArrowRight size={14} /></a>
                  </>
                )}
              </div>
            )}
          </div>
        </li>

        {/* Step 3: Publish Entry */}
        <li
          className={`onboarding-step ${step3Done ? 'done' : activeStep === 3 ? 'active' : 'upcoming'}`}
          aria-current={activeStep === 3 ? 'step' : undefined}
        >
          <div className="step-indicator" aria-hidden="true">
            {step3Done ? <CheckCircle2 size={20} className="step-icon-done" /> : <span className="step-num">3</span>}
          </div>
          <div className="step-content">
            <div className="step-title-row">
              <h3>Publish an entry</h3>
              {step3Done && <span className="step-status done">Completed ({overview?.published} published)</span>}
            </div>
            <p>
              Editorial draft saves remain private. Publishing makes the entry accessible to your delivery tokens and frontends.
            </p>
            {!step3Done && activeStep === 3 && (
              <div className="step-actions">
                {role === 'reader' ? (
                  <p className="step-role-note">
                    <ShieldAlert size={14} /> Readers cannot publish entries.
                  </p>
                ) : (
                  <div>
                    <Button type="button" disabled={openingDraft} onClick={openDraft}>{openingDraft ? 'Opening…' : 'Open a draft to publish'} <ArrowRight size={14} /></Button>
                    {overview?.drafts ? (
                      <small className="block mt-1 muted">
                        You have {overview.drafts} unpublished draft(s). Draft saves do not satisfy publication.
                      </small>
                    ) : null}
                  </div>
                )}
              </div>
            )}
          </div>
        </li>

        {/* Step 4: Verify Delivery Query */}
        <li
          className={`onboarding-step ${step4Done ? 'done' : activeStep === 4 ? 'active' : 'upcoming'}`}
          aria-current={activeStep === 4 ? 'step' : undefined}
        >
          <div className="step-indicator" aria-hidden="true">
            {step4Done ? <CheckCircle2 size={20} className="step-icon-done" /> : <span className="step-num">4</span>}
          </div>
          <div className="step-content">
            <div className="step-title-row">
              <h3>Verify delivery query with a delivery token</h3>
              {step4Done && <span className="step-status done">Verified securely</span>}
            </div>
            <p>
              Delivery tokens provide read-only access to published content without granting administrative permissions.
              Verify your delivery endpoint with a token to confirm your website will connect.
            </p>
            {!step4Done && activeStep === 4 && (
              <div className="step-actions">
                {role === 'admin' && (
                  <div className="step-help">{types.length > 1 && <label>Frontend content type<select value={nextType?.key || ''} onChange={event => setStarterType(event.target.value)}>{types.map(type => <option key={type.key} value={type.key}>{type.name}</option>)}</select></label>}<p>Create a token for {nextType?.name} and verify delivery here. It expires in 90 days.</p><Button type="button" disabled={testStatus.loading || !nextType} onClick={createAndVerify}>{testStatus.loading ? 'Verifying…' : 'Create token & verify delivery'}</Button><p>Already have a token? Paste it below. Manage tokens in <a href={`#settings?workspace=${encodeURIComponent(project.id)}&section=delivery-tokens`}>Settings &rarr; Delivery tokens</a>.</p></div>
                )}
                {role !== 'admin' && (
                  <p className="step-role-note">
                    <ShieldAlert size={14} /> Delivery tokens are generated by administrators in Settings. You can test a token provided by your admin below.
                  </p>
                )}
                <form className="delivery-test-form inline-form" onSubmit={handleTestDelivery}>
                  <input
                    type="password"
                    aria-label="Delivery token"
                    placeholder="Paste delivery token"
                    value={tokenInput}
                    onChange={e => setTokenInput(e.target.value)}
                    required
                    autoComplete="off"
                  />
                  <Button type="submit" disabled={testStatus.loading}>
                    {testStatus.loading ? 'Testing…' : 'Test delivery query'}
                  </Button>
                  <a href="#explorer" className="button button-outline">
                    Explore API schema
                  </a>
                </form>
                {testStatus.error && (
                  <p className="form-error" role="alert">
                    {testStatus.error}
                  </p>
                )}
                {testStatus.success && (
                  <p className="notice" role="status">
                    {testStatus.success}
                  </p>
                )}
              </div>
            )}
            {step4Done && (
              <div className="verified-summary">
                <p className="notice" role="status">
                  <Check size={14} /> Delivery verified: <code>/delivery/graphql</code> successfully returns published content.
                </p>
                <div className="inline-form">
                  <a href="#explorer" className="button button-outline button-sm">
                    Open API explorer
                  </a>
                  <Button
                    type="button"
                    variant="ghost"
                              onClick={() => {
                      removeStorage(verifyKey)
                      setVerified(false)
                    }}
                  >
                    Test another token
                  </Button>
                </div>
                <DeliveryHandoff typeKey={nextType?.key || ''} />
              </div>
            )}
          </div>
        </li>
      </ol>
      {tokenDialog}
    </section>
  )
}
