import { useEffect, useState } from 'react'

import {
  getClaimEvidence,
  getEntity,
  getPublication,
} from '../../shared/api/scientificKb'
import type {
  Chunk,
  Claim,
  GraphNode,
  Job,
  Locale,
  Publication,
  ScientificEntity,
} from '../../shared/types/scientific-kb'

// Каноническая последовательность 12 шагов pipeline'а (TT.md §1.2).
// Если шаг не присутствует в job.steps — отрисовываем его серым, чтобы
// пользователь видел КАК должен выглядеть полный pipeline.
const PIPELINE_STEPS: Array<{ name: string; label: { ru: string; en: string } }> = [
  { name: 'text_extraction', label: { ru: 'Извлечение текста', en: 'Text extraction' } },
  { name: 'section_detection', label: { ru: 'Разбор секций', en: 'Section detection' } },
  { name: 'semantic_chunking', label: { ru: 'Сегментация по смыслу', en: 'Semantic chunking' } },
  { name: 'embeddings', label: { ru: 'Векторные представления', en: 'Embeddings' } },
  { name: 'entity_extraction', label: { ru: 'Извлечение сущностей', en: 'Entity extraction' } },
  { name: 'entity_normalization', label: { ru: 'Нормализация сущностей', en: 'Entity normalization' } },
  { name: 'claim_extraction_v2', label: { ru: 'Извлечение утверждений', en: 'Claim extraction' } },
  { name: 'claim_relations', label: { ru: 'Связи между утверждениями', en: 'Claim relations' } },
  { name: 'weighted_graph', label: { ru: 'Взвешенный граф', en: 'Weighted graph' } },
  { name: 'activation_index', label: { ru: 'Индекс активации', en: 'Activation index' } },
  { name: 'ready', label: { ru: 'Готово к запросам', en: 'Ready' } },
]

const STATUS_ICONS: Record<string, string> = {
  completed: '✅',
  running: '⏳',
  pending: '⚪',
  error: '❌',
  skipped: '⏭',
}

type PipelineData =
  | { kind: 'loading' }
  | { kind: 'empty' }
  | { kind: 'error'; message: string }
  | {
      kind: 'publication'
      publication: Publication
      chunksCount: number
      claimsCount: number
      entitiesCount: number
      jobs: Job[]
    }
  | {
      kind: 'claim'
      claim: Claim
      chunk: Chunk | null
      publication: Publication | null
      job: Job | null
    }
  | {
      kind: 'entity'
      entity: ScientificEntity
      claims: Claim[]
      publications: Publication[]
    }

