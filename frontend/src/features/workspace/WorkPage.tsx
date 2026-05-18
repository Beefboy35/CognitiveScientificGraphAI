import type { FormEvent, ReactNode } from 'react'

import type { Labels } from '../../shared/i18n/dictionary'
import { claimTypeLabel, defaultSteps, kindLabel, metricLabel, statusLabel, stepName } from '../../shared/i18n/labels'
import { Empty, Metric, PanelTitle, Score } from '../../shared/ui/Primitives'
import type { Chunk, Claim, Evaluation, Job, Locale, Publication, RagAnswer, SearchHit, WorkSummary } from '../../shared/types/scientific-kb'
import { formatPages, formatPercent, normalizeNumber } from '../../shared/utils/format'

const WORK_PAGE_LIMITS = {
  sources: 3,
  claims: 6,
  chunks: 4,
  metrics: 6,
} as const

type WorkPageProps = {
  t: Labels
  locale: Locale
  summary: WorkSummary
  publications: Publication[]
  selectedPublicationId: string
  selectedPublication?: Publication
  selectedClaims: Claim[]
  chunks: Chunk[]
  jobs: Job[]
  searchQuery: string
  searchHits: SearchHit[]
  question: string
  ragAnswer: RagAnswer | null
  evaluation: Evaluation | null
  draftTitle: string
  draftText: string
  busy: boolean
  onSelectPublication: (id: string) => void
  onDraftTitleChange: (value: string) => void
  onDraftTextChange: (value: string) => void
  onSearchQueryChange: (value: string) => void
  onQuestionChange: (value: string) => void
  onCreatePublication: () => void
  onUploadFile: (file: File | null) => void
  onResetDemo: () => void
  onRefresh: () => void
  onSearch: () => void
  onAsk: () => void
  onEvaluate: () => void
}

type PanelProps = {
  title: string
  children: ReactNode
  className?: string
}

function Panel({ title, children, className = '' }: PanelProps) {
  return (
    <section className={['panel', className].filter(Boolean).join(' ')}>
      <PanelTitle title={title} />
      {children}
    </section>
  )
}

function TextPreview({ text, maxLength = 320 }: { text: string; maxLength?: number }) {
  const safeText = typeof text === 'string' ? text : ''

  if (safeText.length <= maxLength) {
    return <p>{safeText}</p>
  }

  return <p>{safeText.slice(0, maxLength).trimEnd()}...</p>
}

function emptyMaterialsLabel(locale: Locale) {
  return locale === 'ru' ? 'Материалов пока нет' : 'No materials yet'
}

function noSelectedMaterialLabel(locale: Locale) {
  return locale === 'ru' ? 'Материал не выбран' : 'No material selected'
}

function SummaryStats({ t, summary }: { t: Labels; summary: WorkSummary }) {
  return (
    <div className="stats">
      <Metric label={t.materials} value={normalizeNumber(summary.publications)} />
      <Metric label={t.facts} value={normalizeNumber(summary.claims)} />
      <Metric label={t.terms} value={normalizeNumber(summary.entities)} />
      <Metric label={t.links} value={normalizeNumber(summary.relations)} />
    </div>
  )
}

function PublicationList({
  t,
  locale,
  publications,
  selectedPublicationId,
  onSelectPublication,
}: {
  t: Labels
  locale: Locale
  publications: Publication[]
  selectedPublicationId: string
  onSelectPublication: (id: string) => void
}) {
  return (
    <Panel title={t.materials}>
      <nav className="material-list" aria-label={t.materials}>
        {publications.length > 0 ? (
          publications.map((publication) => {
            const isSelected = publication.id === selectedPublicationId

            return (
              <button
                key={publication.id}
                type="button"
                aria-pressed={isSelected}
                className={isSelected ? 'material active' : 'material'}
                onClick={() => onSelectPublication(publication.id)}
              >
                <strong>{publication.title}</strong>
                <span>{statusLabel(publication.status, t)} · {formatPages(publication.pages, locale)}</span>
              </button>
            )
          })
        ) : (
          <Empty text={emptyMaterialsLabel(locale)} />
        )}
      </nav>
    </Panel>
  )
}

