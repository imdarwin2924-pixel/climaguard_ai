// E2-S3: only High and Very high districts, highest score first; same data as the map.
import LevelBadge from './LevelBadge'

export default function AttentionList({ items, emptyText, onSelect, selectedId }) {
  if (!items.length) return <p className="muted">{emptyText}</p>
  return (
    <ol className="attention">
      {items.map((d) => (
        <li key={d.id}>
          <button className={d.id === selectedId ? 'row selected' : 'row'} onClick={() => onSelect(d.id)}>
            <span>{d.name}</span>
            <LevelBadge level={d.level} />
          </button>
        </li>
      ))}
    </ol>
  )
}
