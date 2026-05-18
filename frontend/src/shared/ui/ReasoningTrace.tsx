import type { Activation, RagAnswer, RagSource } from '../types/scientific-kb'

type Labels = Record<string, string>

type Props = {
  rag: RagAnswer
  activation?: Activation | null
  labels: Labels
}

const ICONS: Record<string, string> = {
  question: '❓',
  activation_keys: '🔑',
  entities: '📦',
  claims: '📌',
  evidence_builder: '📄',
  contradiction_disclosure: '⚖️',
  evidence_aggregation: '🧩',
  grounded_answer: '💬',
  insufficient_entities_or_claims: '🚫',
  honest_refusal: '🤷',
}

const RU_LABEL: Record<string, string> = {
  question: 'Вопрос',
  activation_keys: 'Ключи активации',
  entities: 'Сущности',
  claims: 'Утверждения',
  evidence_builder: 'Доказательства',
  contradiction_disclosure: 'Раскрытие противоречий',
  evidence_aggregation: 'Сбор evidence',
  grounded_answer: 'Обоснованный ответ',
  insufficient_entities_or_claims: 'Недостаточно данных',
  honest_refusal: 'Честный отказ',
}

const EN_LABEL: Record<string, string> = {
  question: 'Question',
  activation_keys: 'Activation keys',
  entities: 'Entities',
  claims: 'Claims',
  evidence_builder: 'Evidence',
  contradiction_disclosure: 'Contradiction disclosure',
  evidence_aggregation: 'Evidence aggregation',
  grounded_answer: 'Grounded answer',
  insufficient_entities_or_claims: 'Insufficient evidence',
  honest_refusal: 'Honest refusal',
}

export function ReasoningTrace({ rag, activation, labels }: Props) {
  const dict = labels.reasoning?.startsWith('Reasoning') ? EN_LABEL : RU_LABEL
  return (
    <section className="reasoning card-strong">
      <header className="reasoning-header">
        <strong>{labels.reasoning ?? 'Reasoning trace'}</strong>
        <span className={`tag ${rag.status === 'answered' ? 'success' : 'warn'}`}>
          {rag.status}
        </span>
      </header>

      <ol className="reasoning-steps">
        {rag.reasoning_trace.map((stage, idx) => (
          <li key={`${stage}_${idx}`} className="reasoning-step">
            <span className="reasoning-icon">{ICONS[stage] ?? '•'}</span>
            <div className="reasoning-body">
              <header>
                <strong>{dict[stage] ?? stage}</strong>
                <small className="muted">step {idx + 1}</small>
              </header>
              {stage === 'question' && <p>{rag.question}</p>}
              {stage === 'activation_keys' && activation && (
                <div className="chips">
                  {activation.activation_keys.slice(0, 18).map((key) => (
                    <span key={key} className="tag blue">{key}</span>
                  ))}
                </div>
              )}
              {stage === 'entities' && rag.used_entities?.length > 0 && (
                <div className="chips">
                  {rag.used_entities.slice(0, 12).map((entity) => (
                    <span key={entity.id} className="tag violet">{entity.canonical_name}</span>
                  ))}
                </div>
              )}
              {stage === 'claims' && rag.used_claims?.length > 0 && (
                <ul className="reasoning-list">
                  {rag.used_claims.slice(0, 5).map((claim) => (
                    <li key={claim.id}>
                      <span className="tag brand">{claim.claim_type}</span>
                      <span className="muted"> {claim.claim_text}</span>
                    </li>
                  ))}
                </ul>
              )}
              {stage === 'evidence_builder' && rag.sources?.length > 0 && (
                <ul className="reasoning-list">
                  {rag.sources.slice(0, 5).map((source, i) => (
                    <li key={i}>
                      <strong>{source.publication_title}</strong>
                      {source.pages && (
                        <span className="muted"> p. {Array.isArray(source.pages) ? source.pages.join('–') : source.pages}</span>
                      )}
                      <p className="muted">{source.evidence_text?.slice(0, 220)}</p>
                    </li>
                  ))}
                </ul>
              )}
              {stage === 'contradiction_disclosure' && (
                <ul className="reasoning-list">
                  {rag.sources?.filter((s) => (s.contradiction_risk ?? 0) > 0.3).slice(0, 3).map((s, idx2) => (
                    <li key={idx2}>
                      <span className="tag danger">contradiction_risk {Number(s.contradiction_risk ?? 0).toFixed(2)}</span>
                      <span className="muted"> {s.claim_text}</span>
                    </li>
                  ))}
                </ul>
              )}
              {(stage === 'grounded_answer' || stage === 'honest_refusal') && (
                <p className="reasoning-answer">{rag.answer}</p>
              )}
            </div>
          </li>
        ))}
      </ol>

      {rag.limitations?.length > 0 && (
        <footer className="reasoning-footer">
          <strong>{labels.limitations ?? 'Limitations'}</strong>
          <ul>
            {rag.limitations.map((lim, idx) => (
              <li key={idx} className="muted">{lim}</li>
            ))}
          </ul>
        </footer>
      )}
    </section>
  )
}

export function SourceCard({ source }: { source: RagSource }) {
  return (
    <article className="source-card">
      <header>
        <strong>{source.publication_title}</strong>
        <span className="muted">p. {Array.isArray(source.pages) ? source.pages.join('–') : source.pages ?? '?'}</span>
      </header>
      {source.claim_type && <span className={`tag ${source.claim_type === 'contradiction_candidate' ? 'danger' : 'brand'}`}>{source.claim_type}</span>}
      <p>{source.claim_text || source.evidence_text}</p>
    </article>
  )
}
