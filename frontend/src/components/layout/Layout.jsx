import React, { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../store/auth'
import './Layout.css'

const NAV = [
  { to: '/', label: 'Overview', icon: '◈' },
  { to: '/upload', label: 'Upload', icon: '⊕' },
  { to: '/hitl', label: 'Review Queue', icon: '⚑' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">DV</div>
          <div>
            <div className="brand-name">DocVerify</div>
            <div className="brand-sub">Immigration Intelligence</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) =>
              `nav-item ${isActive ? 'active' : ''}`}>
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {user && (
            <div className="user-block">
              <div className="user-avatar">{(user.full_name || user.email)[0].toUpperCase()}</div>
              <div className="user-info">
                <div className="user-name">{user.full_name || 'User'}</div>
                <div className="user-firm">{user.firm_name || user.email}</div>
              </div>
            </div>
          )}
          <button className="logout-btn" onClick={handleLogout}>Sign out</button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
