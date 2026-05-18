import { apiFetch } from '../../api'
import type {
  Activation,
  Chunk,
  Claim,
  ClaimRelation,
  Evaluation,
  FeedbackEvent,
  GraphData,
  Job,
  Locale,
  Publication,
  RagAnswer,
  ReviewItem,
  ScientificEntity,
  SearchHit,
  WorkSummary,
} from '../types/scientific-kb'

async function list<T>(path: string): Promise<T[]> {
  return (await apiFetch<{ items: T[] }>(path)).items
}

export function getScientificHealth() {
  return apiFetch<WorkSummary>('/v1/scientific/health')
}

export function getOntology() {
  return apiFetch<{ entity_types: string[]; claim_types: string[]; relation_types: string[]; pipeline_steps: string[] }>('/v1/scientific/ontology')
}

export function getHybridWeights() {
  return apiFetch<Record<string, number>>('/v1/scientific/hybrid-weights')
}

export function listPublications(params: {
  research_field?: string
  status?: string
  year?: number
  search?: string
} = {}) {
  const search = new URLSearchParams()
  if (params.research_field) search.set('research_field', params.research_field)
  if (params.status) search.set('status', params.status)
  if (params.year) search.set('year', String(params.year))
  if (params.search) search.set('search', params.search)
  const query = search.toString()
  return list<Publication>(`/v1/publications${query ? `?${query}` : ''}`)
}

export function getPublication(id: string) {
  return apiFetch<{
    publication: Publication
    chunks: Chunk[]
    claims: Claim[]
    entities: ScientificEntity[]
    jobs: Job[]
    citations: Array<{ source_publication_id: string; target_publication_id: string; context: string }>
  }>(`/v1/publications/${id}`)
}

export function listAuthors() {
  return apiFetch<{ authors: Array<{ id: string; name: string; organization?: string; orcid?: string }>; organizations: Array<{ id: string; name: string; country?: string; kind?: string }> }>('/v1/authors')
}

export function listCitations() {
  return apiFetch<{ items: Array<{ source_publication_id: string; target_publication_id: string; context: string }> }>('/v1/citations')
}

export function listClaims(params: {
  publication_id?: string
  claim_type?: string
  min_confidence?: number
  min_evidence_strength?: number
} = {}) {
  const search = new URLSearchParams()
  if (params.publication_id) search.set('publication_id', params.publication_id)
  if (params.claim_type) search.set('claim_type', params.claim_type)
  if (params.min_confidence != null) search.set('min_confidence', String(params.min_confidence))
  if (params.min_evidence_strength != null) search.set('min_evidence_strength', String(params.min_evidence_strength))
  const query = search.toString()
  return list<Claim>(`/v1/knowledge/claims${query ? `?${query}` : ''}`)
}

export function getClaim(id: string) {
  return apiFetch<{ claim: Claim; relations: ClaimRelation[]; related_claims: Claim[] }>(`/v1/knowledge/claims/${id}`)
}

export function getClaimEvidence(id: string) {
  return apiFetch<{
    claim: Claim
    chunk: Chunk | null
    publication: Publication | null
    evidence_text: string
    pages: [number, number]
    evidence_strength: number
    source_reliability: number
  }>(`/v1/knowledge/claims/${id}/evidence`)
}

export function listEntities(params: { entity_type?: string; search?: string } = {}) {
  const search = new URLSearchParams()
  if (params.entity_type) search.set('entity_type', params.entity_type)
  if (params.search) search.set('search', params.search)
  const query = search.toString()
  return list<ScientificEntity>(`/v1/knowledge/entities${query ? `?${query}` : ''}`)
}

export function getEntity(id: string) {
  return apiFetch<{ entity: ScientificEntity; claims: Claim[]; publications: Publication[] }>(`/v1/knowledge/entities/${id}`)
}

export function listRelations(relation_type?: string) {
  return list<ClaimRelation>(relation_type ? `/v1/knowledge/relations?relation_type=${relation_type}` : '/v1/knowledge/relations')
}

export function listPipelineJobs(publicationId?: string) {
  return list<Job>(publicationId ? `/v1/pipeline/jobs?publication_id=${publicationId}` : '/v1/pipeline/jobs')
}

export function getPipelineJob(id: string) {
  return apiFetch<{ job: Job; publication: Publication | null }>(`/v1/pipeline/jobs/${id}`)
}

export function runPipeline(publicationId: string) {
  return apiFetch<Job>(`/v1/pipeline/publications/${publicationId}/run`, { method: 'POST' })
}

export function retryPipelineStep(publicationId: string, step: string) {
  return apiFetch<Job>(`/v1/pipeline/publications/${publicationId}/steps/${step}/retry`, { method: 'POST' })
}

export function getScientificGraph() {
  return apiFetch<GraphData>('/v1/graph/scientific')
}

