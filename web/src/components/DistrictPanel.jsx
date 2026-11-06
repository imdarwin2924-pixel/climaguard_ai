// E3-S1, E3-S2: level, score and exactly three plain-language driver cards.
import { useApi } from '../useApi'
import LevelBadge from './LevelBadge'
import PriorityList from './PriorityList'
import WhatIf from './WhatIf'

export default function DistrictPanel({ id, horizon, onClose }) {
  const { data, error, loading } = useApi(id ? `/districts/${id}?horizon=${horizon}` : null)
  if (!id) return <p className="muted">Select a district on the map or in the list to see why it is flagged.</p>
  if (error) return <p className="error">{error.message}</p>
  if (loading || !data) return <p className="muted">Loading…</p>

  return (
    <section className="district" aria-live="polite">
      <header>
        <h2>{data.name}</h2>
        <button className="close" onClick={onClose} aria-label="Close district">×</button>
      </header>
      <p className="level-line">
        <LevelBadge level={data.level} /> <span className="muted">score {Math.round(data.score * 100)} / 100 · next {horizon} days</span>
      </p>
      <h3>Why this district</h3>
      <ul className="cards">
        {data.drivers.map((c, i) => (
          <li key={i} className={`card ${c.direction}`}>
            <span className="card-factor">{c.factor} · {c.lag}</span>
            <span className="card-text">{c.text}</span>
            <span className="card-dir">{c.direction === 'raises' ? '▲ raises risk' : '▼ lowers risk'}</span>
          </li>
        ))}
      </ul>
      <details className="whatif-box">
        <summary>What if the weather changes?</summary>
        {/* key: start from the forecast again whenever the district or outlook changes */}
        <WhatIf key={`${id}-${horizon}`} id={id} horizon={horizon} />
      </details>
      <h3>Where to go first</h3>
      <PriorityList id={id} horizon={horizon} />
      {data.recent_alerts.length > 0 && (
        <>
          <h3>Recent alerts</h3>
          <ul className="plain">
            {data.recent_alerts.map((a, i) => <li key={i}>{a.reason} · {new Date(a.at).toLocaleDateString()}</li>)}
          </ul>
        </>
      )}
      <p className="muted small">{data.score_meaning}</p>
    </section>
  )
}
