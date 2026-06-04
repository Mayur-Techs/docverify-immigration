import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { docs } from '../lib/api'
import { format, parseISO } from 'date-fns'
import './DocumentDetail.css'

const CONF_LABEL = (c) => {
  if (c == null) return { text: '—', cls: 'muted' }
  const p = Math.round(c * 100)
  if (p >= 90) return { text: `${p}%`, cls: 'green' }
  if (p >= 75) return { text: `${p}%`, cls: 'amber' }
  return { text: `${p}%`, cls: 'red' }
}

function FieldRow({ docId, field, onVerified }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(field.field_value || '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await docs.verifyField(docId, field.id, val)
    setSaving(false)
    setEditing(false)
    onVerified()
  }

  const conf = CONF_LABEL(field.confidence)

  return (
    <tr className={field.confidence < 0.75 && !field.is_verified ? 'row-flagged' : ''}>
      <td className="field-name-cell">
        <div className="field-nm">{field.field_name.replace(/_/g, ' ')}</div>
        {field.page_number && <div className="field-pg">p.{field.page_number}</div>}
      </td>
      <td className="field-val-cell">
        {editing ? (
          <input className="field-edit-input" value={val} onChange={e => setVal(e.target.value)} autoFocus />
        ) : (
          <span className={field.field_value ? '' : 'val-null'}>
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
            <button className="btn-save" onClick={save} disabled={saving}>{saving ? '…' : 'Save'}</button>
            <button className="btn-cancel" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        ) : (
          <button className="btn-verify" onClick={() => setEditing(true)}>Verify</button>
        )}
      </td>
    </tr>
  )
}

export default function DocumentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [doc, setDoc] = useState(null)
  const [fields, setFields] = useState([])
  const [loading, setLoading] = useState(true)
  const [polling, setPolling] = useState(false)

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
  const flaggedCount = fields.filter(f => !f.is_verified && f.confidence < 0.75).length
  const verifiedCount = fields.filter(f => f.is_verified).length

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

      <div className="doc-summary-grid">
        <div className="summary-card">
          <div className="summary-label">Overall Confidence</div>
          <div className={`summary-val conf-${confColor}`}>
            {confPct != null ? `${confPct}%` : '—'}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Status</div>
          <div className="summary-val">{doc.status}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Fields Extracted</div>
          <div className="summary-val">{fields.length}</div>
        </div>
        <div className="summary-card">
          <div className="summary-label">Verified / Flagged</div>
          <div className="summary-val">{verifiedCount} / <span className="conf-red">{flaggedCount}</span></div>
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
            {flaggedCount > 0 && (
              <span className="flag-count">⚑ {flaggedCount} field{flaggedCount > 1 ? 's' : ''} need verification</span>
            )}
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
              {fields.map(f => (
                <FieldRow key={f.id} docId={id} field={f} onVerified={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
