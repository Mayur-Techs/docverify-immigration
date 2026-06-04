import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import './Auth.css'

export default function Signup() {
  const [form, setForm] = useState({ email:'', password:'', full_name:'', firm_name:'' })
  const { signup, loading, error } = useAuth()
  const navigate = useNavigate()

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    const ok = await signup(form)
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
          Built for<br />
          <em>immigration law.</em>
        </h1>
        <p className="auth-sub">
          Extract, score, and verify fields from any immigration document.
          Groq LLM extraction with automatic HITL routing on low confidence.
        </p>
      </div>

      <div className="auth-right">
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-form-header">
            <h2>Create account</h2>
            <p>Get started in 30 seconds</p>
          </div>

          {error && <div className="auth-error">{error}</div>}

          <div className="field-row">
            <div className="field-group">
              <label>Full Name</label>
              <input placeholder="Christi Jackson" value={form.full_name} onChange={set('full_name')} />
            </div>
            <div className="field-group">
              <label>Firm Name</label>
              <input placeholder="Laura Devine Immigration" value={form.firm_name} onChange={set('firm_name')} />
            </div>
          </div>

          <div className="field-group">
            <label>Work Email</label>
            <input type="email" placeholder="you@yourfirm.com" value={form.email} onChange={set('email')} required />
          </div>

          <div className="field-group">
            <label>Password</label>
            <input type="password" placeholder="Min. 8 characters" value={form.password} onChange={set('password')} required minLength={8} />
          </div>

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? 'Creating account…' : 'Create account →'}
          </button>

          <p className="auth-switch">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
