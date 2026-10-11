import { useState, useEffect, useRef, type FormEvent } from 'react'
import { Check, CheckCircle2, ArrowRight, ShieldAlert, Sparkles, X } from 'lucide-react'
import { Button } from './ui/button'
import { getContext, gql, message, REQUEST_TIMEOUT_MS, saveContentTypeMutation, type ContentType, type Project } from '../lib/api'
import { toSchema, TYPE_TEMPLATES } from '../lib/fields'

type Overview = { total: number; published: number; drafts: number; scheduled: number; types: number; assets: number; members: number }

type Props = {
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

export function OnboardingChecklist({ project, userId, role, types, overview, onChanged }: Props) {
  const dismissKey = `moss-onboarding-dismissed-${userId}-${project.id}`
  const verifyKey = `moss-onboarding-verified-${userId}-${project.id}`
  const generation = useRef(0)

  const [dismissed, setDismissed] = useState<boolean>(() => getStorage(dismissKey) === 'true')
  const [verified, setVerified] = useState<boolean>(() => getStorage(verifyKey) === 'true')
  const [tokenInput, setTokenInput] = useState('')
  const [testStatus, setTestStatus] = useState<{ loading: boolean; error?: string; success?: string }>({ loading: false })
  const [creatingTemplate, setCreatingTemplate] = useState<string | null>(null)
  const [error, setError] = useState('')

  // Re-sync dismissal and verified status when project changes
  useEffect(() => {
    generation.current += 1
    setDismissed(getStorage(dismissKey) === 'true')
    setVerified(getStorage(verifyKey) === 'true')
    setTokenInput('')
    setTestStatus({ loading: false })
    setError('')
    return () => { generation.current += 1 }
  }, [dismissKey, verifyKey])

  const step1Done = types.length > 0
  const step2Done = (overview?.total ?? 0) > 0
  // Draft saves NEVER satisfy the publish step
  const step3Done = (overview?.published ?? 0) > 0
  const step4Done = verified

  const completedCount = (step1Done ? 1 : 0) + (step2Done ? 1 : 0) + (step3Done ? 1 : 0) + (step4Done ? 1 : 0)
  const allDone = completedCount === 4

  // Single actionable next step
  const activeStep = !step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : !step4Done ? 4 : 5

  const handleDismiss = () => {
    setStorage(dismissKey, 'true')
    setDismissed(true)
  }

  const handleResume = () => {
    removeStorage(dismissKey)
    setDismissed(false)
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
      if (generation.current === current) onChanged()
    } catch (reason) {
      if (generation.current === current) setError(message(reason))
    } finally {
      if (generation.current === current) setCreatingTemplate(null)
    }
  }

  const handleTestDelivery = async (e: FormEvent) => {
    e.preventDefault()
    const current = generation.current
    const context = getContext()
    const cleanToken = tokenInput.trim()
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
      const editorial = await gql<{ entry: { id: string; isLive: boolean } | null }>(
        'query($id:ID!){entry(id:$id){id isLive}}', { id: delivered.id }, context
      )
      if (generation.current !== current) return
      if (!editorial.entry?.isLive) throw new Error('Use a delivery token for this workspace and a currently published entry.')

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

  if (dismissed) {
    return (
      <div className="onboarding-resumer" aria-label="Onboarding checklist">
        <Button
          type="button"
          variant="outline"
          onClick={handleResume}
          aria-label="Resume getting started guide"
        >
          <Sparkles size={14} className="mr-1" />
          Setup checklist ({completedCount}/4)
        </Button>
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
                  <a href="#content" className="button button-sm">
                    Go to Content to draft an entry <ArrowRight size={14} />
                  </a>
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
                    <a href="#content" className="button button-sm">
                      Open Content and publish <ArrowRight size={14} />
                    </a>
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
                  <p className="step-help">
                    Create or manage delivery tokens in <a href="#settings">Settings &rarr; Delivery tokens</a>, then paste a token below to verify.
                  </p>
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
              </div>
            )}
          </div>
        </li>
      </ol>
    </section>
  )
}
