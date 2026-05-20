import { useCallback, useEffect, useState } from 'react'

import {
  applyPendingFeedback,
  askWithEvidence,
  evaluateRagAnswer,
  evaluationAggregate,
  getActivationKeys,
  listClaims,
  listEntities,
  listFeedbackEvents,
  listReviewQueue,
  listRelations,
  resolveReviewItem,
  searchGraph,
  searchHybrid,
  searchKeyword,
  searchSemantic,
  submitFeedback,
} from '../../shared/api/scientificKb'
import { ReasoningTrace } from '../../shared/ui/ReasoningTrace'
import { ScoreBreakdown } from '../../shared/ui/ScoreBreakdown'
import type {
  Activation,
  Claim,
  ClaimRelation,
  Evaluation,
  FeedbackEvent,
  Locale,
  RagAnswer,
  ReviewItem,
  ScientificEntity,
  SearchHit,
} from '../../shared/types/scientific-kb'

// Метки типов связей на русском и английском, чтобы пользователь не видел
// сырое `supports/contradicts/limits/extends`.
const RELATION_LABEL: Record<string, { ru: string; en: string }> = {
  supports: { ru: 'подтверждает', en: 'supports' },
  contradicts: { ru: 'противоречит', en: 'contradicts' },
  limits: { ru: 'ограничивает', en: 'limits' },
  extends: { ru: 'развивает', en: 'extends' },
}

type SearchMode = 'keyword' | 'semantic' | 'graph' | 'hybrid'

const SEARCH_MODES: SearchMode[] = ['keyword', 'semantic', 'graph', 'hybrid']

type Labels = Record<string, string>

type Props = {
  t: Labels
  locale: Locale
  defaultQuestion: string
  defaultSearch: string
  onError: (message: string) => void
}