function AddPublicationPanel({
  t,
  draftTitle,
  draftText,
  busy,
  onDraftTitleChange,
  onDraftTextChange,
  onCreatePublication,
  onUploadFile,
  onResetDemo,
}: {
  t: Labels
  draftTitle: string
  draftText: string
  busy: boolean
  onDraftTitleChange: (value: string) => void
  onDraftTextChange: (value: string) => void
  onCreatePublication: () => void
  onUploadFile: (file: File | null) => void
  onResetDemo: () => void
}) {
  const canCreatePublication = draftTitle.trim().length > 0 && draftText.trim().length > 0 && !busy

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (canCreatePublication) onCreatePublication()
  }

  return (
    <Panel title={t.add} className="add-panel">
      <form className="add-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="sr-only">{t.titleField}</span>
          <input
            className="input"
            value={draftTitle}
            onChange={(event) => onDraftTitleChange(event.target.value)}
            placeholder={t.titleField}
          />
        </label>
        <label className="field">
          <span className="sr-only">{t.textField}</span>
          <textarea
            className="textarea"
            value={draftText}
            onChange={(event) => onDraftTextChange(event.target.value)}
            placeholder={t.textPlaceholder}
          />
        </label>
        <div className="actions">
          <button className="button primary" type="submit" disabled={!canCreatePublication}>{t.analyze}</button>
          <label className="button file">
            {t.upload}
            <input
              className="sr-only file-input"
              type="file"
              accept=".pdf,.txt,.md"
              disabled={busy}
              onChange={(event) => onUploadFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>
      </form>
      <button className="button ghost full" type="button" disabled={busy} onClick={onResetDemo}>{t.demo}</button>
    </Panel>
  )
}

function WorkSidebar(props: {
  t: Labels
  locale: Locale
  summary: WorkSummary
  publications: Publication[]
  selectedPublicationId: string
  draftTitle: string
  draftText: string
  busy: boolean
  onSelectPublication: (id: string) => void
  onDraftTitleChange: (value: string) => void
  onDraftTextChange: (value: string) => void
  onCreatePublication: () => void
  onUploadFile: (file: File | null) => void
  onResetDemo: () => void
}) {
  return (
    <aside className="side">
      <SummaryStats t={props.t} summary={props.summary} />
      <PublicationList
        t={props.t}
        locale={props.locale}
        publications={props.publications}
        selectedPublicationId={props.selectedPublicationId}
        onSelectPublication={props.onSelectPublication}
      />
      <AddPublicationPanel
        t={props.t}
        draftTitle={props.draftTitle}
        draftText={props.draftText}
        busy={props.busy}
        onDraftTitleChange={props.onDraftTitleChange}
        onDraftTextChange={props.onDraftTextChange}
        onCreatePublication={props.onCreatePublication}
        onUploadFile={props.onUploadFile}
        onResetDemo={props.onResetDemo}
      />
    </aside>
  )
}

function WorkHero({
  t,
  locale,
  busy,
  selectedPublicationId,
  selectedPublication,
  onRefresh,
}: {
  t: Labels
  locale: Locale
  busy: boolean
  selectedPublicationId: string
  selectedPublication?: Publication
  onRefresh: () => void
}) {
  return (
    <section className="hero">
      <h1>{selectedPublication?.title || noSelectedMaterialLabel(locale)}</h1>
      <button className="button" type="button" disabled={busy || !selectedPublicationId} onClick={onRefresh}>{t.refresh}</button>
    </section>
  )
}

function SearchPanel({
  t,
  locale,
  searchQuery,
  searchHits,
  busy,
  onSearchQueryChange,
  onSearch,
}: {
  t: Labels
  locale: Locale
  searchQuery: string
  searchHits: SearchHit[]
  busy: boolean
  onSearchQueryChange: (value: string) => void
  onSearch: () => void
}) {
  const canSearch = searchQuery.trim().length > 0 && !busy

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (canSearch) onSearch()
  }

  return (
    <Panel title={t.search} className="span-6 primary-panel">
      <form className="command" onSubmit={handleSubmit}>
        <label className="field">
          <span className="sr-only">{t.search}</span>
          <input
            className="input"
            value={searchQuery}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            placeholder={t.searchPlaceholder}
          />
        </label>
        <button className="button primary" type="submit" disabled={!canSearch}>{t.search}</button>
      </form>
      <div className="stack" aria-live="polite">
        {searchHits.length > 0 ? (
          searchHits.map((hit) => (
            <article className="card" key={hit.id}>
              <small>{kindLabel(hit.kind, locale)} · {formatPercent(hit.score)}</small>
              <TextPreview text={hit.text} />
            </article>
          ))
        ) : (
          <Empty text={t.emptySearch} />
        )}
      </div>
    </Panel>
  )
}

