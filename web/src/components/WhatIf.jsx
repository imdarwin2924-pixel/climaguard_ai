// E5-S1: change forecast rainfall and humidity (−50% to +50%) and see the level and reasons beside the forecast.
import { useEffect, useState } from 'react'
import { useApi } from '../useApi'
import LevelBadge from './LevelBadge'

function useDebounced(value, ms) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function Slider({ label, value, onChange }) {
  return (
    <label className="slider">
      <span>{label}: <b>{value > 0 ? '+' : ''}{value}%</b></span>
      <input type="range" min={-50} max={50} step={10} value={value} onChange={(e) => onChange(Number(e.target.value))}
             aria-valuetext={`${value} percent`} />
    </label>
  )
}

export default function WhatIf({ id, horizon }) {
  const [rain, setRain] = useState(0)
  const [humidity, setHumidity] = useState(0)
  const query = useDebounced(`/districts/${id}/whatif?horizon=${horizon}&rain=${rain}&humidity=${humidity}`, 250)
  const { data, error } = useApi(query)
  const changed = rain !== 0 || humidity !== 0

  return (
    <div className={changed ? 'whatif scenario' : 'whatif'}>
      <Slider label="Forecast rainfall" value={rain} onChange={setRain} />
      <Slider label="Forecast humidity" value={humidity} onChange={setHumidity} />
      <button type="button" onClick={() => { setRain(0); setHumidity(0) }} disabled={!changed}>Reset to forecast</button>
      {error && <p className="error">{error.message}</p>}
      {data && (
        <>
          {changed && <p className="scenario-label" role="status">Scenario, not forecast</p>}
          <div className="compare">
            <div><span className="muted small">Forecast</span><LevelBadge level={data.current.level} /></div>
            <span aria-hidden="true">→</span>
            <div><span className="muted small">{changed ? 'Scenario' : 'Same as forecast'}</span><LevelBadge level={data.scenario.level} /></div>
          </div>
          {changed && (
            <ul className="plain small">
              {data.scenario.drivers.map((c, i) => <li key={i}>{c.direction === 'raises' ? '▲' : '▼'} {c.text}</li>)}
            </ul>
          )}
          <p className="muted small">{data.note}</p>
        </>
      )}
    </div>
  )
}
