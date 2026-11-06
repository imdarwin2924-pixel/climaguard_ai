// A 401 on any call means the session ended: tell the app to show sign-in again.
function checkSignedIn(res, path) {
  if (res.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('cg:signed-out'))
}

export async function get(path) {
  const res = await fetch(`/api${path}`)
  checkSignedIn(res, path)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export async function post(path, body) {
  const res = await fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  checkSignedIn(res, path)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save. Check the form.')
  return data
}

export const LEVELS = ['Low', 'Moderate', 'High', 'Very high']

// NF5: colour is never the only cue; every use also shows the level text.
export const LEVEL_COLOR = { Low: '#cfe8c6', Moderate: '#fde28a', High: '#f4934e', 'Very high': '#c9302c' }
