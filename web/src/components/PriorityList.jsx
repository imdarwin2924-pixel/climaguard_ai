// E4-S1: ranked units in a High / Very high district, with the factors behind each rank and what to check.
import { useApi } from '../useApi'

export default function PriorityList({ id, horizon }) {
  const { data, error, loading } = useApi(`/districts/${id}/priority?horizon=${horizon}`)
  if (error) return <p className="error">{error.message}</p>
  if (loading || !data) return <p className="muted">Loading priority list…</p>
  if (data.message) return <p className="muted">{data.message}</p>

  return (
    <>
      <ol className="priority">
        {data.units.map((u) => (
          <li key={u.name}>
            <details open={u.rank <= 2}>
              <summary>
                <span className="rank">{u.rank}</span>
                <span className="unit-name">{u.name}</span>
                <span className="muted small">priority {Math.round(u.priority * 100)}</span>
              </summary>
              <p className="factors small">
                {u.density_per_km2.toLocaleString()} people/km² · {u.children_0_6_pct}% children 0–6 ·{' '}
                {u.past_outbreaks ? `${u.past_outbreaks} past outbreak${u.past_outbreaks > 1 ? 's' : ''}` : 'no past outbreak on record'}
              </p>
              <ul className="actions">
                {u.actions.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </details>
          </li>
        ))}
      </ol>
      <p className="muted small">{data.unit}s. {data.method}</p>
    </>
  )
}
