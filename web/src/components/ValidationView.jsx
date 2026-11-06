// E5-S2 / MRD N6: how far to trust the outlook. Shows the real check, including when it is weak.
import { useApi } from '../useApi'
import SeasonReplay from './SeasonReplay'

export default function ValidationView() {
  const { data, error, loading } = useApi('/backtest')
  if (error) return <p className="error">{error.message}</p>
  if (loading || !data) return <p className="muted">Loading…</p>

  if (data.engine?.startsWith('weather-index')) {
    return (
      <section className="prose">
        <h2>How far to trust this outlook</h2>
        <p>
          The outlook is a <b>weather suitability index</b>: it measures how favourable temperature, rain and humidity are
          for dengue mosquitoes compared with what is usual for each district in that month. It is not fitted to case data
          and does not forecast case numbers.
        </p>
        <p>
          Checked against {data.outbreak_examples} district-weeks with a dengue outbreak in the {data.against}, the index
          shows <b>no agreement yet</b> (AUC {data.auc_all}; 0.5 means no better than chance). Those reports are sparse, so
          this check is weak either way. A proper test needs monthly case counts per district.
        </p>
        <table className="table">
          <thead><tr><th>Level</th><th>Share of district-weeks</th><th>Outbreak reported</th></tr></thead>
          <tbody>
            {['Low', 'Moderate', 'High', 'Very high'].map((l) => (
              <tr key={l}>
                <td>{l}</td>
                <td>{Math.round((data.level_share[l] ?? 0) * 100)}%</td>
                <td>{((data.outbreak_rate_by_level[l]?.rate ?? 0) * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <SeasonReplay />
      </section>
    )
  }
  return (
    <section className="prose">
      <h2>Backtest, season {data.holdout_season}</h2>
      <p>Detection rate {data.detection_rate_model} vs {data.detection_rate_last_year} for "same month last year";
        median lead time {data.lead_time_weeks_median ?? '–'} weeks; Brier {data.brier_model} vs {data.brier_last_year}.</p>
    </section>
  )
}
