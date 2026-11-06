// Self sign-up: saved as a pending request with the chosen role; it can sign in only after approval.
import { useEffect, useState } from 'react'
import { get, post } from '../api'

const ROLES = [
  { value: 'nurse', label: 'Village Health Nurse', approver: 'your district officer' },
  { value: 'officer', label: 'Deputy Director of Health Services', approver: 'the state admin' },
  { value: 'admin', label: 'State admin', approver: 'the state admin' },
]

export default function CreateAccount({ onDone }) {
  const [form, setForm] = useState({ name: '', role: 'nurse', districtId: '', blockIds: [], email: '', mobile: '', password: '', again: '' })
  const [districts, setDistricts] = useState([])
  const [blocks, setBlocks] = useState([])
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(null)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const isNurse = form.role === 'nurse'

  useEffect(() => { get('/public/districts').then((r) => setDistricts(r.districts)).catch((e) => setError(e.message)) }, [])
  useEffect(() => {
    if (!isNurse || !form.districtId) return setBlocks([])
    get(`/public/blocks?district_id=${form.districtId}`).then((r) => setBlocks(r.blocks)).catch((e) => setError(e.message))
  }, [isNurse, form.districtId])

  const toggle = (id) => setForm((f) => ({ ...f, blockIds: f.blockIds.includes(id) ? f.blockIds.filter((b) => b !== id) : [...f.blockIds, id] }))

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    if (form.password !== form.again) return setError('The two passwords do not match.')
    try {
      const r = await post('/signup', {
        name: form.name, role: form.role, password: form.password,
        email: isNurse ? null : form.email, mobile: isNurse ? form.mobile : null,
        district_id: form.role === 'admin' ? null : Number(form.districtId) || null,
        block_ids: isNurse ? form.blockIds : [],
      })
      setSent(r.message)
    } catch (err) {
      setError(err.message)
    }
  }

  if (sent) {
    return (
      <div className="card-box">
        <h1>Request sent</h1>
        <p className="ok" role="status">{sent}</p>
        <button className="primary" type="button" onClick={onDone}>Back to sign in</button>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="card-box">
      <h1>Create account</h1>
      <p className="muted small">Your request is saved and waits for approval by {ROLES.find((r) => r.value === form.role).approver}.</p>
      <label className="field">Full name<input value={form.name} onChange={set('name')} autoComplete="name" required /></label>
      <fieldset className="field">
        <legend>Role</legend>
        {ROLES.map((r) => (
          <label key={r.value} className="check">
            <input type="radio" name="role" value={r.value} checked={form.role === r.value}
                   onChange={() => setForm((f) => ({ ...f, role: r.value, blockIds: [] }))} /> {r.label}
          </label>
        ))}
      </fieldset>
      {form.role !== 'admin' && (
        <label className="field">District
          <select value={form.districtId} onChange={(e) => setForm((f) => ({ ...f, districtId: e.target.value, blockIds: [] }))} required>
            <option value="">Choose your district…</option>
            {districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>
      )}
      {isNurse && blocks.length > 0 && (
        <fieldset className="field">
          <legend>Blocks (sub-districts) you cover</legend>
          {blocks.map((b) => (
            <label key={b.id} className="check"><input type="checkbox" checked={form.blockIds.includes(b.id)} onChange={() => toggle(b.id)} /> {b.name}</label>
          ))}
        </fieldset>
      )}
      {isNurse
        ? <label className="field">Mobile number (you will sign in with it)
            <input value={form.mobile} onChange={set('mobile')} inputMode="numeric" autoComplete="tel" placeholder="10 digits" required />
          </label>
        : <label className="field">Official email (you will sign in with it)
            <input type="email" value={form.email} onChange={set('email')} autoComplete="email" required />
          </label>}
      <label className="field">Password (at least 10 characters)
        <input type="password" value={form.password} onChange={set('password')} autoComplete="new-password" minLength={10} required />
      </label>
      <label className="field">Password again
        <input type="password" value={form.again} onChange={set('again')} autoComplete="new-password" minLength={10} required />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" type="submit">Request account</button>
    </form>
  )
}
