// E1-S3: on first sign-in the temporary password must be replaced before anything else opens.
import { useState } from 'react'
import { post } from '../api'

export default function ChangePassword({ user, onDone }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (next !== again) return setError('The two new passwords do not match.')
    try {
      onDone(await post('/auth/password', { current, new: next }))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <main className="auth">
      <form onSubmit={submit} className="card-box">
        <h1>Set your password</h1>
        <p className="muted small">Welcome, {user.name}. Replace the temporary password you were given with your own (at least 10 characters).</p>
        <label className="field">Temporary password
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label className="field">New password
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
        </label>
        <label className="field">New password again
          <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" minLength={10} required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" type="submit">Save and continue</button>
      </form>
    </main>
  )
}
