import { LEVEL_COLOR } from '../api'

export default function LevelBadge({ level }) {
  return (
    <span className={`badge level-${level.replace(' ', '-').toLowerCase()}`} style={{ background: LEVEL_COLOR[level] }}>
      {level}
    </span>
  )
}
