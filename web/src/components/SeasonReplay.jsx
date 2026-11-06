// E5-S2: how past outlooks compared with reported outbreaks, month by month, for the last complete season.
import { useState } from 'react'
import { useApi } from '../useApi'
import LevelBadge from './LevelBadge'

const pct = (x) => (x == null ? '–' : `${Math.round(x * 100)}%`)
const monthName = (ym) => new Date(`${ym}-01T00:00:00`).toLocaleString('en-IN', { month: 'short', year: 'numeric' })

export default function SeasonReplay() {
  const [districtId, setDistrictId] = useState('')
  const { data, error } = useApi(`/feedback${districtId ? `?district_id=${districtId}` : ''}`)
  if (error) return <p className="error">{error.message}</p>
  if (!data) return <p className="muted">Loading…</p>
  const s = data.state
  const d = data.district

  return (
    <section className="replay">
      <h2>Season {data.season}, replayed</h2>
      <p className="muted small">
        What the outlook would have said each month, against the dengue outbreaks reported in the {data.against}.
        A month counts as warned when an outlook run before the month began already said High or Very high.
      </p>

      <div className="stats">
        <div><b>{s.detected} of {s.outbreak_months}</b><span>outbreak months warned in advance ({pct(s.detection_rate)})</span></div>
        <div><b>{pct(s.detection_rate_last_year)}</b><span>caught by "same month last year"</span></div>
        <div><b>{s.median_lead_weeks ?? '–'} weeks</b><span>median warning time</span></div>
        <div><b>{pct(s.false_alarm_share)}</b><span>of warned months had no outbreak reported ({s.false_alarm_months} of {s.flagged_months})</span></div>
      </div>

      <label className="field inline">District
        <select value={districtId || data.district_id} onChange={(e) => setDistrictId(e.target.value)}>
          {data.districts.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </label>
      {d.shares_record_of && (
        <p className="muted small">{d.name} was formed in 2019–20; its outbreak record is {d.shares_record_of}'s, so it is counted there in the totals.</p>
      )}

      <table className="table">
        <thead><tr><th>Month</th><th>Highest outlook</th><th>Warned in advance</th><th>Outbreak reported</th></tr></thead>
        <tbody>
          {d.months.map((m) => (
            <tr key={m.month} className={m.outbreak ? 'hit-row' : ''}>
              <td>{monthName(m.month)}</td>
              <td><LevelBadge level={m.peak_level} /> <span className="muted small">{Math.round(m.peak_score * 100)}</span></td>
              <td>{m.flagged_in_advance ? `Yes, ${m.lead_weeks} wk ahead` : 'No'}</td>
              <td>{m.outbreak ? <b>Yes</b> : 'No'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">{d.name}: {d.outbreak_months} outbreak month{d.outbreak_months === 1 ? '' : 's'} reported, {d.detected} warned in advance.</p>
    </section>
  )
}