export function NodePipeline({ node, locale }: { node: GraphNode; locale: Locale }) {
  const [data, setData] = useState<PipelineData>({ kind: 'loading' })

  useEffect(() => {
    // Сбрасываем состояние перед каждым запросом, иначе при быстрых кликах
    // в UI может остаться старая инфа, пока грузится новая.
    setData({ kind: 'loading' })
    let cancelled = false

    // Определяем тип узла. ScientificEntity-узлы в Neo4j отдаются с kind =
    // entity_type (Method/Tool/Dataset/Metric/Task/Model/ResearchField), а не
    // строкой "ScientificEntity" — поэтому смотрим на конкретные значения.
    const kind = node.kind
    const isPublication = kind === 'Publication'
    const isClaim = kind === 'ScientificClaim'

    const fetchData = async () => {
      try {
        if (isPublication) {
          const res = await getPublication(node.id)
          if (cancelled) return
          setData({
            kind: 'publication',
            publication: res.publication,
            chunksCount: res.chunks.length,
            claimsCount: res.claims.length,
            entitiesCount: res.entities.length,
            jobs: res.jobs,
          })
        } else if (isClaim) {
          // Для claim нужен evidence (chunk + publication) и job по этой публикации.
          const evidence = await getClaimEvidence(node.id)
          if (cancelled) return
          let job: Job | null = null
          if (evidence.publication?.id) {
            // Берём job из getPublication — он содержит steps.
            try {
              const pubRes = await getPublication(evidence.publication.id)
              if (cancelled) return
              job = pubRes.jobs[0] ?? null
            } catch {
              job = null
            }
          }
          if (cancelled) return
          setData({
            kind: 'claim',
            claim: evidence.claim,
            chunk: evidence.chunk,
            publication: evidence.publication,
            job,
          })
        } else {
          // Все остальные типы — это entities (Method, Tool, Metric, ...).
          const res = await getEntity(node.id)
          if (cancelled) return
          setData({
            kind: 'entity',
            entity: res.entity,
            claims: res.claims,
            publications: res.publications,
          })
        }
      } catch (err) {
        if (cancelled) return
        setData({ kind: 'error', message: String(err) })
      }
    }

    fetchData()

    return () => {
      cancelled = true
    }
  }, [node.id, node.kind])

  if (data.kind === 'loading') {
    return (
      <section className="pipeline-section card-section">
        <b className="card-section-title">{locale === 'ru' ? 'Pipeline' : 'Pipeline'}</b>
        <span className="pipeline-loading">{locale === 'ru' ? 'Загрузка...' : 'Loading...'}</span>
      </section>
    )
  }

  if (data.kind === 'error') {
    return (
      <section className="pipeline-section card-section">
        <b className="card-section-title">{locale === 'ru' ? 'Pipeline' : 'Pipeline'}</b>
        <span className="pipeline-error">
          {locale === 'ru' ? 'Не удалось загрузить:' : 'Failed to load:'} {data.message}
        </span>
      </section>
    )
  }

  if (data.kind === 'publication') {
    const { publication, chunksCount, claimsCount, entitiesCount, jobs } = data
    const job = jobs[0]
    return (
      <section className="pipeline-section card-section">
        <b className="card-section-title">
          {locale === 'ru' ? '📦 Pipeline обработки' : '📦 Processing pipeline'}
        </b>

        <div className="pipeline-row">
          <span className="pipeline-icon">📄</span>
          <div className="pipeline-row-body">
            <b>{locale === 'ru' ? 'Публикация' : 'Publication'}</b>
            <span className="pipeline-row-title">{publication.title}</span>
            <span className="pipeline-row-meta">
              {publication.year && <>{publication.year} · </>}
              {(publication.authors || []).slice(0, 2).join(', ')}
            </span>
          </div>
        </div>

        <div className="pipeline-row">
          <span className="pipeline-icon">📊</span>
          <div className="pipeline-row-body">
            <b>{locale === 'ru' ? 'Артефакты' : 'Artifacts'}</b>
            <span className="pipeline-row-meta">
              {chunksCount} {locale === 'ru' ? 'чанк(ов)' : 'chunk(s)'} ·{' '}
              {claimsCount} {locale === 'ru' ? 'утвержд.' : 'claim(s)'} ·{' '}
              {entitiesCount} {locale === 'ru' ? 'сущност.' : 'entit.'}
            </span>
          </div>
        </div>

        <PipelineSteps job={job} locale={locale} />
      </section>
    )
  }

  if (data.kind === 'claim') {
    const { claim, chunk, publication, job } = data
    return (
      <section className="pipeline-section card-section">
        <b className="card-section-title">
          {locale === 'ru' ? '📦 Pipeline / Откуда взято' : '📦 Pipeline / Provenance'}
        </b>

        {publication && (
          <div className="pipeline-row">
            <span className="pipeline-icon">📄</span>
            <div className="pipeline-row-body">
              <b>{locale === 'ru' ? 'Публикация' : 'Publication'}</b>
              <span className="pipeline-row-title">{publication.title}</span>
              <span className="pipeline-row-meta">
                {publication.year && <>{publication.year} · </>}
                {(publication.authors || []).slice(0, 2).join(', ')}
              </span>
            </div>
          </div>
        )}

        {chunk && (
          <div className="pipeline-row">
            <span className="pipeline-icon">✂️</span>
            <div className="pipeline-row-body">
              <b>{locale === 'ru' ? 'Фрагмент текста (chunk)' : 'Text chunk'}</b>
              <span className="pipeline-row-meta">
                {locale === 'ru' ? 'Секция' : 'Section'}: {chunk.section || '—'}
                {chunk.page_start && <> · {locale === 'ru' ? 'стр.' : 'p.'} {chunk.page_start}{chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ''}</>}
              </span>
              {chunk.text && (
                <blockquote className="pipeline-quote">
                  {chunk.text.length > 240 ? `${chunk.text.slice(0, 240)}…` : chunk.text}
                </blockquote>
              )}
            </div>
          </div>
        )}

        <div className="pipeline-row">
          <span className="pipeline-icon">📌</span>
          <div className="pipeline-row-body">
            <b>{locale === 'ru' ? 'Извлечённое утверждение' : 'Extracted claim'}</b>
            <span className="pipeline-row-meta">
              {locale === 'ru' ? 'Тип' : 'Type'}: {claim.claim_type || '—'}
            </span>
            <blockquote className="pipeline-quote">{claim.claim_text}</blockquote>
          </div>
        </div>

        {(claim.subject_entity || claim.object_entity) && (
          <div className="pipeline-row">
            <span className="pipeline-icon">🏷️</span>
            <div className="pipeline-row-body">
              <b>{locale === 'ru' ? 'Упоминает сущности' : 'Mentions entities'}</b>
              <span className="pipeline-row-meta">
                {[claim.subject_entity, claim.object_entity].filter(Boolean).join(' → ')}
              </span>
            </div>
          </div>
        )}

        <PipelineSteps job={job} locale={locale} />
      </section>
    )
  }

  // entity
  const { entity, claims, publications } = data
  return (
    <section className="pipeline-section card-section">
      <b className="card-section-title">
        {locale === 'ru' ? '📦 Pipeline / Где встречается' : '📦 Pipeline / Where it appears'}
      </b>

      <div className="pipeline-row">
        <span className="pipeline-icon">🏷️</span>
        <div className="pipeline-row-body">
          <b>{locale === 'ru' ? 'Сущность' : 'Entity'}</b>
          <span className="pipeline-row-title">{entity.canonical_name}</span>
          <span className="pipeline-row-meta">
            {locale === 'ru' ? 'Тип' : 'Type'}: {entity.entity_type}
            {entity.aliases && entity.aliases.length > 0 && (
              <> · {locale === 'ru' ? 'синонимы' : 'aliases'}: {entity.aliases.slice(0, 3).join(', ')}</>
            )}
          </span>
        </div>
      </div>

      {publications.length > 0 && (
        <div className="pipeline-row">
          <span className="pipeline-icon">📄</span>
          <div className="pipeline-row-body">
            <b>{locale === 'ru' ? 'Публикации' : 'Publications'} ({publications.length})</b>
            <ul className="pipeline-list">
              {publications.slice(0, 5).map((p) => (
                <li key={p.id} title={p.id}>{p.title}</li>
              ))}
              {publications.length > 5 && (
                <li className="pipeline-list-more">
                  {locale === 'ru' ? `и ещё ${publications.length - 5}…` : `and ${publications.length - 5} more…`}
                </li>
              )}
            </ul>
          </div>
        </div>
      )}

      {claims.length > 0 && (
        <div className="pipeline-row">
          <span className="pipeline-icon">📌</span>
          <div className="pipeline-row-body">
            <b>{locale === 'ru' ? 'Утверждения' : 'Claims'} ({claims.length})</b>
            <ul className="pipeline-list">
              {claims.slice(0, 5).map((c) => (
                <li key={c.id} title={c.claim_type}>
                  {c.claim_text.length > 140 ? `${c.claim_text.slice(0, 140)}…` : c.claim_text}
                </li>
              ))}
              {claims.length > 5 && (
                <li className="pipeline-list-more">
                  {locale === 'ru' ? `и ещё ${claims.length - 5}…` : `and ${claims.length - 5} more…`}
                </li>
              )}
            </ul>
          </div>
        </div>
      )}
    </section>
  )
}

