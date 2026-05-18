import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'

import type { Labels } from '../../shared/i18n/dictionary'
import { filterLabel, nodeLabel } from '../../shared/i18n/labels'
import { Empty, PanelTitle, Score } from '../../shared/ui/Primitives'
import type { GraphData, GraphEdge, GraphNode, Locale, NodeFilter } from '../../shared/types/scientific-kb'
import { buildBrainGraph } from './model/buildBrainGraph'
import { BrainGraph3D, type BrainGraph3DHandle } from './BrainGraph3D'
import { NodePipeline } from './NodePipeline'
import { RelationsBlock } from './RelationsBlock'

const FOCUS_DIRECTIONS: Array<{ value: 'forward' | 'backward' | 'both'; label: { ru: string; en: string }; title: { ru: string; en: string } }> = [
  {
    value: 'both',
    label: { ru: '↔ всё связанное', en: '↔ all related' },
    title: { ru: 'По стрелкам и против — любая связь', en: 'Follow edges in both directions' },
  },
  {
    value: 'forward',
    label: { ru: '→ исходящие', en: '→ outgoing' },
    title: { ru: 'Только по стрелкам: что узел порождает / влияет на', en: 'Forward only: what this node produces / influences' },
  },
  {
    value: 'backward',
    label: { ru: '← входящие', en: '← incoming' },
    title: { ru: 'Только против стрелок: что ведёт к узлу / влияет на него', en: 'Backward only: what leads to / influences this node' },
  },
]

// Канвас можно делать большим — пользователь может растянуть его на 2 экрана.
const MIN_CANVAS_HEIGHT = 360
const MAX_CANVAS_HEIGHT = 2200
const DEFAULT_CANVAS_HEIGHT = 680

// Опции в дропдауне "Сколько узлов". 'all' = без ограничения.
const NODE_LIMIT_OPTIONS: Array<number | 'all'> = [100, 200, 500, 1000, 2000, 'all']
const DEFAULT_NODE_LIMIT: number | 'all' = 500

const WEIGHT_HELP = {
  ru: 'Вес связи показывает силу зависимости между сущностями. Чем выше вес, тем важнее эта связь для построения маршрута обучения и рекомендаций.',
  en: 'Edge weight reflects how strong the dependency between two entities is. Higher weight means a more important link in the learning path.',
}

const HOTKEYS = {
  ru: [
    { key: 'колесо мыши', text: 'масштаб (zoom)' },
    { key: 'левая кнопка', text: 'вращение' },
    { key: 'правая кнопка', text: 'перемещение' },
    { key: 'клик по узлу', text: 'показать только связанные (фокус)' },
    { key: 'кнопка «Весь граф»', text: 'выйти из режима фокуса' },
    { key: 'двойной клик по нижнему краю', text: 'сбросить высоту' },
  ],
  en: [
    { key: 'mouse wheel', text: 'zoom' },
    { key: 'left button', text: 'rotate' },
    { key: 'right button', text: 'pan' },
    { key: 'node click', text: 'focus on related nodes' },
    { key: '«Show all» button', text: 'exit focus mode' },
    { key: 'dbl-click bottom edge', text: 'reset height' },
  ],
}

// Направление обхода для фокус-режима:
//   forward  — только по стрелкам (descendant'ы / то, что узел порождает)
//   backward — только против стрелок (ancestor'ы / то, что ведёт к узлу)
//   both     — игнорируем направление (всё, что хоть как-то связано) — default
export type FocusDirection = 'forward' | 'backward' | 'both'

// BFS по графу с учётом направления и максимальной глубины.
// На вход — два списка соседей (исходящие и входящие).
// maxDepth: число hop'ов от rootId; Infinity = транзитивная замыкание.
// Возвращает множество достижимых id'шников.
function bfsConnected(
  rootId: string,
  outgoing: Map<string, string[]>,
  incoming: Map<string, string[]>,
  direction: FocusDirection,
  maxDepth: number,
): Set<string> {
  const visited = new Set<string>([rootId])
  // Очередь хранит пары [id, depth].
  const queue: Array<[string, number]> = [[rootId, 0]]
  while (queue.length) {
    const [current, depth] = queue.shift() as [string, number]
    if (depth >= maxDepth) continue
    const neighbors: string[] = []
    if (direction !== 'backward') {
      const out = outgoing.get(current)
      if (out) neighbors.push(...out)
    }
    if (direction !== 'forward') {
      const inc = incoming.get(current)
      if (inc) neighbors.push(...inc)
    }
    for (const n of neighbors) {
      if (!visited.has(n)) {
        visited.add(n)
        queue.push([n, depth + 1])
      }
    }
  }
  return visited
}

