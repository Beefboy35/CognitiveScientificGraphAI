import { useMemo, useState } from 'react'

import type { GraphEdge, GraphNode, Locale } from '../../shared/types/scientific-kb'

// ─────────────────────────────────────────────────────────────────────────────
// Понятные ярлыки для типов связей. Технические `SUPPORTS/EXTENDS/LIMITS/...`
// заменяются на человеческий язык — пользователю не нужно знать терминологию.
//
// Каждый тип имеет:
//   • verb — глагол, описывающий действие в активном залоге;
//   • passive — пассивный залог (для входящих связей: «поддерживается X»);
//   • color — цветовая категория для chip'а;
//   • icon — emoji-маркер.
// ─────────────────────────────────────────────────────────────────────────────
const RELATION_LABELS: Record<
  string,
  {
    verb: { ru: string; en: string }
    passive: { ru: string; en: string }
    color: 'green' | 'red' | 'orange' | 'blue' | 'grey'
    icon: string
    help: { ru: string; en: string }
  }
> = {
  supports: {
    verb: { ru: 'подтверждает', en: 'supports' },
    passive: { ru: 'подтверждается', en: 'supported by' },
    color: 'green',
    icon: '✓',
    help: {
      ru: 'Другая публикация утверждает то же самое — независимое подтверждение факта.',
      en: 'Another publication makes the same claim — independent confirmation.',
    },
  },
  contradicts: {
    verb: { ru: 'противоречит', en: 'contradicts' },
    passive: { ru: 'оспаривается', en: 'contradicted by' },
    color: 'red',
    icon: '⚠',
    help: {
      ru: 'Другая публикация утверждает обратное — есть конфликт, который требует внимания.',
      en: 'Another publication makes an opposing claim — conflict needs attention.',
    },
  },
  extends: {
    verb: { ru: 'развивает', en: 'extends' },
    passive: { ru: 'развит в', en: 'extended by' },
    color: 'blue',
    icon: '→',
    help: {
      ru: 'Это утверждение опирается на другое и добавляет новое: расширение или применение метода.',
      en: 'Builds on another claim — adds a parameter or applies to a new case.',
    },
  },
  limits: {
    verb: { ru: 'ограничивает', en: 'limits' },
    passive: { ru: 'ограничен в', en: 'limited by' },
    color: 'orange',
    icon: '⚠',
    help: {
      ru: 'Один claim указывает условия, при которых другой перестаёт работать или работает хуже.',
      en: 'One claim describes conditions under which another fails or works worse.',
    },
  },
}

// Шкала силы связи. Вес 0..1 → словесная категория.
// 0.0-0.4 — слабая связь, 0.4-0.7 — средняя, 0.7-1.0 — сильная.
function strengthLabel(weight: number, locale: Locale): { text: string; tone: 'low' | 'mid' | 'high' } {
  if (weight >= 0.7) return { text: locale === 'ru' ? 'сильная' : 'strong', tone: 'high' }
  if (weight >= 0.4) return { text: locale === 'ru' ? 'средняя' : 'medium', tone: 'mid' }
  return { text: locale === 'ru' ? 'слабая' : 'weak', tone: 'low' }
}

const STRENGTH_HELP = {
  ru: 'Сила связи показывает, насколько уверенно система установила эту связь. Сильная — точное совпадение или прямое цитирование. Слабая — связь обнаружена эвристикой и может быть ошибкой.',
  en: 'Strength reflects how confidently the system established this link. Strong = exact match or direct citation. Weak = heuristic guess, might be wrong.',
}

type RelationsBlockProps = {
  edges: GraphEdge[]
  selectedNode: GraphNode | null
  locale: Locale
}

