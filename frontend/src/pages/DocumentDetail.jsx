import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { docs } from '../lib/api'
import { format, parseISO } from 'date-fns'
import './DocumentDetail.css'

const CONF_LABEL = (c, valSeverity) => {
  if (c == null) return { text: '—', cls: 'muted' }
  if (valSeverity === 'error') return { text: `${Math.round(c*100)}%`, cls: 'red' }
  if (valSeverity === 'warning') return { text: `${Math.round(c*100)}%`, cls: 'amber' }
  const p = Math.round(c * 100)
  if (p >= 90) return { text: `${p}%`, cls: 'green' }
  if (p >= 75) return { text: `${p}%`, cls: 'amber' }
  return { text: `${p}%`, cls: 'red' }
}

function ValidationBadge({ flags }) {
  if (!flags || flags.length === 0) return null
  const hasError = flags.some(f => f.severity === 'error')
  return (
    <div className="val-flags">
      {flags.map((f, i) => (
        <div key={i} className={`val-flag ${f.severity}`}>
          <span className="val-icon">{f.severity === 'error' ? '✕' : '⚠'}</span>
          <div className="val-content">
            <span className="val-reason">{f.reason}</span>
            <span className="val-action">→ {f.action}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function FieldRow({ docId, field, onVerified }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(field.field_value || '')
  const [saving, setSaving] = useState(false)
  const [expanded, setExpanded] = useState(
    field.validation_severity === 'error'
  )

  const save = async () => {
    setSaving(true)
    await docs.verifyField(docId, field.id, val)
    setSaving(false)
    setEditing(false)
    onVerified()
  }

  const conf = CONF_LABEL(field.confidence, field.validation_severity)
  const hasFlags = field.validation_flags && field.validation_flags.length > 0
  const isError = field.validation_severity === 'error'
  const isWarning = field.validation_severity === 'warning'

  return (
    <>
      <tr className={`
        ${isError ? 'row-error' : ''}
        ${isWarning && !isError ? 'row-flagged' : ''}
        ${!isError && !isWarning && field.confidence < 0.75 ? 'row-flagged' : ''}
      `}>
        <td className="field-name-cell">
          <div className="field-nm">{field.field_name.replace(/_/g, ' ')}</div>
          {field.page_number && <div className="field-pg">p.{field.page_number}</div>}
          {hasFlags && (
            <button className="expand-btn" onClick={() => setExpanded(e => !e)}>
              {isError ? '✕ ' : '⚠ '}
              {field.validation_flags.length} issue{field.validation_flags.length > 1 ? 's' : ''}
              {expanded ? ' ▴' : ' ▾'}
            </button>
          )}
        </td>
        <td className="field-val-cell">
          {editing ? (
            <input className="field-edit-input" value={val}
              onChange={e => setVal(e.target.value)} autoFocus />
          ) : (
            <span className={field.field_value ? (isError ? 'val-error-text' : '') : 'val-null'}>
              {field.field_value || 'Not found'}
            </span>
          )}
        </td>
        <td>
          <span className={`conf-badge conf-${conf.cls}`}>{conf.text}</span>
        </td>
        <td>
          {field.is_verified ? (
            <span className="verified-mark">✓ Verified</span>
          ) : editing ? (
            <div className="edit-actions">
              <button className="btn-save" onClick={save} disabled={saving}>
                {saving ? '…' : 'Save'}
              </button>
              <button className="btn-cancel" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          ) : (
            <button className={`btn-verify ${isError ? 'btn-verify-error' : ''}`}
              onClick={() => setEditing(true)}>
              {isError ? '✕ Fix required' : isWarning ? '⚠ Review' : 'Verify'}
            </button>
          )}
        </td>
      </tr>
      {hasFlags && expanded && (
        <tr className="val-row">
          <td colSpan={4}>
            <ValidationBadge flags={field.validation_flags} />
          </td>
        </tr>
      )}
    </>
  )
}

export default function DocumentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [doc, setDoc] = useState(null)
  const [fields, setFields] = useState([])
  const [loading, setLoading] = useState(true)
  const [polling, setPolling] = useState(false)
  const [filter, setFilter] = useState('all')

  const load = useCallback(() => {
    Promise.all([docs.get(id), docs.fields(id)]).then(([d, f]) => {
      setDoc(d.data)
      setFields(f.data)
      setLoading(false)
      if (['queued', 'processing'].includes(d.data.status)) setPolling(true)
      else setPolling(false)
    }).catch(() => setLoading(false))
  }, [id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!polling) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [polling, load])

  const reprocess = async () => {
    await docs.reprocess(id)
    setPolling(true)
    load()
  }

  const deleteDoc = async () => {
    if (!confirm('Delete this document?')) return
    await docs.delete(id)
    navigate('/')
  }

  if (loading) return <div className="page"><div className="loading-row">Loading…</div></div>
  if (!doc) return <div className="page"><div className="loading-row">Not found</div></div>

  const isProcessing = ['queued', 'processing'].includes(doc.status)
  const confPct = doc.ai_confidence != null ? Math.round(doc.ai_confidence * 100) : null
  const confColor = confPct == null ? 'muted' : confPct >= 90 ? 'green' : confPct >= 75 ? 'amber' : 'red'

  // Field stats
  const errorFields = fields.filter(f => f.validation_severity === 'error')
  const warnFields = fields.filter(f => f.validation_severity === 'warning')
  const verifiedCount = fields.filter(f => f.is_verified).length
  const lowConfCount = fields.filter(f => !f.is_verified && f.confidence < 0.75
    && f.validation_severity !== 'error' && f.validation_severity !== 'warning').length

  // Filtered fields
  const filteredFields = fields.filter(f => {
    if (filter === 'errors') return f.validation_severity === 'error'
    if (filter === 'warnings') return f.validation_severity === 'warning'
    if (filter === 'flagged') return f.needs_review || f.confidence < 0.75
    return true
  })

  return (
    <div className="page">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>

      <div className="doc-header">
        <div>
          <h1 className="page-title" style={{ fontSize: '1.5rem' }}>{doc.file_name}</h1>
          <div className="doc-meta-row">
            {doc.detected_type && <span className="meta-tag">{doc.detected_type}</span>}
            {doc.extraction_model && <span className="meta-tag mono">{doc.extraction_model}</span>}
            {doc.used_fallback && <span className="meta-tag amber">fallback model</span>}
            {doc.processed_at && (
              <span className="meta-date">
                Processed {format(parseISO(doc.processed_at), 'dd MMM yyyy, HH:mm')}
              </span>
            )}
          </div>
        </div>
        <div className="doc-actions">
          <button className="btn-ghost" onClick={reprocess}>↺ Reprocess</button>
          <button className="btn-ghost danger" onClick={deleteDoc}>Delete</button>
        </div>
      </div>

      {isProcessing && (
        <div className="processing-banner">
          <div className="pulse-dot" />
          Extraction in progress — auto-refreshing every 3 seconds…
        </div>
      )}

      {/* Validation error banner — shown prominently if errors exist */}
      {errorFields.length > 0 && (
        <div className="error-banner">
          <div className="error-banner-icon">✕</div>
          <div>
            <div className="error-banner-title">
              {errorFields.length} validation error{errorFields.length > 1 ? 's' : ''} found
            </div>
            <div className="error-banner-sub">
              {errorFields.map(f => f.field_name.replace(/_/g, ' ')).join(', ')} —
              these fields have impossible or contradictory values and must be corrected before the document can be cleared
            </div>
          </div>
        </div>
      )}

      <div className="doc-summary-grid">
        <div className="summary-card">
          <div className="summary-label">Overall Confidence</div>
          <div className={`summary-val conf-${confColor}`}>
            {confPct != null ? `${confPct}%` : '—'}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Fields Extracted</div>
          <div className="summary-val">{fields.length}</div>
        </div>
        <div className={`summary-card ${errorFields.length > 0 ? 'card-error' : ''}`}>
          <div className="summary-label">Validation Errors</div>
          <div className="summary-val" style={{ color: errorFields.length > 0 ? 'var(--rose)' : 'inherit' }}>
            {errorFields.length}
          </div>
        </div>
        <div className={`summary-card ${warnFields.length > 0 ? 'card-warn' : ''}`}>
          <div className="summary-label">Warnings</div>
          <div className="summary-val" style={{ color: warnFields.length > 0 ? 'var(--amber)' : 'inherit' }}>
            {warnFields.length}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Low Confidence</div>
          <div className="summary-val conf-amber">{lowConfCount}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Verified</div>
          <div className="summary-val conf-green">{verifiedCount}</div>
        </div>
      </div>

      {doc.applicant_name && (
        <div className="applicant-card">
          <div className="applicant-label">Applicant</div>
          <div className="applicant-name">{doc.applicant_name}</div>
          <div className="applicant-meta">
            {doc.applicant_nationality && <span>{doc.applicant_nationality}</span>}
            {doc.passport_number && <span>Passport: {doc.passport_number}</span>}
            {doc.visa_classification && <span>{doc.visa_classification}</span>}
            {doc.employer_name && <span>{doc.employer_name}</span>}
          </div>
        </div>
      )}

      {doc.error_message && (
        <div className="error-card">⚠ {doc.error_message}</div>
      )}

      {fields.length > 0 && (
        <div className="fields-section">
          <div className="section-header">
            <h2 className="section-title">Extracted Fields</h2>
            <div className="filter-tabs">
              {[
                { key: 'all', label: `All (${fields.length})` },
                { key: 'errors', label: `Errors (${errorFields.length})`, color: 'red' },
                { key: 'warnings', label: `Warnings (${warnFields.length})`, color: 'amber' },
                { key: 'flagged', label: `Needs review (${fields.filter(f=>f.needs_review||f.confidence<0.75).length})` },
              ].map(t => (
                <button key={t.key}
                  className={`filter-tab ${filter === t.key ? 'on' : ''} ${t.color || ''}`}
                  onClick={() => setFilter(t.key)}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <table className="fields-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Extracted Value</th>
                <th>Confidence</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredFields.map(f => (
                <FieldRow key={f.id} docId={id} field={f} onVerified={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
