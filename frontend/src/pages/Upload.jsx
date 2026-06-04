import React, { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { docs } from '../lib/api'
import './Upload.css'

const DOC_TYPES = [
  { value: 'i129', label: 'Form I-129 (H-1B / L-1 Petition)' },
  { value: 'i140', label: 'Form I-140 (Immigrant Petition)' },
  { value: 'i485', label: 'Form I-485 (Adjustment of Status)' },
  { value: 'passport', label: 'Passport' },
  { value: 'visa', label: 'Visa / Entry Document' },
  { value: 'l1_petition', label: 'L-1 Intracompany Transfer' },
  { value: 'ds160', label: 'DS-160 (Nonimmigrant Visa App)' },
  { value: 'eea_form', label: 'EEA Form (UK)' },
  { value: 'other', label: 'Other / Auto-detect' },
]

export default function Upload() {
  const [file, setFile] = useState(null)
  const [docType, setDocType] = useState('other')
  const [status, setStatus] = useState(null) // null | 'uploading' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('')
  const [jobId, setJobId] = useState(null)
  const navigate = useNavigate()

  const onDrop = useCallback(files => {
    if (files[0]) setFile(files[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1
  })

  const submit = async () => {
    if (!file) return
    setStatus('uploading')
    try {
      const { data } = await docs.upload(file, docType)
      setJobId(data.job_id)
      setStatus('success')
      setTimeout(() => navigate(`/documents/${data.job_id}`), 1800)
    } catch (e) {
      setErrorMsg(e.response?.data?.detail || 'Upload failed')
      setStatus('error')
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Upload Document</h1>
          <p className="page-sub">PDF immigration documents up to 20MB</p>
        </div>
      </div>

      <div className="upload-layout">
        <div className="upload-main">
          <div {...getRootProps()} className={`dropzone ${isDragActive ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}>
            <input {...getInputProps()} />
            {file ? (
              <div className="file-selected">
                <div className="file-icon">⊞</div>
                <div className="file-info">
                  <div className="file-name">{file.name}</div>
                  <div className="file-size">{(file.size / 1024).toFixed(1)} KB</div>
                </div>
                <button className="file-remove" onClick={e => { e.stopPropagation(); setFile(null) }}>✕</button>
              </div>
            ) : (
              <>
                <div className="drop-icon">⊙</div>
                <p className="drop-label">{isDragActive ? 'Drop it here' : 'Drop PDF here'}</p>
                <p className="drop-sub">or click to browse files</p>
              </>
            )}
          </div>

          <div className="type-select-wrap">
            <label className="field-label">Document Type</label>
            <select value={docType} onChange={e => setDocType(e.target.value)} className="type-select">
              {DOC_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          {status === 'error' && (
            <div className="upload-error">⚠ {errorMsg}</div>
          )}

          {status === 'success' && (
            <div className="upload-success">
              ✓ Queued for extraction (Job #{jobId}) — redirecting…
            </div>
          )}

          {status === 'uploading' && (
            <div className="upload-progress">
              <div className="progress-bar"><div className="progress-fill" /></div>
              <span>Uploading and queuing…</span>
            </div>
          )}

          <button
            className="upload-btn"
            onClick={submit}
            disabled={!file || status === 'uploading' || status === 'success'}>
            {status === 'uploading' ? 'Processing…' : 'Extract Fields →'}
          </button>
        </div>

        <div className="upload-info">
          <h3>What gets extracted</h3>
          <ul className="extract-list">
            {['Applicant full name & DOB','Passport number & expiry','Visa classification (H-1B, L-1…)',
              'Petition / receipt numbers','Employer & petitioner details','Priority date',
              'Validity period (start & end)','Job title & salary','Consulate / port of entry',
              'MRZ data (passports)'].map(i => (
              <li key={i}><span className="check">✓</span>{i}</li>
            ))}
          </ul>

          <div className="info-box">
            <div className="info-title">Confidence scoring</div>
            <div className="info-row"><span className="dot green" />≥ 90% — Auto-verified</div>
            <div className="info-row"><span className="dot amber" />75–89% — Flagged for review</div>
            <div className="info-row"><span className="dot red" />{'< 75%'} — Sent to HITL queue</div>
          </div>
        </div>
      </div>
    </div>
  )
}
