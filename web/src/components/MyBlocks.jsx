// E4-S3: a nurse's own blocks, highest priority first, latest alert on top, with age-specific advice.
import { useApi } from '../useApi'
import LevelBadge from './LevelBadge'

export default function MyBlocks() {
  const { data, error, loading } = useApi('/me/blocks?horizon=7')
  if (error) return <p className="error">{error.message}</p>
  if (loading || !data) return <p className="muted">Loading…</p>

  return (
    <section className="my-blocks">
      <h1>My blocks</h1>
      <p className="muted small">{data.name} · {data.role} · {data.district} · outlook for the next {data.horizon} days</p>

      {data.latest_alert && (
        <div className="alert-card" role="status">
          <span className="small muted">Latest alert · {new Date(data.latest_alert.at).toLocaleString()}</span>
          <p>{data.latest_alert.message}</p>
        </div>
      )}

      {data.blocks.length === 0
        ? <p className="empty">{data.empty_text}</p>
        : (
          <ol className="priority">
            {data.blocks.map((b, i) => (
              <li key={b.block}>
                <div className="block-head">
                  <span className="rank">{i + 1}</span>
                  <span className="unit-name">{b.block}</span>
                  <LevelBadge level={b.level} />
                </div>
                <h3>What to check</h3>
                <ul className="actions">{b.actions.map((a) => <li key={a}>{a}</li>)}</ul>
                <details>
                  <summary>What to tell each household</summary>
                  <dl className="advice">
                    {data.age_advice.map((g) => <div key={g.group}><dt>{g.group}</dt><dd>{g.advice}</dd></div>)}
                  </dl>
                </details>
              </li>
            ))}
          </ol>
        )}
      <p className="muted small">{data.assigned_count} block{data.assigned_count === 1 ? '' : 's'} assigned to you. Advice text is a draft for review by public health officials.</p>
    </section>
  )
}
