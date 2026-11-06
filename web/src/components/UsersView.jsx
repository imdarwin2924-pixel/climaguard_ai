// E1-S1: the state admin creates Deputy Director accounts and sees every user.
import { useState } from 'react'
import { post } from '../api'
import { useApi } from '../useApi'
import AccountRequests from './AccountRequests'
import OneTimePassword from './OneTimePassword'

export default function UsersView() {
  const [version, setVersion] = useState(0)
  const users = useApi(`/users?v=${version}`)
  const districts = useApi('/districts')
  const [form, setForm] = useState({ name: '', email: '', district_id: '' })
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)

  const reset = async (u) => {
    if (!window.confirm(`Reset the password for ${u.name}? They will be signed out and must use the new one-time password.`)) return
    try {
      const r = await post(`/users/${u.id}/reset`, {})
      setCreated({ name: r.name, password: r.temporary_password, signIn: r.sign_in, reset: true })
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const r = await post('/users', { ...form, district_id: Number(form.district_id) })
      setCreated({ name: r.name, password: r.temporary_password, signIn: form.email.trim().toLowerCase() })
      setForm({ name: '', email: '', district_id: '' })
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <main>
      <h1>Users</h1>
      <AccountRequests onDecided={() => setVersion((v) => v + 1)} />
      <div className="staff-grid">
        <form onSubmit={save} className="card-box">
          <h2>Add a Deputy Director</h2>
          <label className="field">Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
          <label className="field">Official email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="off" required />
          </label>
          <label className="field">District
            <select value={form.district_id} onChange={(e) => setForm({ ...form, district_id: e.target.value })} required>
              <option value="">Choose a district…</option>
              {districts.data?.districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          {created && <OneTimePassword {...created} onDismiss={() => setCreated(null)} />}
          <button className="primary" type="submit">Create account</button>
        </form>

        <div className="card-box">
          <h2>All users</h2>
          <table className="table">
            <thead><tr><th>Name</th><th>Role</th><th>District</th><th>Signs in with</th><th /></tr></thead>
            <tbody>
              {users.data?.users.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}{!u.password_set && <span className="muted small"> · not signed in yet</span>}</td>
                  <td>{u.role}</td><td>{u.district ?? '—'}</td><td>{u.sign_in}</td>
                  <td>{u.can_reset && <button className="link" onClick={() => reset(u)}>Reset password</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