export function GraphPage({
  t,
  locale,
  graph,
  filter,
  spacing,
  canvasHeight,
  selectedNodeId,
  selectedNode,
  onFilter,
  onSpacing,
  onCanvasHeight,
  onSelect,
}: {
  t: Labels
  locale: Locale
  graph: GraphData
  filter: NodeFilter
  spacing: number
  canvasHeight: number
  selectedNodeId: string
  selectedNode?: GraphNode
  onFilter: (filter: NodeFilter) => void
  onSpacing: (spacing: number) => void
  onCanvasHeight: (height: number) => void
  onSelect: (id: string) => void
}) {
  const [panelOpen, setPanelOpen] = useState(true)
  const [showEdges, setShowEdges] = useState(true)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  // Сколько узлов показывать в обычном режиме (когда фокус не активен).
  // Топ-N по степени (в первую очередь самые связные узлы).
  const [nodeLimit, setNodeLimit] = useState<number | 'all'>(DEFAULT_NODE_LIMIT)

  // Фокус-режим: после клика по узлу графа показываем только то, что с ним
  // связано (напрямую или транзитивно). Сбрасывается кнопкой "Весь граф".
  const [focusedNodeId, setFocusedNodeId] = useState<string>('')
  // Направление BFS в фокус-режиме. По умолчанию 'both' = и по стрелкам,
  // и против. Граф ориентированный — пользователь может выбрать
  // только outgoing или только incoming.
  const [focusDirection, setFocusDirection] = useState<'forward' | 'backward' | 'both'>('both')
  // Глубина BFS (число hop'ов). Граф плотно связный — без ограничения
  // подграф ≈ весь граф. По умолчанию 2 hop'а — это «ближайшее окружение».
  // Infinity = транзитивное замыкание (как раньше).
  const [focusDepth, setFocusDepth] = useState<number>(2)

  const brainRef = useRef<BrainGraph3DHandle>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)
  // dragState — стартовые Y/высота на момент mousedown по handle'у.
  const dragState = useRef<{ startY: number; startHeight: number } | null>(null)

  // Если выбранный узел исчез из графа (например, обновили данные), сбрасываем фокус.
  useEffect(() => {
    if (focusedNodeId && !graph.nodes.some((n) => n.id === focusedNodeId)) {
      setFocusedNodeId('')
    }
  }, [graph.nodes, focusedNodeId])

  // ── Adjacency maps для BFS (ориентированный граф!) ──────────────────
  // Храним отдельно outgoing (source → targets) и incoming (target → sources).
  // BFS использует ту или обе карты в зависимости от focusDirection.
  // Перестраивается только при изменении edges. На 3k рёбер — <5ms.
  const { outgoing, incoming } = useMemo(() => {
    const out = new Map<string, string[]>()
    const inc = new Map<string, string[]>()
    for (const edge of graph.edges) {
      const o = out.get(edge.source) ?? []
      o.push(edge.target)
      out.set(edge.source, o)
      const i = inc.get(edge.target) ?? []
      i.push(edge.source)
      inc.set(edge.target, i)
    }
    return { outgoing: out, incoming: inc }
  }, [graph.edges])

  // Степень узла — нужна для top-N сортировки в обычном режиме.
  const degree = useMemo(() => {
    const map = new Map<string, number>()
    for (const edge of graph.edges) {
      map.set(edge.source, (map.get(edge.source) ?? 0) + 1)
      map.set(edge.target, (map.get(edge.target) ?? 0) + 1)
    }
    return map
  }, [graph.edges])

  // ── Главный фильтрующий шаг: focus + limit ──────────────────────────
  // Возвращает урезанный GraphData, который пойдёт в buildBrainGraph и в 3D.
  const displayGraph: GraphData = useMemo(() => {
    let nodes: GraphNode[] = graph.nodes
    let edges: GraphEdge[] = graph.edges

    if (focusedNodeId) {
      // BFS с учётом направления и глубины — оставляем только узлы,
      // достижимые из focusedNodeId за ≤ focusDepth шагов в выбранном направлении.
      const reachable = bfsConnected(focusedNodeId, outgoing, incoming, focusDirection, focusDepth)
      nodes = nodes.filter((n) => reachable.has(n.id))
      // Для рёбер: оставляем те, у которых оба конца входят в подграф,
      // И само ребро согласовано с направлением (если выбран forward — рёбра
      // строго от ancestor'а к descendant'у; для both — все).
      edges = edges.filter((e) => {
        if (!reachable.has(e.source) || !reachable.has(e.target)) return false
        return true
      })
    } else if (nodeLimit !== 'all' && nodes.length > nodeLimit) {
      // Топ-N узлов по степени → берём только их + их рёбра.
      const sorted = [...nodes].sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0))
      const keep = new Set(sorted.slice(0, nodeLimit).map((n) => n.id))
      nodes = nodes.filter((n) => keep.has(n.id))
      edges = edges.filter((e) => keep.has(e.source) && keep.has(e.target))
    }

    return { nodes, edges, summary: graph.summary }
  }, [graph.nodes, graph.edges, graph.summary, focusedNodeId, focusDirection, focusDepth, outgoing, incoming, nodeLimit, degree])

  // buildBrainGraph переехал внутрь GraphPage чтобы могла отрабатывать
  // на отфильтрованном (focus/limit) графе.
  const brainGraph = useMemo(
    () => buildBrainGraph(displayGraph, filter, spacing),
    [displayGraph, filter, spacing],
  )

  // Связи выбранного узла (или топ-N по весу, если ничего не выбрано).
  const detailEdges = useMemo(() => {
    const list = selectedNode
      ? graph.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
      : [...graph.edges].sort((left, right) => (right.weight || 0) - (left.weight || 0))
    return list.slice(0, 8)
  }, [graph.edges, selectedNode])

  // ── Resize канваса (drag нижнего края) ───────────────────────────────
  const handleMouseMove = useCallback(
    (event: MouseEvent) => {
      const state = dragState.current
      if (!state) return
      const delta = event.clientY - state.startY
      const next = Math.max(MIN_CANVAS_HEIGHT, Math.min(MAX_CANVAS_HEIGHT, state.startHeight + delta))
      onCanvasHeight(next)
    },
    [onCanvasHeight],
  )

  const handleMouseUp = useCallback(() => {
    if (!dragState.current) return
    dragState.current = null
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }, [])

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [handleMouseMove, handleMouseUp])

  const beginResize = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.stopPropagation()
      const startHeight = canvasHeight
      dragState.current = { startY: event.clientY, startHeight }
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'ns-resize'
    },
    [canvasHeight],
  )

  const onDoubleClickReset = useCallback(() => {
    onCanvasHeight(DEFAULT_CANVAS_HEIGHT)
  }, [onCanvasHeight])

  // ── Toolbar actions ──────────────────────────────────────────────────
  const handleCenterOnSelected = useCallback(() => {
    brainRef.current?.centerOn(selectedNodeId || focusedNodeId || undefined)
  }, [selectedNodeId, focusedNodeId])

  const handleResetCamera = useCallback(() => {
    brainRef.current?.resetCamera()
  }, [])

  const handleResetFocus = useCallback(() => {
    setFocusedNodeId('')
    // После выхода из фокуса возвращаем камеру в дефолт, чтобы пользователь
    // снова видел весь граф.
    setTimeout(() => brainRef.current?.resetCamera(), 50)
  }, [])

  // Клик по узлу: открываем панель свойств И активируем фокус-режим.
  // Если уже в фокусе и пользователь кликает по узлу внутри подграфа —
  // переключаем фокус на новый узел.
  const handleNodeClick = useCallback(
    (id: string) => {
      onSelect(id)
      setFocusedNodeId(id)
    },
    [onSelect],
  )

  // Имя узла лейбла в правой панели может быть очень длинным (claim_text);
  // отделяем человеко-читаемый "тип" в подзаголовок и поясняем технический
  // источник в раскрывающемся "Дополнительно".
  const technicalFields = useMemo(() => {
    if (!selectedNode) return [] as Array<{ label: string; value: string }>
    const fields: Array<{ label: string; value: string }> = []
    fields.push({ label: 'ID', value: selectedNode.id })
    if (selectedNode.kind) fields.push({ label: locale === 'ru' ? 'Тип (raw)' : 'Type (raw)', value: selectedNode.kind })
    if (selectedNode.publication_id) fields.push({ label: locale === 'ru' ? 'Публикация' : 'Publication', value: selectedNode.publication_id })
    if (selectedNode.research_field) fields.push({ label: locale === 'ru' ? 'Область' : 'Field', value: selectedNode.research_field })
    if (selectedNode.claim_type) fields.push({ label: locale === 'ru' ? 'Тип утверждения' : 'Claim type', value: selectedNode.claim_type })
    if (selectedNode.status) fields.push({ label: locale === 'ru' ? 'Статус' : 'Status', value: selectedNode.status })
    return fields
  }, [selectedNode, locale])

  // Узел, на котором сейчас фокус (для баннера).
  const focusedNode = useMemo(
    () => (focusedNodeId ? graph.nodes.find((n) => n.id === focusedNodeId) : undefined),
    [graph.nodes, focusedNodeId],
  )

  return (
    <main className="graph-page">
      <section className="graph-toolbar panel">
        <div className="graph-title">
          <h1>{locale === 'ru' ? '3D мозг знаний' : '3D knowledge brain'}</h1>
          <span>
            {locale === 'ru' ? 'Показано' : 'Shown'}: {displayGraph.nodes.length}/{graph.nodes.length}
            {' · '}
            {locale === 'ru' ? 'связи' : 'edges'}: {displayGraph.edges.length}/{graph.edges.length}
          </span>
        </div>

        <div className="filters" role="group" aria-label={locale === 'ru' ? 'Фильтр по типу' : 'Filter by type'}>
          {(['all', 'Publication', 'ScientificClaim', 'Entity'] as NodeFilter[]).map((item) => (
            <button className={filter === item ? 'active' : ''} key={item} onClick={() => onFilter(item)}>
              {filterLabel(item, t)}
            </button>
          ))}
        </div>

        {/* Селектор количества отображаемых узлов. Disabled в режиме фокуса —
            в нём граф уже ограничен подмножеством связанных узлов. */}
        <label className="graph-limit">
          <span>{locale === 'ru' ? 'Узлов' : 'Nodes'}</span>
          <select
            value={String(nodeLimit)}
            disabled={Boolean(focusedNodeId)}
            onChange={(event) => {
              const raw = event.target.value
              setNodeLimit(raw === 'all' ? 'all' : Number(raw))
            }}
            title={
              focusedNodeId
                ? (locale === 'ru' ? 'Недоступно в режиме фокуса' : 'Disabled in focus mode')
                : (locale === 'ru' ? 'Сколько узлов показывать (топ-N по числу связей)' : 'How many nodes to show (top-N by degree)')
            }
          >
            {NODE_LIMIT_OPTIONS.map((option) => (
              <option key={String(option)} value={String(option)}>
                {option === 'all' ? (locale === 'ru' ? 'Все' : 'All') : option}
              </option>
            ))}
          </select>
        </label>

        <label className="graph-density">
          <span>{locale === 'ru' ? 'Размах' : 'Spread'}</span>
          <input
            type="range"
            min="160"
            max="620"
            step="20"
            value={spacing}
            onChange={(event) => onSpacing(Number(event.target.value))}
          />
        </label>

        <div className="graph-actions">
          <button type="button" onClick={handleCenterOnSelected} title={locale === 'ru' ? 'Центрировать камеру на выбранном узле' : 'Center camera on selected node'}>
            {locale === 'ru' ? 'Центрировать' : 'Center'}
          </button>
          <button type="button" onClick={handleResetCamera} title={locale === 'ru' ? 'Сбросить положение камеры' : 'Reset camera'}>
            {locale === 'ru' ? 'Сбросить вид' : 'Reset view'}
          </button>
          <button
            type="button"
            className={showEdges ? 'toggle on' : 'toggle'}
            onClick={() => setShowEdges((value) => !value)}
            title={locale === 'ru' ? 'Скрыть/показать связи между узлами' : 'Toggle edges'}
          >
            {showEdges ? (locale === 'ru' ? 'Связи: вкл' : 'Edges: on') : (locale === 'ru' ? 'Связи: выкл' : 'Edges: off')}
          </button>
          <button
            type="button"
            className={panelOpen ? 'toggle on' : 'toggle'}
            onClick={() => setPanelOpen((value) => !value)}
            title={locale === 'ru' ? 'Скрыть/показать правую панель свойств' : 'Toggle properties panel'}
          >
            {panelOpen ? (locale === 'ru' ? 'Панель: вкл' : 'Panel: on') : (locale === 'ru' ? 'Панель: выкл' : 'Panel: off')}
          </button>
          <button
            type="button"
            className={helpOpen ? 'toggle on' : 'toggle'}
            onClick={() => setHelpOpen((value) => !value)}
            aria-label={locale === 'ru' ? 'Подсказки управления' : 'Controls help'}
            title={locale === 'ru' ? 'Подсказки управления' : 'Controls help'}
          >
            {locale === 'ru' ? 'Как управлять' : 'How to use'}
          </button>
        </div>
      </section>

      {helpOpen && (
        <section className="graph-help panel">
          <b>{locale === 'ru' ? 'Управление графом' : 'Graph controls'}</b>
          <ul>
            {HOTKEYS[locale].map((hint) => (
              <li key={hint.key}>
                <kbd>{hint.key}</kbd>
                <span>{hint.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Баннер активного фокус-режима. Сразу под тулбаром, заметный. */}
      {focusedNodeId && (
        <section className="focus-banner panel" role="status">
          <div className="focus-banner-text">
            <b>{locale === 'ru' ? 'Режим фокуса' : 'Focus mode'}</b>
            <span>
              {locale === 'ru' ? 'Показаны узлы, связанные с' : 'Showing nodes connected to'}{' '}
              <em>{focusedNode?.label ?? focusedNodeId}</em>{' '}
              {locale === 'ru'
                ? `(${displayGraph.nodes.length} узл., ${displayGraph.edges.length} св.)`
                : `(${displayGraph.nodes.length} nodes, ${displayGraph.edges.length} edges)`}
            </span>
          </div>
          {/* Глубина BFS — на плотном графе без неё подграф ≈ весь граф. */}
          <label className="focus-depth" title={locale === 'ru' ? 'Сколько шагов от выбранного узла включать' : 'How many hops from the selected node to include'}>
            <span>{locale === 'ru' ? 'Глубина' : 'Depth'}</span>
            <select
              value={String(focusDepth)}
              onChange={(event) => {
                const raw = event.target.value
                setFocusDepth(raw === 'inf' ? Number.POSITIVE_INFINITY : Number(raw))
              }}
            >
              <option value="1">{locale === 'ru' ? '1 — соседи' : '1 — neighbors'}</option>
              <option value="2">{locale === 'ru' ? '2 — окружение' : '2 — neighborhood'}</option>
              <option value="3">{locale === 'ru' ? '3 — расширенное' : '3 — extended'}</option>
              <option value="inf">{locale === 'ru' ? '∞ — всё' : '∞ — all'}</option>
            </select>
          </label>
          {/* Сегментный переключатель направления BFS — граф ориентированный. */}
          <div
            className="focus-direction"
            role="group"
            aria-label={locale === 'ru' ? 'Направление связей' : 'Edge direction'}
          >
            {FOCUS_DIRECTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={focusDirection === option.value ? 'active' : ''}
                title={option.title[locale]}
                onClick={() => setFocusDirection(option.value)}
              >
                {option.label[locale]}
              </button>
            ))}
          </div>
          <button type="button" className="focus-reset" onClick={handleResetFocus}>
            {locale === 'ru' ? 'Весь граф ←' : '← Show all'}
          </button>
        </section>
      )}

      <section className={panelOpen ? 'graph-grid' : 'graph-grid panel-collapsed'}>
        <div
          ref={canvasRef}
          className="panel graph-canvas brain-canvas resizable-canvas"
          style={{ '--graph-canvas-height': `${canvasHeight}px` } as CSSProperties}
        >
          <BrainGraph3D
            ref={brainRef}
            graph={brainGraph}
            selectedNodeId={selectedNodeId}
            showEdges={showEdges}
            onSelect={handleNodeClick}
          />

          <div className="brain-overlay">
            <b>{locale === 'ru' ? 'Вращайте, приближайте, выбирайте узлы' : 'Rotate, zoom, select nodes'}</b>
            <span>
              {locale === 'ru'
                ? `Высота: ${Math.round(canvasHeight)}px · потяните нижний край`
                : `Height: ${Math.round(canvasHeight)}px · drag the bottom edge`}
            </span>
            {!focusedNodeId && (
              <span>
                {locale === 'ru'
                  ? 'Кликните по узлу, чтобы увидеть только связанные с ним'
                  : 'Click any node to see only related ones'}
              </span>
            )}
          </div>

          <div
            className="canvas-resize-handle bottom"
            role="separator"
            aria-orientation="horizontal"
            aria-label={locale === 'ru' ? 'Изменить высоту' : 'Resize height'}
            title={locale === 'ru' ? 'Потяните, чтобы изменить высоту. Двойной клик — сброс.' : 'Drag to resize. Double-click to reset.'}
            onMouseDown={beginResize}
            onDoubleClick={onDoubleClickReset}
          >
            <span className="grip" />
            <span className="grip-text">
              {locale === 'ru' ? '↕ изменить высоту' : '↕ resize'}
            </span>
          </div>

          {!panelOpen && (
            <button
              type="button"
              className="show-panel-fab"
              onClick={() => setPanelOpen(true)}
              title={locale === 'ru' ? 'Показать панель свойств' : 'Show properties panel'}
            >
              {locale === 'ru' ? 'Свойства →' : 'Properties →'}
            </button>
          )}
        </div>

        {panelOpen && (
          <aside className="panel graph-details">
            <div className="panel-header">
              <PanelTitle title={t.selected} />
              <button
                type="button"
                className="panel-close"
                onClick={() => setPanelOpen(false)}
                aria-label={locale === 'ru' ? 'Скрыть панель' : 'Hide panel'}
                title={locale === 'ru' ? 'Скрыть панель свойств' : 'Hide properties panel'}
              >
                ×
              </button>
            </div>

            {selectedNode ? (
              <div className="node-card">
                <section className="card-section">
                  <b className="node-title">{selectedNode.label}</b>
                  <span className="node-kind">
                    {locale === 'ru' ? 'Тип' : 'Type'}: {nodeLabel(selectedNode.kind, locale)}
                  </span>
                </section>

                {/* Pipeline / provenance — главная новая секция: показывает откуда
                    взят узел (Publication → Chunk → 12 шагов → Claim → Entities). */}
                <NodePipeline node={selectedNode} locale={locale} />

                {(typeof selectedNode.evidence_strength === 'number' ||
                  typeof selectedNode.confidence_score === 'number') && (
                  <section className="card-section">
                    <b className="card-section-title">
                      {locale === 'ru' ? 'Качество данных' : 'Data quality'}
                    </b>
                    {typeof selectedNode.evidence_strength === 'number' && (
                      <Score
                        label={locale === 'ru' ? 'Доказательность' : 'Evidence'}
                        value={selectedNode.evidence_strength}
                      />
                    )}
                    {typeof selectedNode.confidence_score === 'number' && (
                      <Score
                        label={locale === 'ru' ? 'Уверенность' : 'Confidence'}
                        value={selectedNode.confidence_score}
                      />
                    )}
                  </section>
                )}

                {/* Связи: новый человеко-понятный блок с группировкой по типу,
                    словесной силой (сильная/средняя/слабая), направлением. */}
                <RelationsBlock edges={detailEdges} selectedNode={selectedNode} locale={locale} />


                {technicalFields.length > 0 && (
                  <section className="card-section">
                    <button
                      type="button"
                      className="advanced-toggle"
                      onClick={() => setAdvancedOpen((value) => !value)}
                      aria-expanded={advancedOpen}
                    >
                      {advancedOpen
                        ? (locale === 'ru' ? '▼ Дополнительно' : '▼ Advanced')
                        : (locale === 'ru' ? '▶ Дополнительно' : '▶ Advanced')}
                    </button>
                    {advancedOpen && (
                      <dl className="advanced-fields">
                        {technicalFields.map((field) => (
                          <div key={field.label} className="advanced-row">
                            <dt>{field.label}</dt>
                            <dd>{field.value}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </section>
                )}
              </div>
            ) : (
              <Empty text={locale === 'ru' ? 'Выберите узел графа, чтобы увидеть его свойства' : 'Select a node to see its properties'} />
            )}

            {!selectedNode && detailEdges.length > 0 && (
              <RelationsBlock edges={detailEdges} selectedNode={null} locale={locale} />
            )}

            <div className="legend">
              <span><i className="pub" />{t.publications}</span>
              <span><i className="claim" />{t.claims}</span>
              <span><i className="entity" />{t.entities}</span>
            </div>
          </aside>
        )}
      </section>
    </main>
  )
}