// Отдельная подкомпонента — 12-шаговый pipeline с галочками.
function PipelineSteps({ job, locale }: { job: Job | null | undefined; locale: Locale }) {
  // Маппим из job.steps по имени; если в job нет шага — показываем как pending.
  const statusByName = new Map<string, string>()
  if (job) {
    for (const step of job.steps) {
      statusByName.set(step.name, step.status)
    }
  }
  return (
    <div className="pipeline-row">
      <span className="pipeline-icon">🧠</span>
      <div className="pipeline-row-body">
        <b>
          {locale === 'ru' ? 'Pipeline (12 шагов)' : 'Pipeline (12 steps)'}
          {job?.status && <> · <em className={`pipeline-status pipeline-status-${job.status}`}>{job.status}</em></>}
        </b>
        <ol className="pipeline-steps">
          {PIPELINE_STEPS.map((step) => {
            const status = statusByName.get(step.name) ?? (job ? 'pending' : 'unknown')
            const icon = STATUS_ICONS[status] ?? '·'
            return (
              <li key={step.name} className={`pipeline-step pipeline-step-${status}`} title={step.name}>
                <span className="pipeline-step-icon">{icon}</span>
                <span className="pipeline-step-label">{step.label[locale]}</span>
              </li>
            )
          })}
        </ol>
        {!job && (
          <span className="pipeline-loading">
            {locale === 'ru' ? 'Нет данных по job — публикация была загружена через bootstrap, не через upload' : 'No job data — publication was loaded via bootstrap, not via upload'}
          </span>
        )}
      </div>
    </div>
  )
}
