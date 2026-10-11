import { useState } from 'react'
import { AssetPicker } from './AssetPicker'
import { MarkdownInput } from './MarkdownInput'
import { ReferencePicker } from './ReferencePicker'
import { Button } from './ui/button'
import { initialValue } from '../lib/fields'
import { LOCALE_PATTERN } from '../lib/locales'
import type { Asset, Entry, Field } from '../lib/api'

type Props = {
  field: Field
  value: unknown
  onChange: (value: unknown) => void
  references: Entry[]
  assets: Asset[]
  projectId?: string
  editable?: boolean
  defaultLocale?: string
  locales?: string[]
  path?: string
  errors?: Record<string, string>
  onClearError?: (path: string, descendants?: boolean) => void
}

export const fieldInputId = (path: string) => `field-${encodeURIComponent(path)}`

export function FieldInput({ field, value, onChange, references, assets, path, errors, onClearError, projectId, editable = false, defaultLocale = 'en', locales = ['en'] }: Props) {
  const [newLocale, setNewLocale] = useState('')
  const [localeError, setLocaleError] = useState('')
  const label = field.label || field.name || 'Item'
  const currentPath = path || `data.${field.name}`
  const inputId = fieldInputId(currentPath)
  const fieldError = errors?.[currentPath]
  const object = (value && typeof value === 'object' && !Array.isArray(value) ? value : {}) as Record<string, unknown>

  const errorId = `error-${inputId}`
  const childProps = { projectId, editable, defaultLocale, locales, errors, onClearError }
  const clear = (descendants = false) => onClearError?.(currentPath, descendants)

  if (field.localized) {
    return (
      <fieldset className="field-group" id={inputId} tabIndex={-1} aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? errorId : undefined}>
        <legend>{label}{field.required ? ' *' : ''}</legend>
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
        {Object.entries(object).map(([locale, translation]) => {
          const locPath = `${currentPath}.${locale}`
          return (
            <div key={locale} className="locale-field">
              <FieldInput
                field={{ ...field, localized: false, label: locale }}
                value={translation}
                onChange={next => {
                  onClearError?.(locPath)
                  clear()
                  onChange({ ...object, [locale]: next })
                }}
                references={references}
                assets={assets}
                path={locPath}
                {...childProps}
              />
              <button
                type="button"
                aria-label={`Remove ${locale} translation`}
                onClick={() => {
                  const next = { ...object }
                  delete next[locale]
                  clear()
                  onClearError?.(locPath, true)
                  onChange(next)
                }}
              >
                ×
              </button>
            </div>
          )
        })}
        <p className="field-help">Suggested locales present: {locales.filter(locale => locale in object).join(', ') || 'none'}. Missing: {locales.filter(locale => !(locale in object)).join(', ') || 'none'}.</p>
        <div className="inline-form">
          <label htmlFor={`${inputId}-suggested-locale`}>Suggested locale</label>
          <select id={`${inputId}-suggested-locale`} aria-label={`Suggested locale for ${label}`} value={locales.includes(newLocale) && !(newLocale in object) ? newLocale : ''} onChange={event => { setNewLocale(event.target.value); setLocaleError('') }}>
            <option value="">Choose locale…</option>
            {locales.filter(locale => !(locale in object)).map(locale => <option key={locale} value={locale}>{locale}</option>)}
          </select>
          <label htmlFor={`${inputId}-locale`}>Locale code</label>
          <input
            id={`${inputId}-locale`}
            aria-label={`New locale for ${label}`}
            placeholder={defaultLocale}
            value={newLocale}
            dir="ltr"
            aria-invalid={Boolean(localeError)}
            aria-describedby={localeError ? `${inputId}-locale-error` : undefined}
            onChange={e => { setNewLocale(e.target.value); setLocaleError('') }}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const locale = newLocale.trim()
              if (!LOCALE_PATTERN.test(locale)) {
                setLocaleError('Use a locale code such as en, he or pt-BR.')
              } else if (locale in object) {
                setLocaleError(`${locale} already has a translation.`)
              } else {
                clear()
                onChange({ ...object, [locale]: initialValue({ ...field, localized: false }, defaultLocale) })
                setNewLocale('')
                setLocaleError('')
              }
            }}
          >
            Add locale
          </Button>
        </div>
        {localeError && <p id={`${inputId}-locale-error`} role="alert">{localeError}</p>}
      </fieldset>
    )
  }

  if (field.type === 'object') {
    return (
      <fieldset className="field-group" id={inputId} tabIndex={-1} aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? errorId : undefined}>
        <legend>{label}</legend>
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
        {field.fields?.map(child => {
          const childPath = `${currentPath}.${child.name}`
          return (
            <FieldInput
              key={child.name}
              field={child}
              value={object[child.name]}
              onChange={next => {
                onClearError?.(childPath)
                clear()
                onChange({ ...object, [child.name]: next })
              }}
              references={references}
              assets={assets}
              path={childPath}
              {...childProps}
            />
          )
        })}
      </fieldset>
    )
  }

  if (field.type === 'list') {
    const items = Array.isArray(value) ? value : []
    return (
      <fieldset className="field-group" id={inputId} tabIndex={-1} aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? errorId : undefined}>
        <legend>{label}</legend>
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
        {items.map((item, i) => {
          const itemPath = `${currentPath}[${i}]`
          return (
            <div className="list-item" key={i}>
              <FieldInput
                field={{ ...field.item!, name: `${label} ${i + 1}` }}
                value={item}
                onChange={next => {
                  onClearError?.(itemPath)
                  clear()
                  onChange(items.map((old, index) => (index === i ? next : old)))
                }}
                references={references}
                assets={assets}
                path={itemPath}
                {...childProps}
              />
              {[-1, 1].map(direction => (
                <Button
                  type="button"
                  variant="outline"
                  key={direction}
                  disabled={i + direction < 0 || i + direction >= items.length}
                  aria-label={`Move ${label} item ${i + 1} ${direction < 0 ? 'up' : 'down'}`}
                  onClick={() => {
                    const next = [...items]
                    ;[next[i], next[i + direction]] = [next[i + direction], next[i]]
                    clear(true)
                    onChange(next)
                  }}
                >
                  {direction < 0 ? 'Move up' : 'Move down'}
                </Button>
              ))}
              <button
                type="button"
                aria-label={`Remove ${label} item ${i + 1}`}
                onClick={() => {
                  clear(true)
                  onChange(items.filter((_, index) => i !== index))
                }}
              >
                ×
              </button>
            </div>
          )
        })}
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            clear(true)
            onChange([...items, initialValue(field.item || { name: '', type: 'text' }, defaultLocale)])
          }}
        >
          Add item
        </Button>
      </fieldset>
    )
  }

  if (field.type === 'boolean') {
    return (
      <div className="field-control"><label className="checkbox-label" htmlFor={inputId}>
        <input
          id={inputId}
          type="checkbox"
          checked={value === true}
          aria-invalid={Boolean(fieldError)}
          aria-describedby={fieldError ? `error-${inputId}` : undefined}
          onChange={e => {
            clear()
            onChange(e.target.checked)
          }}
        />
        {label}{field.required ? ' *' : ''}
      </label>
        {fieldError && <span id={`error-${inputId}`} className="field-error" role="alert">{fieldError}</span>}</div>
    )
  }

  if (field.type === 'richText') {
    return (
      <div>
        <MarkdownInput
          label={label}
          id={inputId}
          error={fieldError}
          projectId={projectId}
          editable={editable}
          value={String(value ?? '')}
          required={field.required}
          onChange={val => {
            clear()
            onChange(val)
          }}
          assets={assets}
        />
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
      </div>
    )
  }

  if (field.type === 'asset') {
    return (
      <div>
        <AssetPicker
          label={label}
          id={inputId}
          error={fieldError}
          projectId={projectId}
          editable={editable}
          value={String(value || '')}
          onChange={val => {
            clear()
            onChange(val)
          }}
          imagesOnly={field.imageOnly}
        />
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
      </div>
    )
  }

  if (field.type === 'reference') {
    return (
      <div>
        <ReferencePicker
          label={label}
          id={inputId}
          error={fieldError}
          projectId={projectId}
          editable={editable}
          value={String(value || '') || null}
          onChange={val => {
            clear()
            onChange(val)
          }}
          target={field.target}
          required={field.required}
          initialReferences={references}
        />
        {fieldError && <span id={errorId} className="field-error" role="alert">{fieldError}</span>}
      </div>
    )
  }

  if (field.type === 'enum') {
    const options = field.options?.map(v => ({ id: v, name: v }))
    return (
      <div className="field-control"><label htmlFor={inputId}>
        {label}{field.required ? ' *' : ''}
        <select
          id={inputId}
          value={String(value ?? '')}
          required={field.required}
          aria-invalid={Boolean(fieldError)}
          aria-describedby={fieldError ? `error-${inputId}` : undefined}
          onChange={e => {
            clear()
            onChange(e.target.value || null)
          }}
        >
          <option value="">Select…</option>
          {options?.map(option => (
            <option key={option.id} value={option.id}>{option.name}</option>
          ))}
        </select>
      </label>
        {fieldError && <span id={`error-${inputId}`} className="field-error" role="alert">{fieldError}</span>}</div>
    )
  }

  return (
    <div className="field-control"><label htmlFor={inputId}>
      {label}{field.required ? ' *' : ''}
      <input
        id={inputId}
        type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}
        min={field.name === 'focalX' || field.name === 'focalY' ? 0 : undefined}
        max={field.name === 'focalX' || field.name === 'focalY' ? 100 : undefined}
        step={field.type === 'number' ? 'any' : undefined}
        required={field.required}
        dir={field.type === 'text' ? 'auto' : 'ltr'}
        value={String(value ?? '')}
        aria-invalid={Boolean(fieldError)}
        aria-describedby={fieldError ? `error-${inputId}` : undefined}
        onChange={e => {
          clear()
          onChange(field.type === 'number' ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)
        }}
      />
    </label>
      {fieldError && <span id={`error-${inputId}`} className="field-error" role="alert">{fieldError}</span>}</div>
  )
}
