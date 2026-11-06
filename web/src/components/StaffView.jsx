// E1-S2: the Deputy Director creates Village Health Nurse IDs in their own district and assigns blocks.
import { useState } from 'react'
import { post } from '../api'
import { useApi } from '../useApi'
import AccountRequests from './AccountRequests'
import OneTimePassword from './OneTimePassword'

export default function StaffView() {
  const [version, setVersion] = useState(0)
  const blocks = useApi('/blocks')
  const staff = useApi(`/staff?v=${version}`)
  const [form, setForm] = useState({ name: '', mobile: '', blockIds: [] })
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)

  const toggle = (id) => setForm((f) => ({ ...f, blockIds: f.blockIds.includes(id) ? f.blockIds.filter((b) => b !== id) : [...f.blockIds, id] }))

  const reset = async (s) => {
    if (!window.confirm(`Reset the password for ${s.name}? They will be signed out and must use the new one-time password.`)) return
    try {
      const r = await post(`/staff/${s.id}/reset`, {})
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
      const r = await post('/staff', { name: form.name, mobile: form.mobile, block_ids: form.blockIds })
      setCreated({ name: r.name, password: r.temporary_password, signIn: form.mobile.replace(/\D/g, '').slice(-10) })
      setForm({ name: '', mobile: '', blockIds: [] })
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <main className="staff">
      <h1>Field staff{blocks.data && ` · ${blocks.data.district}`}</h1>
      <AccountRequests onDecided={() => setVersion((v) => v + 1)} />
      <div className="staff-grid">
        <form onSubmit={save} className="card-box">
          <h2>Add a Village Health Nurse</h2>
          <label className="field">Name<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
          <label className="field">Mobile number (used to sign in)
            <input value={form.mobile} inputMode="numeric" autoComplete="off" placeholder="10 digits"
                   onChange={(e) => setForm({ ...form, mobile: e.target.value })} required />
          </label>
          <fieldset className="field">
            <legend>Blocks (sub-districts) in your district</legend>
            {blocks.data?.blocks.map((b) => (
              <label key={b.id} className="check"><input type="checkbox" checked={form.blockIds.includes(b.id)} onChange={() => toggle(b.id)} /> {b.name}</label>
            ))}
          </fieldset>
          {error && <p className="error" role="alert">{error}</p>}
          {created && <OneTimePassword {...created} onDismiss={() => setCreated(null)} />}
          <button className="primary" type="submit">Create staff ID</button>
        </form>

        <div className="card-box">
          <h2>Staff in your district</h2>
          {staff.data?.staff.length === 0 && <p className="muted">No staff yet.</p>}
          <ul className="plain">
            {staff.data?.staff.map((s) => (
              <li key={s.id} className="staff-row"><b>{s.name}</b> <span className="muted small">ID {s.id} · {s.mobile}
                {!s.password_set && ' · not signed in yet'}</span><br />
                <span className="small">{s.blocks.join(', ')}</span>{' '}
                <button className="link small" onClick={() => reset(s)}>Reset password</button></li>
            ))}
          </ul>
        </div>
      </div>
    </main>
  )
}
