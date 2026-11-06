// E1-S3: sign in with an official email (admin, Deputy Director) or a mobile number (Village Health Nurse).
import { useState } from 'react'
import { post } from '../api'
import CreateAccount from './CreateAccount'

export default function SignIn({ onSignedIn }) {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState('signin')

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await post('/auth/login', { login, password }))
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth">
      <div className="auth-tabs" role="tablist">
        <button role="tab" aria-selected={mode === 'signin'} className={mode === 'signin' ? 'tab active' : 'tab'} onClick={() => setMode('signin')}>Sign in</button>
        <button role="tab" aria-selected={mode === 'create'} className={mode === 'create' ? 'tab active' : 'tab'} onClick={() => setMode('create')}>Create account</button>
      </div>
      {mode === 'create' ? <CreateAccount onDone={() => setMode('signin')} /> : (
      <form onSubmit={submit} className="card-box">
        <h1>Sign in</h1>
        <label className="field">Official email or mobile number
          <input value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" required autoFocus />
        </label>
        <label className="field">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="muted small">New here? Use Create account; your district officer or the state admin approves it. Forgot your password? Nurses: ask your district officer. Officers: ask the state admin. They can reset it.</p>
      </form>
      )}
    </main>
  )
}
