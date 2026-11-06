// Pending sign-ups this user may decide: the admin sees all, a district officer sees nurses of their district.
import { useState } from 'react'
import { post } from '../api'
import { useApi } from '../useApi'

export default function AccountRequests({ onDecided }) {
  const [version, setVersion] = useState(0)
  const { data, error } = useApi(`/requests?v=${version}`)
  const [message, setMessage] = useState(null)

  const decide = async (q, decision) => {
    if (decision === 'reject' && !window.confirm(`Reject the account request from ${q.name}?`)) return
    try {
      await post(`/requests/${q.id}/${decision}`, {})
      setMessage(`${q.name}: ${decision === 'approve' ? 'approved, they can sign in now' : 'request rejected'}.`)
      setVersion((v) => v + 1)
      onDecided?.()
    } catch (err) {
      setMessage(err.message)
    }
  }

  if (error) return <p className="error">{error.message}</p>
  if (!data || (data.requests.length === 0 && !message)) return null

  return (
    <div className="card-box requests">
      <h2>Account requests{data.requests.length > 0 && ` (${data.requests.length})`}</h2>
      {message && <p className="ok" role="status">{message}</p>}
      {data.requests.length === 0 && <p className="muted">No requests waiting.</p>}
      <ul className="plain">
        {data.requests.map((q) => (
          <li key={q.id} className="staff-row">
            <b>{q.name}</b> <span className="muted small">{q.role}{q.district && ` · ${q.district}`} · {q.sign_in}</span>
            {q.blocks.length > 0 && <><br /><span className="small">Blocks: {q.blocks.join(', ')}</span></>}
            <br /><span className="muted small">Asked {new Date(q.requested_at).toLocaleString()}</span>
            <div className="decide">
              <button className="primary" onClick={() => decide(q, 'approve')}>Approve</button>
              <button onClick={() => decide(q, 'reject')}>Reject</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
