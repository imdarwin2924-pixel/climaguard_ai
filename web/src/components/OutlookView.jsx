// E2-E4 officer outlook: risk map, 7/14 toggle, needs-attention list, district panel.
import { useEffect, useState } from 'react'
import { LEVELS } from '../api'
import { useApi } from '../useApi'
import AttentionList from './AttentionList'
import DistrictPanel from './DistrictPanel'
import LevelBadge from './LevelBadge'
import RiskMap from './RiskMap'

// Days between a run date (YYYY-MM-DD) and today, in local time.
function daysOld(runDate) {
  const [y, m, d] = runDate.split('-').map(Number)
  const today = new Date()
  return Math.floor((new Date(today.getFullYear(), today.getMonth(), today.getDate()) - new Date(y, m - 1, d)) / 86400000)
}

function useWide() {
  const query = '(min-width: 768px)'
  const [wide, setWide] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const m = window.matchMedia(query)
    const on = () => setWide(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return wide
}

export default function OutlookView({ homeDistrictId }) {
  const [horizon, setHorizon] = useState(7)
  const [selectedId, setSelectedId] = useState(homeDistrictId ?? null)  // an officer opens on their own district
  const [labels, setLabels] = useState(useWide())
  const risk = useApi(`/risk?horizon=${horizon}`)
  const geo = useApi('/geo/districts')

  return (
    <main className="outlook">
      <div className="toolbar">
        <h1>{risk.data?.title ?? `Dengue outlook, next ${horizon} days`}</h1>
        <div className="toggle" role="group" aria-label="Outlook length">
          {[7, 14].map((h) => (
            <button key={h} className={horizon === h ? 'on' : ''} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>
              {h} days
            </button>
          ))}
        </div>
        <label className="check"><input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} /> Labels on map</label>
      </div>
      {risk.error && <p className="error">{risk.error.message}</p>}
      {risk.data && (
        <>
          <p className="muted small">Run of {risk.data.run_date} · {risk.data.model_version}</p>
          {daysOld(risk.data.run_date) > 1 && (
            <p className="error" role="alert">
              This outlook is {daysOld(risk.data.run_date)} days old: the daily update has not run since {risk.data.run_date}.
              Check the scheduled task and backend/logs/run-live.log.
            </p>
          )}
        </>
      )}

      <div className="grid">
        <div className="map-wrap">
          {geo.data && risk.data
            ? <RiskMap geo={geo.data} districts={risk.data.districts} selectedId={selectedId}
                       onSelect={setSelectedId} showLabels={labels} />
            : <div className="map placeholder">{geo.error ? geo.error.message : 'Loading map…'}</div>}
          <ul className="legend" aria-label="Legend">
            {LEVELS.map((l) => <li key={l}><LevelBadge level={l} /></li>)}
          </ul>
        </div>

        <aside className="side">
          <section className="panel">
            <DistrictPanel id={selectedId} horizon={horizon} onClose={() => setSelectedId(null)} />
          </section>
          <section>
            <h2>Needs attention</h2>
            {risk.data && <AttentionList items={risk.data.needs_attention} emptyText={risk.data.needs_attention_empty_text}
                                         onSelect={setSelectedId} selectedId={selectedId} />}
          </section>
        </aside>
      </div>

      {risk.data && (
        <details className="all">
          <summary>All {risk.data.districts.length} districts</summary>
          <ul className="all-list">
            {risk.data.districts.map((d) => (
              <li key={d.id}>
                <button className="row" onClick={() => setSelectedId(d.id)}><span>{d.name}</span><LevelBadge level={d.level} /></button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </main>
  )
}
