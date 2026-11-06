// E1-S3: everyone signs in; each role lands on its own home screen and sees only its own tabs.
import { useEffect, useState } from 'react'
import { get, post } from './api'
import AlertsView from './components/AlertsView'
import ChangePassword from './components/ChangePassword'
import MyBlocks from './components/MyBlocks'
import OutlookView from './components/OutlookView'
import SignIn from './components/SignIn'
import StaffView from './components/StaffView'
import UsersView from './components/UsersView'
import ValidationView from './components/ValidationView'

const DISCLAIMER = 'Risk estimate, not a diagnosis.'
const TABS = {
  admin: { users: 'Users', outlook: 'Outlook', alerts: 'Alerts', trust: 'How far to trust it' },
  officer: { outlook: 'Outlook', staff: 'Staff', alerts: 'Alerts', trust: 'How far to trust it' },
  nurse: { 'my-blocks': 'My blocks' },
}

export default function App() {
  const [user, setUser] = useState(undefined)  // undefined = checking, null = signed out
  const [tab, setTab] = useState(null)

  useEffect(() => {
    get('/auth/me').then(setUser).catch(() => setUser(null))
    const signedOut = () => setUser(null)   // any 401 (expired session) sends you back to sign-in
    window.addEventListener('cg:signed-out', signedOut)
    return () => window.removeEventListener('cg:signed-out', signedOut)
  }, [])

  const signIn = (u) => { setUser(u); setTab(u.home) }
  const signOut = async () => { await post('/auth/logout', {}).catch(() => {}); setUser(null) }

  const current = user && (tab && TABS[user.role][tab] ? tab : user.home)

  return (
    <div className="app">
      <header className="top">
        <div className="brand">ClimaGuard AI <span className="muted">· Tamil Nadu dengue</span></div>
        {user && !user.must_change_password && (
          <nav className="tabs" aria-label="Sections">
            {Object.entries(TABS[user.role]).map(([k, label]) => (
              <button key={k} className={current === k ? 'tab active' : 'tab'} aria-current={current === k} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </nav>
        )}
        {user && (
          <div className="who small">
            <span>{user.name} · {user.role_label}{user.district ? ` · ${user.district}` : ''}</span>
            <button className="link" onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>
      {/* NF3 / E2-S1: visible on every screen without scrolling */}
      <div className="disclaimer" role="note">{DISCLAIMER} Population-level weather signal for planning field work.</div>

      {user === undefined && <p className="muted">Loading…</p>}
      {user === null && <SignIn onSignedIn={signIn} />}
      {user?.must_change_password && <ChangePassword user={user} onDone={signIn} />}
      {user && !user.must_change_password && (
        <>
          {current === 'users' && <UsersView />}
          {current === 'outlook' && <OutlookView homeDistrictId={user.role === 'officer' ? user.district_id : null} />}
          {current === 'staff' && <StaffView />}
          {current === 'alerts' && <main><h1>Alerts</h1><AlertsView /></main>}
          {current === 'trust' && <main><ValidationView /></main>}
          {current === 'my-blocks' && <main><MyBlocks /></main>}
        </>
      )}
    </div>
  )
}
