import type { Labels } from './dictionary'
import type { Locale, NodeFilter } from '../types/scientific-kb'

export function defaultSteps() {
  return ['upload', 'text_extraction', 'semantic_chunking', 'entity_extraction', 'claim_extraction_v2', 'weighted_graph', 'ready']
    .map((name) => ({ name, status: 'completed' }))
}

export function stepName(name: string, locale: Locale) {
  const ru: Record<string, string> = {
    upload: 'Файл',
    text_extraction: 'Текст',
    semantic_chunking: 'Фрагменты',
    entity_extraction: 'Понятия',
    claim_extraction_v2: 'Факты',
    weighted_graph: 'Граф',
    ready: 'Готово',
  }
  const en: Record<string, string> = {
    upload: 'File',
    text_extraction: 'Text',
    semantic_chunking: 'Fragments',
    entity_extraction: 'Terms',
    claim_extraction_v2: 'Facts',
    weighted_graph: 'Graph',
    ready: 'Ready',
  }
  return (locale === 'ru' ? ru : en)[name] ?? name
}

export function statusLabel(status: string, t: Labels) {
  if (status === 'ready') return t.ready
  if (status === 'uploaded') return t.uploaded
  if (status === 'error') return t.error
  return status
}

export function kindLabel(kind: string, locale: Locale) {
  if (locale === 'ru') return kind === 'claim' ? 'факт' : kind === 'chunk' ? 'фрагмент' : 'понятие'
  return kind === 'claim' ? 'fact' : kind === 'chunk' ? 'fragment' : 'term'
}

export function claimTypeLabel(type: string, locale: Locale) {
  const ru: Record<string, string> = {
    experimental_result: 'результат',
    limitation: 'ограничение',
    method_description: 'метод',
    conclusion: 'вывод',
    contradiction_candidate: 'противоречие',
  }
  const en: Record<string, string> = {
    experimental_result: 'result',
    limitation: 'limitation',
    method_description: 'method',
    conclusion: 'conclusion',
    contradiction_candidate: 'contradiction',
  }
  return (locale === 'ru' ? ru : en)[type] ?? type
}

export function metricLabel(metric: string, locale: Locale) {
  const ru: Record<string, string> = {
    faithfulness: 'источники',
    source_coverage: 'покрытие',
    hallucination_rate: 'риск',
    answer_completeness: 'полнота',
    citation_correctness: 'цитаты',
    limitation_honesty: 'честность',
  }
  const en: Record<string, string> = {
    faithfulness: 'sources',
    source_coverage: 'coverage',
    hallucination_rate: 'risk',
    answer_completeness: 'complete',
    citation_correctness: 'citations',
    limitation_honesty: 'honesty',
  }
  return (locale === 'ru' ? ru : en)[metric] ?? metric
}

export function filterLabel(filter: NodeFilter, t: Labels) {
  if (filter === 'all') return t.all
  if (filter === 'Publication') return t.publications
  if (filter === 'ScientificClaim') return t.claims
  return t.entities
}

export function nodeLabel(kind: string, locale: Locale) {
  if (kind === 'Publication') return locale === 'ru' ? 'Публикация' : 'Publication'
  if (kind === 'ScientificClaim') return locale === 'ru' ? 'Факт' : 'Fact'
  return locale === 'ru' ? 'Понятие' : 'Term'
}