export function RelationsBlock({ edges, selectedNode, locale }: RelationsBlockProps) {
  // Группируем рёбра по их «человеческому» relation-type. Для входящих связей
  // (target = selected) меняем смысл: «X поддерживает меня» → «меня поддерживает X».
  const grouped = useMemo(() => {
    const groups: Record<string, Array<{ edge: GraphEdge; isIncoming: boolean; otherId: string }>> = {}
    for (const edge of edges) {
      const type = (edge.type || '').toLowerCase()
      if (!RELATION_LABELS[type]) continue
      const isIncoming = selectedNode != null && edge.target === selectedNode.id
      const otherId = isIncoming ? edge.source : edge.target
      groups[type] = groups[type] || []
      groups[type].push({ edge, isIncoming, otherId })
    }
    return groups
  }, [edges, selectedNode])

  const totalShown = Object.values(grouped).reduce((sum, items) => sum + items.length, 0)

  if (totalShown === 0) {
    return (
      <section className="relations-block">
        <div className="relations-header">
          <b>{locale === 'ru' ? 'Связи с другими утверждениями' : 'Links to other claims'}</b>
        </div>
        <p className="relations-empty">
          {locale === 'ru'
            ? 'У этого утверждения нет явных связей с другими в базе. Это нормально — связь создаётся только если есть доказательство.'
            : 'This claim has no explicit links to others. That is fine — links are added only when evidence exists.'}
        </p>
      </section>
    )
  }

  // Порядок секций: SUPPORTS → EXTENDS → LIMITS → CONTRADICTS
  // (от позитивных к проблемным — наиболее полезно для пользователя).
  const order = ['supports', 'extends', 'limits', 'contradicts']

  return (
    <section className="relations-block">
      <div className="relations-header">
        <b>{locale === 'ru' ? 'Связи с другими утверждениями' : 'Links to other claims'}</b>
        <span className="relations-count">
          {totalShown} {locale === 'ru' ? 'связ.' : 'links'}
        </span>
      </div>

      {order.map((type) => {
        const items = grouped[type]
        if (!items || items.length === 0) return null
        const meta = RELATION_LABELS[type]
        return (
          <RelationGroup
            key={type}
            type={type}
            items={items}
            meta={meta}
            locale={locale}
            selectedLabel={selectedNode?.label || ''}
          />
        )
      })}
    </section>
  )
}

function RelationGroup({
  type,
  items,
  meta,
  locale,
  selectedLabel,
}: {
  type: string
  items: Array<{ edge: GraphEdge; isIncoming: boolean; otherId: string }>
  meta: (typeof RELATION_LABELS)[string]
  locale: Locale
  selectedLabel: string
}) {
  const [expanded, setExpanded] = useState(items.length <= 3)
  const visible = expanded ? items : items.slice(0, 3)

  return (
    <div className={`relations-group rel-color-${meta.color}`}>
      <header className="relations-group-header">
        <span className={`relations-chip rel-color-${meta.color}`}>
          <span className="relations-chip-icon" aria-hidden>{meta.icon}</span>
          <span>
            {locale === 'ru'
              ? type === 'supports' ? 'Подтверждения'
              : type === 'contradicts' ? 'Противоречия'
              : type === 'extends' ? 'Развития'
              : 'Ограничения'
              : type.charAt(0).toUpperCase() + type.slice(1)}
          </span>
          <span className="relations-chip-count">{items.length}</span>
        </span>
        <span
          className="relations-help"
          title={meta.help[locale]}
          aria-label={meta.help[locale]}
        >?</span>
      </header>

      <ul className="relations-list">
        {visible.map(({ edge, isIncoming, otherId }, index) => {
          const weight = edge.weight ?? 0
          const strength = strengthLabel(weight, locale)
          const directionVerb = isIncoming ? meta.passive[locale] : meta.verb[locale]
          return (
            <li key={`${type}-${otherId}-${index}`} className="relations-item">
              <div className="relations-item-line">
                <span className="relations-arrow" aria-hidden>
                  {isIncoming ? '←' : '→'}
                </span>
                <span className="relations-other-label" title={otherId}>
                  {locale === 'ru'
                    ? <><em>{selectedLabel ? `«${selectedLabel.slice(0, 40)}${selectedLabel.length > 40 ? '…' : ''}»` : 'это утверждение'}</em> {directionVerb} <em>другое утверждение</em></>
                    : <><em>this claim</em> {directionVerb} <em>another</em></>}
                </span>
              </div>
              <div className="relations-strength">
                <span className={`relations-strength-pill strength-${strength.tone}`}>
                  {strength.text}
                </span>
                <span
                  className="relations-strength-help"
                  title={STRENGTH_HELP[locale]}
                  aria-label={STRENGTH_HELP[locale]}
                >?</span>
                <span className="relations-other-id">{otherId.slice(0, 16)}…</span>
              </div>
              {edge.context && (
                <p className="relations-context" title={edge.context}>
                  {edge.context.length > 130 ? `${edge.context.slice(0, 130)}…` : edge.context}
                </p>
              )}
            </li>
          )
        })}
      </ul>

      {items.length > 3 && (
        <button
          type="button"
          className="relations-toggle"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded
            ? (locale === 'ru' ? 'Скрыть' : 'Hide')
            : (locale === 'ru' ? `Показать ещё ${items.length - 3}` : `Show ${items.length - 3} more`)}
        </button>
      )}
    </div>
  )
}