function AskPanel({
  t,
  question,
  ragAnswer,
  busy,
  onQuestionChange,
  onAsk,
  onEvaluate,
}: {
  t: Labels
  question: string
  ragAnswer: RagAnswer | null
  busy: boolean
  onQuestionChange: (value: string) => void
  onAsk: () => void
  onEvaluate: () => void
}) {
  const canAsk = question.trim().length > 0 && !busy

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (canAsk) onAsk()
  }

  return (
    <Panel title={t.ask} className="span-6 primary-panel">
      <form className="command ask-command" onSubmit={handleSubmit}>
        <label className="field">
          <span className="sr-only">{t.ask}</span>
          <input
            className="input"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            placeholder={t.askPlaceholder}
          />
        </label>
        <button className="button primary" type="submit" disabled={!canAsk}>{t.ask}</button>
        <button className="button" type="button" disabled={busy || !ragAnswer} onClick={onEvaluate}>{t.evaluate}</button>
      </form>
      {ragAnswer ? (
        <article className="answer">
          <b>{t.answer} · {formatPercent(ragAnswer.confidence_score)}</b>
          <TextPreview text={ragAnswer.answer} maxLength={520} />
          <div className="source-list">
            {ragAnswer.sources.slice(0, WORK_PAGE_LIMITS.sources).map((source, index) => (
              <div className="source" key={`${String(source.chunk_id ?? source.publication_id ?? 'source')}-${index}`}>
                <strong>{String(source.publication_title ?? t.sources)}</strong>
                <span>{String(source.claim_text ?? source.evidence_text ?? '')}</span>
              </div>
            ))}
          </div>
        </article>
      ) : (
        <Empty text={t.emptyAnswer} />
      )}
    </Panel>
  )
}

function ClaimsPanel({ t, locale, selectedClaims }: { t: Labels; locale: Locale; selectedClaims: Claim[] }) {
  return (
    <Panel title={t.classFacts} className="span-7">
      <div className="stack">
        {selectedClaims.length > 0 ? (
          selectedClaims.slice(0, WORK_PAGE_LIMITS.claims).map((claim) => (
            <article className="card fact" key={claim.id}>
              <small>{claimTypeLabel(claim.claim_type, locale)}</small>
              <TextPreview text={claim.claim_text} />
              <div className="bars">
                <Score label={t.proof} value={claim.evidence_strength} />
                <Score label={t.confidence} value={claim.confidence_score} />
              </div>
            </article>
          ))
        ) : (
          <Empty text={t.emptyFacts} />
        )}
      </div>
    </Panel>
  )
}

function ChunksPanel({ t, chunks }: { t: Labels; chunks: Chunk[] }) {
  return (
    <Panel title={t.fragments} className="span-5">
      <div className="stack">
        {chunks.length > 0 ? (
          chunks.slice(0, WORK_PAGE_LIMITS.chunks).map((chunk) => (
            <article className="card" key={chunk.id}>
              <small>{chunk.section} · {t.page} {chunk.page_start}</small>
              <TextPreview text={chunk.text} />
            </article>
          ))
        ) : (
          <Empty text={t.emptyFragments} />
        )}
      </div>
    </Panel>
  )
}

function ReadinessPanel({ t, locale, jobs }: { t: Labels; locale: Locale; jobs: Job[] }) {
  return (
    <Panel title={t.readiness} className="span-6">
      <div className="steps">
        {(jobs[0]?.steps ?? defaultSteps()).map((step) => (
          <span className={step.status === 'completed' ? 'done' : ''} key={step.name}>{stepName(step.name, locale)}</span>
        ))}
      </div>
    </Panel>
  )
}

