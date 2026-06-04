import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import './Auth.css'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, loading, error } = useAuth()
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    const ok = await login(email, password)
    if (ok) navigate('/')
  }

  return (
    <div className="auth-page">
      <div className="auth-left">
        <div className="auth-brand">
          <div className="auth-brand-mark">DV</div>
          <span>DocVerify AI</span>
        </div>
        <h1 className="auth-headline">
          Every field.<br />
          <em>Extracted correctly.</em>
        </h1>
        <p className="auth-sub">
          AI-powered immigration document intelligence with confidence scoring
          and human-in-the-loop review for zero missed fields.
        </p>
        <div className="auth-stats">
          <div className="auth-stat"><strong>98.4%</strong><span>Avg. accuracy</span></div>
          <div className="auth-stat"><strong>&lt;8s</strong><span>Per document</span></div>
          <div className="auth-stat"><strong>I-129, L-1,<br/>Passports +</strong><span>Doc types</span></div>
        </div>
      </div>

      <div className="auth-right">
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-form-header">
            <h2>Sign in</h2>
            <p>Access your document workspace</p>
          </div>

          {error && <div className="auth-error">{error}</div>}

          <div className="field-group">
            <label>Email</label>
            <input type="email" placeholder="you@yourfirm.com"
              value={email} onChange={e => setEmail(e.target.value)} required />
          </div>

          <div className="field-group">
            <label>Password</label>
            <input type="password" placeholder="••••••••"
              value={password} onChange={e => setPassword(e.target.value)} required />
          </div>

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in →'}
          </button>

          <p className="auth-switch">
            No account? <Link to="/signup">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
