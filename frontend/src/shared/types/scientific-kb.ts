export type Locale = 'ru' | 'en'
export type View = 'work' | 'graph' | 'lab' | 'library' | 'entities' | 'claims' | 'evaluation' | 'review'
export type NodeFilter = 'all' | 'Publication' | 'ScientificClaim' | 'Entity'
export type Theme = 'light' | 'dark'

export type Publication = {
  id: string
  title: string
  status: string
  pages: number
  abstract?: string
  authors?: string[]
  year?: number
  metadata?: {
    research_field?: string | null
    author_ids?: string[]
    organizations?: string[]
    cites?: string[]
    cited_by?: string[]
    [key: string]: unknown
  }
}

export type WorkSummary = Partial<{
  publications: number
  claims: number
  entities: number
  relations: number
  authors: number
  organizations: number
  citations: number
  feedback_events: number
  human_review_queue: number
  activation_keys: number
  qdrant_mode: string
  graph_mode: string
  postgres_mode: string
  redis_mode: string
}>

export type Chunk = {
  id: string
  chunk_index: number
  text: string
  page_start: number
  page_end?: number
  section: string
  publication_id?: string
}

export type ClaimType =
  | 'definition'
  | 'method_description'
  | 'experimental_result'
  | 'comparison'
  | 'limitation'
  | 'hypothesis'
  | 'conclusion'
  | 'contradiction_candidate'
  | 'replication_note'

export type Claim = {
  id: string
  claim_text: string
  claim_type: ClaimType | string
  evidence_strength: number
  confidence_score: number
  source_reliability?: number
  publication_id: string
  chunk_id?: string
  subject_entity?: string
  object_entity?: string
  predicate?: string
  metric?: string | null
  value?: string | null
  comparison_target?: string | null
  condition?: string | null
  evidence_text?: string
  page_start?: number
  page_end?: number
  extraction_run_id?: string
}

export type ClaimRelation = {
  id: string
  source_claim_id: string
  target_claim_id: string
  relation_type: 'supports' | 'contradicts' | 'limits' | 'extends'
  weight: number
  confidence_score: number
  evidence_strength: number
  source_reliability?: number
  rationale?: string
}

export type ScientificEntity = {
  id: string
  canonical_name: string
  entity_type: string
  aliases: string[]
  confidence_score: number
  mentions?: Array<{ publication_id: string; chunk_id?: string; page?: number; section?: string; surface?: string }>
}

export type Job = {
  id: string
  publication_id?: string
  extraction_run_id?: string
  status?: string
  steps: Array<{
    name: string
    status: string
    started_at?: string | null
    finished_at?: string | null
    details?: Record<string, unknown>
  }>
  error?: string | null
  created_at?: string
}

export type ScoreBreakdown = Partial<{
  keyword: number
  semantic: number
  graph: number
  activation: number
  claim_confidence: number
  evidence_strength: number
  source_reliability: number
  contradiction_risk: number
  weights: Record<string, number>
}>

export type SearchHit = {
  id: string
  kind: 'chunk' | 'claim' | 'entity'
  score: number
  text: string
  title?: string
  metadata?: Record<string, unknown>
  score_breakdown: ScoreBreakdown
}

export type RagSource = {
  claim_id?: string | null
  publication_id?: string
  publication_title?: string
  chunk_id?: string
  pages?: [number, number] | number[]
  evidence_text?: string
  claim_text?: string | null
  claim_type?: string | null
  score?: number
  score_breakdown?: ScoreBreakdown
  evidence_strength?: number
  confidence_score?: number
  source_reliability?: number
  contradiction_risk?: number
}

export type RagAnswer = {
  id: string
  question: string
  answer: string
  status: 'answered' | 'insufficient_evidence'
  confidence_score: number
  sources: RagSource[]
  used_entities: ScientificEntity[]
  used_claims: Claim[]
  reasoning_trace: string[]
  limitations: string[]
}

export type Evaluation = {
  id?: string
  rag_answer_id?: string
  metrics: Record<string, number>
  feedback_events_created?: string[]
}

export type Activation = {
  question: string
  activation_keys: string[]
  activated_entities: ScientificEntity[]
  activated_claims: Claim[]
  activated_chunks: Chunk[]
}

export type FeedbackEvent = {
  id: string
  event_type: string
  target_id: string
  signal: string
  weight_delta: number
  payload: Record<string, unknown>
  created_at: string
}

export type ReviewItem = {
  id: string
  item_type: string
  item_id: string
  reason: string
  status: string
  created_at: string
  metadata?: Record<string, unknown>
  resolution?: Record<string, unknown>
}

export type GraphNode = {
  id: string
  label: string
  kind: string
  claim_type?: string
  confidence_score?: number
  evidence_strength?: number
  status?: string
  research_field?: string | null
}

export type GraphEdge = {
  source: string
  target: string
  type: string
  weight?: number
  confidence_score?: number
  evidence_strength?: number
  context?: string
}

export type GraphData = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  summary: Record<string, number>
}

export type BrainNode = GraphNode & {
  color: number
  degree: number
  position: [number, number, number]
  radius: number
}

export type BrainEdge = GraphEdge & {
  color: number
  opacity: number
  sourcePosition: [number, number, number]
  targetPosition: [number, number, number]
}

export type NeuralFiber = {
  color: number
  opacity: number
  points: Array<[number, number, number]>
}

export type BrainGraph = {
  nodes: BrainNode[]
  edges: BrainEdge[]
  fibers: NeuralFiber[]
}
