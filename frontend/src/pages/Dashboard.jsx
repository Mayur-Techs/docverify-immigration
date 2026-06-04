import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { docs } from '../lib/api'
import { useAuth } from '../store/auth'
import { format, parseISO } from 'date-fns'
import './Dashboard.css'

const STATUS_META = {
  completed:     { label: 'Verified',    color: '#2d7a5f', bg: 'rgba(45,122,95,0.12)' },
  hitl_pending:  { label: 'Review',      color: '#c97c2d', bg: 'rgba(201,124,45,0.12)' },
  hitl_resolved: { label: 'Resolved',    color: '#4a9d7e', bg: 'rgba(74,157,126,0.12)' },
  processing:    { label: 'Processing',  color: '#6b7db3', bg: 'rgba(107,125,179,0.12)' },
  queued:        { label: 'Queued',      color: '#6b6b80', bg: 'rgba(107,107,128,0.12)' },
  failed:        { label: 'Failed',      color: '#c93d3d', bg: 'rgba(201,61,61,0.12)' },
}

function ConfBar({ value }) {
  if (value == null) return <span className="conf-na">—</span>
  const pct = Math.round(value * 100)
  const color = pct >= 90 ? '#2d7a5f' : pct >= 75 ? '#c97c2d' : '#c93d3d'
  return (
    <div className="conf-bar-wrap">
      <div className="conf-bar-bg">
        <div className="conf-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="conf-pct" style={{ color }}>{pct}%</span>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [stats, setStats] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([docs.stats(), docs.list({ limit: 20 })]).then(([s, d]) => {
      setStats(s.data)
      setDocuments(d.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {user?.firm_name ? `${user.firm_name}` : 'Overview'}
          </h1>
          <p className="page-sub">Document extraction workspace</p>
        </div>
        <Link to="/upload" className="btn-primary">⊕ Upload Document</Link>
      </div>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-num">{stats.total}</div>
            <div className="stat-label">Documents processed</div>
          </div>
          <div className="stat-card accent-green">
            <div className="stat-num">{stats.completed}</div>
            <div className="stat-label">Auto-verified</div>
          </div>
          <div className="stat-card accent-amber">
            <div className="stat-num">{stats.hitl_pending}</div>
            <div className="stat-label">Awaiting review</div>
          </div>
          <div className="stat-card">
            <div className="stat-num">
              {stats.avg_confidence ? `${Math.round(stats.avg_confidence * 100)}%` : '—'}
            </div>
            <div className="stat-label">Avg. confidence</div>
          </div>
          <div className="stat-card accent-green">
            <div className="stat-num">{stats.auto_verified_fields}</div>
            <div className="stat-label">Fields auto-verified</div>
          </div>
          <div className="stat-card accent-red">
            <div className="stat-num">{stats.flagged_fields}</div>
            <div className="stat-label">Fields flagged</div>
          </div>
        </div>
      )}

      <div className="section">
        <div className="section-header">
          <h2 className="section-title">Recent Documents</h2>
          {stats?.hitl_pending > 0 && (
            <Link to="/hitl" className="hitl-alert">
              ⚑ {stats.hitl_pending} document{stats.hitl_pending > 1 ? 's' : ''} need review
            </Link>
          )}
        </div>

        {loading ? (
          <div className="loading-row">Loading documents…</div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">⊙</div>
            <p>No documents yet. <Link to="/upload">Upload your first one →</Link></p>
          </div>
        ) : (
          <table className="doc-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th>Applicant</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Uploaded</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => {
                const meta = STATUS_META[doc.status] || STATUS_META.queued
                return (
                  <tr key={doc.id}>
                    <td>
                      <div className="doc-name">{doc.file_name}</div>
                      <div className="doc-id">#{doc.id}</div>
                    </td>
                    <td><span className="type-badge">{doc.detected_type || doc.document_type || '—'}</span></td>
                    <td className="td-applicant">{doc.applicant_name || <span className="td-na">Unknown</span>}</td>
                    <td><ConfBar value={doc.ai_confidence} /></td>
                    <td>
                      <span className="status-badge" style={{ color: meta.color, background: meta.bg }}>
                        {meta.label}
                      </span>
                    </td>
                    <td className="td-date">
                      {doc.uploaded_at ? format(parseISO(doc.uploaded_at), 'dd MMM yy') : '—'}
                    </td>
                    <td>
                      <Link to={`/documents/${doc.id}`} className="view-link">View →</Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