export function LabPage({ t, locale, defaultQuestion, defaultSearch, onError }: Props) {
  const [searchMode, setSearchMode] = useState<SearchMode>('hybrid')
  const [searchQuery, setSearchQuery] = useState(defaultSearch)
  const [searchHits, setSearchHits] = useState<SearchHit[]>([])
  const [searchWeights, setSearchWeights] = useState<Record<string, number> | undefined>(undefined)
  const [selectedHitId, setSelectedHitId] = useState('')
  const [question, setQuestion] = useState(defaultQuestion)
  const [activation, setActivation] = useState<Activation | null>(null)
  const [rag, setRag] = useState<RagAnswer | null>(null)
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [aggregate, setAggregate] = useState<{ total: number; averages: Record<string, number> } | null>(null)
  const [entities, setEntities] = useState<ScientificEntity[]>([])
  const [entityType, setEntityType] = useState('')
  const [relationType, setRelationType] = useState('')
  const [relations, setRelations] = useState<ClaimRelation[]>([])
  // Claims нужны чтобы показывать в "Связях" реальный текст source/target,
  // а не голые id'шники. Map<id, Claim> строится в useMemo ниже.
  const [claims, setClaims] = useState<Claim[]>([])
  const [feedback, setFeedback] = useState<FeedbackEvent[]>([])
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([])
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [agg, ents, rels, cls, fb, rv] = await Promise.all([
        evaluationAggregate(),
        listEntities(),
        listRelations(),
        listClaims(),
        listFeedbackEvents(),
        listReviewQueue(),
      ])
      setAggregate(agg)
      setEntities(ents)
      setRelations(rels)
      setClaims(cls)
      setFeedback(fb)
      setReviewItems(rv.items)
    } catch (err) {
      onError(String(err))
    }
  }, [onError])

  useEffect(() => {
    refresh().catch(() => undefined)
  }, [refresh])

  useEffect(() => {
    setSearchQuery((value) => (value === defaultSearch ? defaultSearch : value))
    setQuestion((value) => (value === defaultQuestion ? defaultQuestion : value))
  }, [defaultQuestion, defaultSearch, locale])

  const runSearch = useCallback(async () => {
    setBusy(true)
    try {
      const fn = searchMode === 'keyword' ? searchKeyword : searchMode === 'semantic' ? searchSemantic : searchMode === 'graph' ? searchGraph : searchHybrid
      const data = await fn(searchQuery, 8)
      setSearchHits(data.items)
      setSearchWeights(data.weights)
      if (data.items[0]) setSelectedHitId(data.items[0].id)
    } catch (err) {
      onError(String(err))
    } finally {
      setBusy(false)
    }
  }, [onError, searchMode, searchQuery])

  const runAsk = useCallback(async () => {
    setBusy(true)
    try {
      const [activationData, ragData] = await Promise.all([
        getActivationKeys(question),
        askWithEvidence(question, locale, 6),
      ])
      setActivation(activationData)
      setRag(ragData)
      setEvaluation(null)
    } catch (err) {
      onError(String(err))
    } finally {
      setBusy(false)
    }
  }, [locale, onError, question])

  const runEvaluate = useCallback(async () => {
    if (!rag) return
    setBusy(true)
    try {
      const eva = await evaluateRagAnswer(rag.id)
      setEvaluation(eva)
      await refresh()
    } catch (err) {
      onError(String(err))
    } finally {
      setBusy(false)
    }
  }, [onError, rag, refresh])

  const sendFeedback = useCallback(
    async (signal: 'positive' | 'review_required') => {
      if (!rag || !rag.sources[0]?.claim_id) return
      try {
        await submitFeedback({
          target_id: rag.sources[0].claim_id,
          signal,
          payload: { rag_answer_id: rag.id },
        })
        await refresh()
      } catch (err) {
        onError(String(err))
      }
    },
    [onError, rag, refresh],
  )

  const applyPending = useCallback(async () => {
    try {
      await applyPendingFeedback()
      await refresh()
    } catch (err) {
      onError(String(err))
    }
  }, [onError, refresh])

  const resolveItem = useCallback(
    async (id: string, action: 'approve' | 'reject') => {
      try {
        await resolveReviewItem(id, action)
        await refresh()
      } catch (err) {
        onError(String(err))
      }
    },
    [onError, refresh],
  )

  const selectedHit = searchHits.find((hit) => hit.id === selectedHitId) ?? searchHits[0]
  const filteredEntities = entityType ? entities.filter((e) => e.entity_type === entityType) : entities
  const filteredRelations = relationType ? relations.filter((r) => r.relation_type === relationType) : relations
  const entityTypes = Array.from(new Set(entities.map((e) => e.entity_type))).sort()
  const relationTypes: Array<ClaimRelation['relation_type']> = ['supports', 'contradicts', 'limits', 'extends']

  // Индекс claim'ов по id для отрисовки текста source/target в "Связях".
  const claimById = new Map(claims.map((c) => [c.id, c]))

  // Человеко-читаемая «сила связи» по весу (используется в чипе).
  const strengthLabel = (weight: number) =>
    weight >= 0.7
      ? (locale === 'ru' ? 'сильная' : 'strong')
      : weight >= 0.4
      ? (locale === 'ru' ? 'средняя' : 'medium')
      : (locale === 'ru' ? 'слабая' : 'weak')

  return (
    <div className="lab-page">
      {/* Intro — объясняет, что такое раздел Лаб и для чего он. */}
      <section className="lab-intro card-strong">
        <h1>{locale === 'ru' ? 'Лаборатория знаний' : 'Knowledge lab'}</h1>
        <p className="muted">
          {locale === 'ru'
            ? 'Здесь можно сравнить четыре режима поиска (ключевой / семантический / графовый / гибридный), задать вопрос с разбором цепочки вывода (RAG), посмотреть, какие сущности и связи извлечены из корпуса, и разобрать очередь ручной проверки.'
            : 'This page lets you compare four search modes (keyword / semantic / graph / hybrid), ask a question with a full reasoning trace (RAG), explore extracted entities and relations, and resolve the human-review queue.'}
        </p>
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.search} · {t.score}</h2>
          <div className="lab-toolbar">
            {SEARCH_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                className={`chip ${mode === searchMode ? 'active' : ''}`}
                onClick={() => setSearchMode(mode)}
              >
                {t[mode === 'graph' ? 'graphMode' : mode] ?? mode}
              </button>
            ))}
          </div>
        </header>
        <div className="lab-row">
          <input
            className="lab-input"
            value={searchQuery}
            placeholder={t.searchPlaceholder}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button className="button" disabled={busy || !searchQuery.trim()} onClick={runSearch}>
            {t.search}
          </button>
        </div>
        <div className="lab-grid lab-grid-2">
          <ul className="lab-hits scrollable">
            {searchHits.length === 0 && <li className="empty-state">{t.emptySearch}</li>}
            {searchHits.map((hit) => (
              <li
                key={hit.id}
                className={`lab-hit ${hit.id === selectedHitId ? 'active' : ''}`}
                onClick={() => setSelectedHitId(hit.id)}
              >
                <header>
                  <span className={`tag ${hit.kind === 'claim' ? 'brand' : 'blue'}`}>{hit.kind}</span>
                  <span className="lab-hit-score">{hit.score.toFixed(3)}</span>
                </header>
                <strong>{hit.title || hit.text.slice(0, 80)}</strong>
                <p className="muted">{hit.text.slice(0, 180)}</p>
              </li>
            ))}
          </ul>
          {selectedHit ? (
            <ScoreBreakdown
              breakdown={{ ...selectedHit.score_breakdown, weights: selectedHit.score_breakdown?.weights ?? searchWeights }}
              labels={t}
              finalScore={selectedHit.score}
            />
          ) : (
            <div className="empty-state">{t.emptySearch}</div>
          )}
        </div>
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.ask} · {t.reasoning}</h2>
          <div className="lab-toolbar">
            <button className="button ghost" disabled={busy || !rag} onClick={runEvaluate}>{t.evaluate}</button>
            <button className="button ghost" disabled={busy || !rag} onClick={() => sendFeedback('positive')}>{t.feedbackHelpful}</button>
            <button className="button ghost" disabled={busy || !rag} onClick={() => sendFeedback('review_required')}>{t.feedbackUnhelpful}</button>
          </div>
        </header>
        <div className="lab-row">
          <input
            className="lab-input"
            value={question}
            placeholder={t.askPlaceholder}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="button" disabled={busy || !question.trim()} onClick={runAsk}>{t.ask}</button>
        </div>
        {rag ? <ReasoningTrace rag={rag} activation={activation} labels={t} /> : <div className="empty-state">{t.emptyAnswer}</div>}
        {evaluation && (
          <div className="lab-eval">
            <header><strong>{t.evaluate}</strong></header>
            <div className="lab-eval-grid">
              {Object.entries(evaluation.metrics).map(([key, value]) => (
                <div className="lab-metric" key={key}>
                  <span className="muted">{key}</span>
                  <div className="score-bar"><span style={{ width: `${Math.round(Number(value) * 100)}%` }} /></div>
                  <strong>{Number(value).toFixed(2)}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.metricsAggregate}</h2>
        </header>
        {aggregate && aggregate.total > 0 ? (
          <div className="lab-eval-grid">
            {Object.entries(aggregate.averages).map(([key, value]) => (
              <div className="lab-metric" key={key}>
                <span className="muted">{key}</span>
                <div className="score-bar"><span style={{ width: `${Math.round(value * 100)}%` }} /></div>
                <strong>{value.toFixed(2)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">{t.emptyQuality}</div>
        )}
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.entities} · {t.aliases}</h2>
          <div className="lab-toolbar">
            <button className={`chip ${entityType === '' ? 'active' : ''}`} onClick={() => setEntityType('')}>{t.all}</button>
            {entityTypes.map((type) => (
              <button key={type} className={`chip ${entityType === type ? 'active' : ''}`} onClick={() => setEntityType(type)}>
                {type}
              </button>
            ))}
          </div>
        </header>
        <div className="lab-entities scrollable">
          {filteredEntities.slice(0, 60).map((entity) => (
            <article className="lab-entity" key={entity.id}>
              <header>
                <strong>{entity.canonical_name}</strong>
                <span className="tag">{entity.entity_type}</span>
              </header>
              <div className="chips">
                {entity.aliases.slice(0, 6).map((alias) => (
                  <span className="tag blue" key={alias}>{alias}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>
            {t.relations}
            <small className="muted lab-section-hint">
              {' '}— {locale === 'ru'
                ? 'кто что подтверждает, развивает, ограничивает или опровергает'
                : 'which claim supports / extends / limits / contradicts which'}
            </small>
          </h2>
          <div className="lab-toolbar">
            <button className={`chip ${relationType === '' ? 'active' : ''}`} onClick={() => setRelationType('')}>{t.all}</button>
            {relationTypes.map((type) => (
              <button key={type} className={`chip ${relationType === type ? 'active' : ''}`} onClick={() => setRelationType(type)}>
                {RELATION_LABEL[type]?.[locale] ?? type}
              </button>
            ))}
          </div>
        </header>
        <ul className="lab-relations scrollable">
          {filteredRelations.length === 0 && <li className="empty-state">{locale === 'ru' ? 'Связей не найдено' : 'No relations found'}</li>}
          {filteredRelations.slice(0, 40).map((rel) => {
            const src = claimById.get(rel.source_claim_id)
            const tgt = claimById.get(rel.target_claim_id)
            const verb = RELATION_LABEL[rel.relation_type]?.[locale] ?? rel.relation_type
            const tagClass =
              rel.relation_type === 'contradicts' ? 'danger'
              : rel.relation_type === 'limits' ? 'warn'
              : rel.relation_type === 'extends' ? 'violet'
              : 'success'
            return (
              <li className="lab-relation" key={rel.id}>
                <header className="lab-relation-header">
                  <span className={`tag ${tagClass}`}>{verb}</span>
                  <span className="muted lab-relation-strength">{strengthLabel(rel.weight)}</span>
                  <div className="score-bar lab-relation-bar">
                    <span style={{ width: `${Math.round(rel.weight * 100)}%` }} />
                  </div>
                  <strong>{Math.round(rel.weight * 100)}%</strong>
                </header>
                <div className="lab-relation-body">
                  <div className="lab-relation-claim">
                    <span className="muted lab-relation-role">
                      {locale === 'ru' ? 'Источник' : 'From'}
                    </span>
                    <span className="lab-relation-text">
                      {src?.claim_text ?? rel.source_claim_id}
                    </span>
                  </div>
                  <span className="lab-relation-arrow">↓</span>
                  <div className="lab-relation-claim">
                    <span className="muted lab-relation-role">
                      {locale === 'ru' ? 'Цель' : 'To'}
                    </span>
                    <span className="lab-relation-text">
                      {tgt?.claim_text ?? rel.target_claim_id}
                    </span>
                  </div>
                </div>
                {rel.rationale && (
                  <footer className="lab-relation-rationale muted">
                    <span>{locale === 'ru' ? 'Почему связь:' : 'Why:'}</span> {rel.rationale}
                  </footer>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      <section className="lab-section card-strong">
        <header className="lab-section-header">
          <h2>{t.reviewQueue}</h2>
          <div className="lab-toolbar">
            <button className="button ghost" onClick={applyPending}>{t.evaluate}</button>
          </div>
        </header>
        {reviewItems.length === 0 ? (
          <div className="empty-state">{t.noReviewItems}</div>
        ) : (
          <ul className="lab-review scrollable">
            {reviewItems.map((item) => (
              <li className="lab-review-item" key={item.id}>
                <header>
                  <strong>{item.item_type}</strong>
                  <span className="muted">{item.item_id}</span>
                </header>
                <p>{item.reason}</p>
                <div className="lab-toolbar">
                  <button className="button ghost" onClick={() => resolveItem(item.id, 'approve')}>{t.approve}</button>
                  <button className="button ghost" onClick={() => resolveItem(item.id, 'reject')}>{t.reject}</button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {feedback.length > 0 && (
          <details className="lab-feedback">
            <summary>{t.feedbackSent} ({feedback.length})</summary>
            <ul className="scrollable">
              {feedback.slice(0, 25).map((event) => (
                <li className="muted" key={event.id}>
                  <span className={`tag ${event.signal === 'positive' ? 'success' : 'warn'}`}>{event.signal}</span>
                  <span> {event.event_type}: {event.target_id} ({event.weight_delta.toFixed(2)})</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </div>
  )
}
