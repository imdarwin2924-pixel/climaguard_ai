// E4-S2: messages each nurse would receive (simulated SMS), and the district alerts behind them.
import { useApi } from '../useApi'

export default function AlertsView() {
  const outbox = useApi('/outbox')
  const alerts = useApi('/alerts')
  if (outbox.error || alerts.error) return <p className="error">{(outbox.error || alerts.error).message}</p>
  if (!outbox.data || !alerts.data) return <p className="muted">Loading…</p>

  return (
    <>
      <h2>Outbox</h2>
      <p className="muted small">{outbox.data.note}</p>
      {outbox.data.messages.length === 0
        ? <p className="muted">No messages yet. Nurses get one when a district with their blocks raises an alert.</p>
        : (
          <table className="table">
            <thead><tr><th>To</th><th>Message</th><th>Time</th></tr></thead>
            <tbody>
              {outbox.data.messages.map((m) => (
                <tr key={m.id}><td>{m.to}</td><td>{m.message} <span className="muted small">({m.message.length}/160)</span></td>
                  <td>{new Date(m.created_at).toLocaleString()}</td></tr>
              ))}
            </tbody>
          </table>
        )}

      <h2 className="spaced">District alerts</h2>
      {alerts.data.alerts.length === 0
        ? <p className="muted">No alerts yet. An alert is raised when a district is High or above on two runs in a row, or jumps two levels at once.</p>
        : (
          <table className="table">
            <thead><tr><th>District</th><th>Outlook</th><th>Reason</th><th>Run</th></tr></thead>
            <tbody>
              {alerts.data.alerts.map((a) => (
                <tr key={a.id}><td>{a.district}</td><td>{a.horizon} days</td><td>{a.reason}</td><td>{a.run_date}</td></tr>
              ))}
            </tbody>
          </table>
        )}
    </>
  )
}
