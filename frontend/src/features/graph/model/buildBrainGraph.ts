import * as THREE from 'three'

import type { BrainEdge, BrainGraph, BrainNode, GraphData, GraphEdge, GraphNode, NeuralFiber, NodeFilter } from '../../shared/types/scientific-kb'

export function buildBrainGraph(graph: GraphData, filter: NodeFilter, expansion: number): BrainGraph {
  const visibleNodes = graph.nodes.filter((node) => {
    if (filter === 'all') return true
    if (filter === 'Entity') return node.kind !== 'Publication' && node.kind !== 'ScientificClaim'
    return node.kind === filter
  })
  const ids = new Set(visibleNodes.map((node) => node.id))
  const visibleEdges = graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target))
  const degree = new Map<string, number>()
  for (const edge of visibleEdges) {
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1)
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1)
  }

  const spread = Math.max(0.62, expansion / 260)
  const groups = {
    publications: visibleNodes.filter((node) => node.kind === 'Publication'),
    claims: visibleNodes.filter((node) => node.kind === 'ScientificClaim'),
    entities: visibleNodes.filter((node) => node.kind !== 'Publication' && node.kind !== 'ScientificClaim'),
  }
  const claimRanks = rankClaimDag(groups.claims, visibleEdges)
  const maxClaimRank = Math.max(1, ...Array.from(claimRanks.values()))
  const layerInfo = new Map<string, { layer: number; index: number; total: number }>()
  groups.publications.forEach((node, index) => layerInfo.set(node.id, { layer: -1, index, total: groups.publications.length }))
  groups.claims.forEach((node, index) => {
    const rank = claimRanks.get(node.id) || 0
    layerInfo.set(node.id, { layer: -0.18 + (rank / maxClaimRank) * 0.66, index, total: groups.claims.length })
  })
  groups.entities.forEach((node, index) => layerInfo.set(node.id, { layer: 1, index, total: groups.entities.length }))

  const nodes = visibleNodes.map((node, index): BrainNode => {
    const seed = hashString(node.id)
    const rand = mulberry32(seed)
    const info = layerInfo.get(node.id) || { layer: 0, index, total: visibleNodes.length }
    const [px, py, pz] = dagLayerPosition(info.layer, info.index, info.total, spread, rand)
    const d = degree.get(node.id) || 1
    return {
      ...node,
      color: colorForNode(node),
      degree: d,
      position: [px, py, pz],
      radius: 5.5 + Math.min(11, d * 1.65),
    }
  })
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const edges = visibleEdges.flatMap((edge): BrainEdge[] => {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) return []
    return [{
      ...edge,
      color: colorForEdge(edge.type),
      opacity: edge.type === 'HAS_CLAIM' ? 0.34 : 0.48,
      sourcePosition: source.position,
      targetPosition: target.position,
    }]
  })
  return { nodes, edges, fibers: buildNeuralFibers(nodes, edges, expansion) }
}

function rankClaimDag(claims: GraphNode[], edges: GraphEdge[]) {
  const claimIds = new Set(claims.map((claim) => claim.id))
  const incoming = new Map<string, string[]>()
  for (const claim of claims) incoming.set(claim.id, [])
  for (const edge of edges) {
    if (claimIds.has(edge.source) && claimIds.has(edge.target)) {
      incoming.get(edge.target)?.push(edge.source)
    }
  }
  const ranks = new Map<string, number>()
  const visit = (id: string, trail = new Set<string>()): number => {
    if (ranks.has(id)) return ranks.get(id) || 0
    if (trail.has(id)) return 0
    trail.add(id)
    const rank = Math.max(0, ...((incoming.get(id) || []).map((source) => visit(source, trail) + 1)))
    trail.delete(id)
    ranks.set(id, rank)
    return rank
  }
  for (const claim of claims) visit(claim.id)
  return ranks
}

function dagLayerPosition(
  layer: number,
  index: number,
  total: number,
  spread: number,
  rand: () => number
): [number, number, number] {
  const safeTotal = Math.max(1, total)
  const columns = Math.max(1, Math.ceil(Math.sqrt(safeTotal)))
  const row = Math.floor(index / columns)
  const col = index % columns
  const rows = Math.max(1, Math.ceil(safeTotal / columns))
  const x = layer * 330 * spread + (rand() - 0.5) * 28
  const y = ((row - (rows - 1) / 2) * 82 + (rand() - 0.5) * 22) * (0.74 + spread * 0.26)
  const z = ((col - (columns - 1) / 2) * 92 + (rand() - 0.5) * 42) * spread
  return [x, y, z]
}