export function getPublicationGraph(id: string) {
  return apiFetch<GraphData>(`/v1/graph/publication/${id}`)
}

export function getEntityGraph(id: string, depth = 2) {
  return apiFetch<GraphData>(`/v1/graph/entity/${id}?depth=${depth}`)
}

export function getClaimGraph(id: string, depth = 2) {
  return apiFetch<GraphData>(`/v1/graph/claim/${id}?depth=${depth}`)
}

export function listPublicationChunks(publicationId: string) {
  return apiFetch<{ items: Chunk[] }>(`/v1/publications/${publicationId}/chunks`)
}

export function createPublication(title: string, text: string) {
  return apiFetch<{ publication: Publication; processing_job: Job }>('/v1/publications', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, text, run_pipeline: true }),
  })
}

export function uploadPublication(file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<{ publication: Publication; processing_job: Job }>('/v1/publications/upload', {
    method: 'POST',
    body: form,
  })
}

export function resetScientificDemo() {
  return apiFetch('/v1/scientific/demo/reset', { method: 'POST' })
}

export function updatePublication(id: string, payload: { title?: string; abstract?: string }) {
  return apiFetch<Publication>(`/v1/publications/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deletePublication(id: string) {
  return apiFetch<{ deleted_publication: string; deleted_chunks: number; deleted_claims: number }>(
    `/v1/publications/${id}`,
    { method: 'DELETE' },
  )
}

export function updateClaim(
  id: string,
  payload: Partial<{
    claim_text: string
    claim_type: string
    subject_entity: string
    predicate: string
    object_entity: string
    confidence_score: number
    evidence_strength: number
  }>,
) {
  return apiFetch<Claim>(`/v1/knowledge/claims/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteClaim(id: string) {
  return apiFetch<{ deleted_claim: string }>(`/v1/knowledge/claims/${id}`, { method: 'DELETE' })
}

export function exportGraphJson() {
  return apiFetch<GraphData>('/v1/export/graph.json')
}

export function exportSearchCsvUrl(query: string, topK = 12) {
  // Возвращает endpoint, который скачает CSV. Используется через form-based POST.
  return { url: '/v1/export/search.csv', body: { query, top_k: topK } }
}

export function getActivationKeys(question: string) {
  return apiFetch<Activation>('/v1/activation/keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

function postSearch(path: string, query: string, topK: number) {
  return apiFetch<{ items: SearchHit[]; weights?: Record<string, number>; activation?: Activation }>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k: topK }),
  })
}

export function searchKeyword(query: string, topK = 6) {
  return postSearch('/v1/search/keyword', query, topK)
}

export function searchSemantic(query: string, topK = 6) {
  return postSearch('/v1/search/semantic', query, topK)
}

export function searchGraph(query: string, topK = 6) {
  return postSearch('/v1/search/graph', query, topK)
}

export function searchHybrid(query: string, topK = 6) {
  return postSearch('/v1/search/hybrid', query, topK)
}

export function askWithEvidence(question: string, language: Locale, topK = 5) {
  return apiFetch<RagAnswer>('/v1/rag/ask-with-evidence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK, language }),
  })
}

export function evaluateRagAnswer(answerId: string) {
  return apiFetch<Evaluation>(`/v1/evaluation/rag-answer/${answerId}`, { method: 'POST' })
}

export function listRagAnswers(limit = 50) {
  return list<RagAnswer>(`/v1/rag/answers?limit=${limit}`)
}

export function listEvaluations() {
  return list<Evaluation>('/v1/evaluation/records')
}

export function evaluationAggregate() {
  return apiFetch<{ total: number; averages: Record<string, number> }>('/v1/evaluation/aggregate')
}

export function listFeedbackEvents() {
  return list<FeedbackEvent>('/v1/feedback/events')
}

export function submitFeedback(input: {
  target_id: string
  signal: 'positive' | 'review_required' | 'neutral'
  weight_delta?: number
  event_type?: string
  payload?: Record<string, unknown>
}) {
  return apiFetch<FeedbackEvent>('/v1/feedback/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: input.event_type ?? 'user_signal',
      target_id: input.target_id,
      signal: input.signal,
      weight_delta: input.weight_delta ?? (input.signal === 'positive' ? 0.03 : input.signal === 'review_required' ? -0.05 : 0.0),
      payload: input.payload ?? {},
      apply_now: true,
    }),
  })
}

export function applyPendingFeedback() {
  return apiFetch<{ applied: number; skipped: number }>('/v1/feedback/apply-pending', { method: 'POST' })
}

export function listReviewQueue() {
  return apiFetch<{ items: ReviewItem[] }>('/v1/review/queue')
}

export function resolveReviewItem(reviewId: string, action: 'approve' | 'reject' | 'edit', note?: string) {
  return apiFetch<ReviewItem>(`/v1/review/queue/${reviewId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, note }),
  })
}
