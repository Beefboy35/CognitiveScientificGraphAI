import { clampPercentValue, formatPercent } from '../utils/format'

export function PanelTitle({ title }: { title: string }) {
  return <h2 className="panel-title">{title}</h2>
}

export function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <b>{String(value)}</b>
    </div>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

export function Score({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="score">
      <span>{label}</span>
      <i><b style={{ width: `${Math.max(4, clampPercentValue(value))}%` }} /></i>
      <em>{formatPercent(value)}</em>
    </div>
  )
}