function buildNeuralFibers(nodes: BrainNode[], edges: BrainEdge[], expansion: number): NeuralFiber[] {
  const fibers: NeuralFiber[] = []
  const spread = Math.max(0.62, expansion / 260)
  const branchesPerNode = Math.max(3, Math.round(9 - expansion / 105))
  for (const node of nodes) {
    const rand = mulberry32(hashString(node.id + 'fiber'))
    for (let branch = 0; branch < branchesPerNode; branch += 1) {
      const length = (55 + rand() * 105) * Math.sqrt(spread)
      const steps = 4 + Math.floor(rand() * 4)
      const angle = rand() * Math.PI * 2
      const lift = (rand() - 0.5) * 0.9
      const points: Array<[number, number, number]> = [node.position]
      let current: [number, number, number] = [...node.position]
      for (let step = 1; step <= steps; step += 1) {
        const spread = length * (step / steps)
        current = [
          current[0] + Math.cos(angle + step * 0.48) * spread * 0.16 + (rand() - 0.5) * 20,
          current[1] + lift * spread * 0.2 + Math.sin(step * 1.7 + angle) * 10,
          current[2] + Math.sin(angle + step * 0.36) * spread * 0.14 + (rand() - 0.5) * 26,
        ]
        points.push(current)
      }
      fibers.push({ color: node.color, opacity: 0.14 + rand() * 0.18, points })
    }
  }
  for (const edge of edges) {
    const curve = makeCurve(edge.sourcePosition, edge.targetPosition, hashString(edge.source + edge.target))
    fibers.push({
      color: edge.color,
      opacity: 0.22,
      points: curve.getPoints(18).map((point) => [point.x, point.y, point.z]),
    })
  }
  return fibers
}

export function makeCurve(from: [number, number, number], to: [number, number, number], seed: number) {
  const rand = mulberry32(seed)
  const a = new THREE.Vector3(...from)
  const b = new THREE.Vector3(...to)
  const mid = a.clone().lerp(b, 0.5)
  mid.x += (rand() - 0.5) * 70
  mid.y += (rand() - 0.5) * 55
  mid.z += 38 + (rand() - 0.5) * 90
  return new THREE.CatmullRomCurve3([a, mid, b])
}

export function makeDust(count: number) {
  const positions: number[] = []
  const colors: number[] = []
  const palette = [0x22d3ee, 0xf472b6, 0xa3e635, 0xfacc15, 0x60a5fa, 0xc084fc]
  const color = new THREE.Color()
  const rand = mulberry32(9301)
  for (let index = 0; index < count; index += 1) {
    const theta = rand() * Math.PI * 2
    const z = rand() * 2 - 1
    const r = Math.sqrt(1 - z * z)
    const shell = 0.55 + rand() * 0.55
    positions.push(Math.cos(theta) * r * 430 * shell, z * 215 * shell, Math.sin(theta) * r * 185 * shell)
    color.setHex(palette[Math.floor(rand() * palette.length)])
    colors.push(color.r, color.g, color.b)
  }
  return { positions, colors }
}

function colorForNode(node: GraphNode) {
  if (node.kind === 'Publication') return 0x38bdf8
  if (node.kind === 'ScientificClaim') {
    if (node.claim_type === 'limitation') return 0xf59e0b
    if (node.claim_type === 'contradiction_candidate') return 0xfb4bd8
    return 0x5eead4
  }
  if (node.kind === 'Limitation') return 0xf97316
  if (node.kind === 'Metric') return 0xfacc15
  if (node.kind === 'Tool') return 0xa78bfa
  return 0x84cc16
}

function colorForEdge(type: string) {
  if (type === 'contradicts') return 0xff3b8d
  if (type === 'limits') return 0xfb923c
  if (type === 'supports' || type === 'HAS_CLAIM') return 0x2dd4bf
  if (type === 'SUBJECT' || type === 'OBJECT') return 0x8b5cf6
  return 0x7dd3fc
}

export function hashString(input: string) {
  let hash = 2166136261
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function mulberry32(seed: number) {
  return () => {
    let value = seed += 0x6D2B79F5
    value = Math.imul(value ^ value >>> 15, value | 1)
    value ^= value + Math.imul(value ^ value >>> 7, value | 61)
    return ((value ^ value >>> 14) >>> 0) / 4294967296
  }
}
