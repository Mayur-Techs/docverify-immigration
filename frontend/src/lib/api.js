import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${BASE}/api/v1`,
  timeout: 60000,
})

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const auth = {
  signup: (data) => api.post('/auth/signup', data),
  login: (email, password) => api.post(
    '/auth/login',
    new URLSearchParams({ username: email, password }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  ),
  me: () => api.get('/auth/me'),
}

export const docs = {
  list:         (params) => api.get('/documents/', { params }),
  get:          (id) => api.get(`/documents/${id}`),
  status:       (id) => api.get(`/documents/${id}/status`),
  fields:       (id) => api.get(`/documents/${id}/fields`),
  stats:        () => api.get('/documents/stats/summary'),
  search:       (q) => api.get('/documents/search', { params: { q } }),
  export:       () => api.get('/documents/export', { responseType: 'blob' }),
  hitlQueue:    () => api.get('/documents/hitl/queue'),
  resolveHitl:  (id, notes) => api.post(`/documents/hitl/${id}/resolve`, null, { params: { notes } }),
  upload:       (file, docType) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('document_type', docType || 'other')
    return api.post('/documents/upload', fd)
  },
  reprocess:    (id) => api.post(`/documents/${id}/reprocess`),
  delete:       (id) => api.delete(`/documents/${id}`),
  verifyField:  (docId, fid, val) =>
    api.patch(`/documents/${docId}/fields/${fid}/verify`, { corrected_value: val }),
}

export default api