function QualityPanel({ t, locale, evaluation }: { t: Labels; locale: Locale; evaluation: Evaluation | null }) {
  return (
    <Panel title={t.quality} className="span-6">
      {evaluation ? (
        <div className="bars">
          {Object.entries(evaluation.metrics).slice(0, WORK_PAGE_LIMITS.metrics).map(([key, value]) => (
            <Score key={key} label={metricLabel(key, locale)} value={value} />
          ))}
        </div>
      ) : (
        <Empty text={t.emptyQuality} />
      )}
    </Panel>
  )
}

function WorkMain({
  t,
  locale,
  selectedPublicationId,
  selectedPublication,
  selectedClaims,
  chunks,
  jobs,
  searchQuery,
  searchHits,
  question,
  ragAnswer,
  evaluation,
  busy,
  onSearchQueryChange,
  onQuestionChange,
  onRefresh,
  onSearch,
  onAsk,
  onEvaluate,
}: Pick<
  WorkPageProps,
  | 't'
  | 'locale'
  | 'selectedPublicationId'
  | 'selectedPublication'
  | 'selectedClaims'
  | 'chunks'
  | 'jobs'
  | 'searchQuery'
  | 'searchHits'
  | 'question'
  | 'ragAnswer'
  | 'evaluation'
  | 'busy'
  | 'onSearchQueryChange'
  | 'onQuestionChange'
  | 'onRefresh'
  | 'onSearch'
  | 'onAsk'
  | 'onEvaluate'
>) {
  return (
    <main className="main">
      <WorkHero
        t={t}
        locale={locale}
        busy={busy}
        selectedPublicationId={selectedPublicationId}
        selectedPublication={selectedPublication}
        onRefresh={onRefresh}
      />
      <div className="grid">
        <SearchPanel
          t={t}
          locale={locale}
          searchQuery={searchQuery}
          searchHits={searchHits}
          busy={busy}
          onSearchQueryChange={onSearchQueryChange}
          onSearch={onSearch}
        />
        <AskPanel
          t={t}
          question={question}
          ragAnswer={ragAnswer}
          busy={busy}
          onQuestionChange={onQuestionChange}
          onAsk={onAsk}
          onEvaluate={onEvaluate}
        />
        <ClaimsPanel t={t} locale={locale} selectedClaims={selectedClaims} />
        <ChunksPanel t={t} chunks={chunks} />
        <ReadinessPanel t={t} locale={locale} jobs={jobs} />
        <QualityPanel t={t} locale={locale} evaluation={evaluation} />
      </div>
    </main>
  )
}

export function WorkPage(props: WorkPageProps) {
  return (
    <div className="layout">
      <WorkSidebar
        t={props.t}
        locale={props.locale}
        summary={props.summary}
        publications={props.publications}
        selectedPublicationId={props.selectedPublicationId}
        draftTitle={props.draftTitle}
        draftText={props.draftText}
        busy={props.busy}
        onSelectPublication={props.onSelectPublication}
        onDraftTitleChange={props.onDraftTitleChange}
        onDraftTextChange={props.onDraftTextChange}
        onCreatePublication={props.onCreatePublication}
        onUploadFile={props.onUploadFile}
        onResetDemo={props.onResetDemo}
      />
      <WorkMain
        t={props.t}
        locale={props.locale}
        selectedPublicationId={props.selectedPublicationId}
        selectedPublication={props.selectedPublication}
        selectedClaims={props.selectedClaims}
        chunks={props.chunks}
        jobs={props.jobs}
        searchQuery={props.searchQuery}
        searchHits={props.searchHits}
        question={props.question}
        ragAnswer={props.ragAnswer}
        evaluation={props.evaluation}
        busy={props.busy}
        onSearchQueryChange={props.onSearchQueryChange}
        onQuestionChange={props.onQuestionChange}
        onRefresh={props.onRefresh}
        onSearch={props.onSearch}
        onAsk={props.onAsk}
        onEvaluate={props.onEvaluate}
      />
    </div>
  )
}
