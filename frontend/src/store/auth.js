import { create } from 'zustand'
import { auth as authApi } from '../lib/api'

export const useAuth = create((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  loading: false,
  error: null,

  login: async (email, password) => {
    set({ loading: true, error: null })
    try {
      const { data } = await authApi.login(email, password)
      localStorage.setItem('token', data.access_token)
      set({ token: data.access_token, user: data.user, loading: false })
      return true
    } catch (e) {
      set({ error: e.response?.data?.detail || 'Login failed', loading: false })
      return false
    }
  },

  signup: async (payload) => {
    set({ loading: true, error: null })
    try {
      const { data } = await authApi.signup(payload)
      localStorage.setItem('token', data.access_token)
      set({ token: data.access_token, user: data.user, loading: false })
      return true
    } catch (e) {
      set({ error: e.response?.data?.detail || 'Signup failed', loading: false })
      return false
    }
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },

  fetchMe: async () => {
    try {
      const { data } = await authApi.me()
      set({ user: data })
    } catch {
      set({ user: null, token: null })
      localStorage.removeItem('token')
    }
  },
}))
