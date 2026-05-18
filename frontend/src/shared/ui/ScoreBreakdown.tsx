import type { ScoreBreakdown as ScoreBreakdownData } from '../types/scientific-kb'

const COMPONENT_ORDER: Array<{
  key: keyof ScoreBreakdownData
  weightKey: string
  positive: boolean
  variant: 'brand' | 'blue' | 'violet' | 'danger'
}> = [
  { key: 'keyword', weightKey: 'alpha', positive: true, variant: 'blue' },
  { key: 'semantic', weightKey: 'beta', positive: true, variant: 'brand' },
  { key: 'graph', weightKey: 'gamma', positive: true, variant: 'violet' },
  { key: 'claim_confidence', weightKey: 'delta', positive: true, variant: 'brand' },
  { key: 'evidence_strength', weightKey: 'epsilon', positive: true, variant: 'brand' },
  { key: 'source_reliability', weightKey: 'zeta', positive: true, variant: 'blue' },
  { key: 'contradiction_risk', weightKey: 'eta', positive: false, variant: 'danger' },
]

const LABEL_KEYS: Record<keyof ScoreBreakdownData, string> = {
  keyword: 'keyword',
  semantic: 'semantic',
  graph: 'graphMode',
  activation: 'activation',
  claim_confidence: 'claimConfidence',
  evidence_strength: 'evidenceStrength',
  source_reliability: 'sourceReliability',
  contradiction_risk: 'contradictionRisk',
  weights: 'formula',
}

const VARIANT_CLASS: Record<'brand' | 'blue' | 'violet' | 'danger', string> = {
  brand: 'brand',
  blue: 'blue',
  violet: 'violet',
  danger: 'danger',
}

export type ScoreBreakdownLabels = Record<string, string>

type Props = {
  breakdown?: ScoreBreakdownData
  labels: ScoreBreakdownLabels
  finalScore?: number
}

export function ScoreBreakdown({ breakdown, labels, finalScore }: Props) {
  if (!breakdown) return null
  const weights = (breakdown.weights ?? {}) as Record<string, number>
  const components = COMPONENT_ORDER.map((row) => {
    const raw = (breakdown[row.key] as number | undefined) ?? 0
    const weight = weights[row.weightKey] ?? 0
    const signed = (row.positive ? 1 : -1) * raw * weight
    return { ...row, raw, weight, signed }
  })
  const totalAbs = components.reduce((acc, c) => acc + Math.abs(c.signed), 0) || 1

  return (
    <div className="score-breakdown card-strong">
      <header className="sb-header">
        <strong>{labels.score ?? 'Score'}</strong>
        {typeof finalScore === 'number' && <span className="sb-final">{finalScore.toFixed(3)}</span>}
      </header>
      <div className="sb-bars">
        {components.map((c) => {
          const widthPct = Math.max(2, Math.round((Math.abs(c.signed) / totalAbs) * 100))
          const valueText = `${c.raw.toFixed(2)} × ${c.weight.toFixed(2)} = ${c.signed >= 0 ? '+' : ''}${c.signed.toFixed(3)}`
          return (
            <div className="sb-row" key={String(c.key)}>
              <span className="sb-label">{labels[LABEL_KEYS[c.key]] ?? String(c.key)}</span>
              <div className={`score-bar ${VARIANT_CLASS[c.variant]}`}>
                <span style={{ width: `${widthPct}%` }} />
              </div>
              <span className="sb-value">{valueText}</span>
            </div>
          )
        })}
      </div>
      {Object.keys(weights).length > 0 && (
        <footer className="sb-footer">
          <span className="muted">{labels.formula ?? 'Formula'}: </span>
          <code className="sb-code">
            α·k + β·s + γ·g + δ·conf + ε·ev + ζ·src − η·contr
          </code>
        </footer>
      )}
    </div>
  )
}
