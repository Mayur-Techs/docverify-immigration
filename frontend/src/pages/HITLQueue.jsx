import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { docs } from '../lib/api'
import { format, parseISO } from 'date-fns'
import './HITLQueue.css'

const PRIORITY_META = {
  critical: { color: '#c93d3d', bg: 'rgba(201,61,61,0.12)', label: 'Critical' },
  high:     { color: '#c97c2d', bg: 'rgba(201,124,45,0.12)', label: 'High' },
  medium:   { color: '#c9a84c', bg: 'rgba(201,168,76,0.12)', label: 'Medium' },
  low:      { color: '#6b7db3', bg: 'rgba(107,125,179,0.12)', label: 'Low' },
}

export default function HITLQueue() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(null)
  const [notes, setNotes] = useState({})

  const load = () => {
    docs.hitlQueue().then(r => {
      setItems(r.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const resolve = async (id) => {
    setResolving(id)
    await docs.resolveHitl(id, notes[id] || null)
    setResolving(null)
    load()
  }

  const parseFlags = (raw) => {
    try { return JSON.parse(raw || '[]') } catch { return [] }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="page-sub">Documents that scored below the confidence threshold — requiring human verification</p>
        </div>
        <div className="queue-count-badge">
          {items.length} item{items.length !== 1 ? 's' : ''} pending
        </div>
      </div>

      {loading ? (
        <div className="loading-row">Loading queue…</div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">✓</div>
          <p>Queue is clear — all documents verified</p>
        </div>
      ) : (
        <div className="hitl-list">
          {items.map(item => {
            const meta = PRIORITY_META[item.priority] || PRIORITY_META.medium
            const flags = parseFlags(item.flagged_fields)
            const confPct = item.overall_confidence != null
              ? Math.round(item.overall_confidence * 100) : null

            return (
              <div key={item.id} className="hitl-card">
                <div className="hitl-card-top">
                  <div className="hitl-left">
                    <div className="hitl-header-row">
                      <span className="priority-badge"
                        style={{ color: meta.color, background: meta.bg }}>
                        ⚑ {meta.label}
                      </span>
                      {confPct != null && (
                        <span className="hitl-conf" style={{
                          color: confPct < 55 ? '#c93d3d' : confPct < 75 ? '#c97c2d' : '#6b7db3'
                        }}>
                          {confPct}% confidence
                        </span>
                      )}
                      <span className="hitl-date">
                        {format(parseISO(item.created_at), 'dd MMM yyyy, HH:mm')}
                      </span>
                    </div>

                    <div className="hitl-reason">{item.reason}</div>

                    {flags.length > 0 && (
                      <div className="flagged-fields">
                        <span className="flagged-label">Flagged fields:</span>
                        {flags.map(f => (
                          <span key={f} className="flagged-tag">
                            {f.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="hitl-actions">
                    <Link to={`/documents/${item.document_id}`} className="btn-review">
                      Review document →
                    </Link>
                  </div>
                </div>

                <div className="hitl-resolve-row">
                  <input
                    className="notes-input"
                    placeholder="Resolution notes (optional)…"
                    value={notes[item.id] || ''}
                    onChange={e => setNotes(n => ({ ...n, [item.id]: e.target.value }))}
                  />
                  <button
                    className="btn-resolve"
                    onClick={() => resolve(item.id)}
                    disabled={resolving === item.id}>
                    {resolving === item.id ? 'Resolving…' : 'Mark resolved'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="hitl-explainer">
        <h3>How HITL routing works</h3>
        <div className="explainer-grid">
          <div className="explainer-item">
            <div className="explainer-dot green" />
            <div>
              <strong>≥ 90% confidence</strong>
              <p>Fields auto-verified. No action needed.</p>
            </div>
          </div>
          <div className="explainer-item">
            <div className="explainer-dot amber" />
            <div>
              <strong>75–89% confidence</strong>
              <p>Document completed but fields flagged for spot-check.</p>
            </div>
          </div>
          <div className="explainer-item">
            <div className="explainer-dot red" />
            <div>
              <strong>Below 75% confidence</strong>
              <p>Document held here. A reviewer must verify before it's cleared.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
