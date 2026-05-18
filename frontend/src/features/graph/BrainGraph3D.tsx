import { useEffect, useImperativeHandle, useRef, forwardRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

import type { BrainGraph, BrainNode } from '../../shared/types/scientific-kb'

// Публичный handle, который позволяет родителю управлять камерой
// без пересоздания сцены (центрировать, сбрасывать масштаб).
export type BrainGraph3DHandle = {
  centerOn: (nodeId?: string) => void
  resetCamera: () => void
}

type Props = {
  graph: BrainGraph
  selectedNodeId: string
  showEdges: boolean
  onSelect: (id: string) => void
}

// LOD thresholds — при большом числе узлов/рёбер выключаем декоративные
// эффекты и снижаем геометрическую детализацию.
const HEAVY_NODE_THRESHOLD = 400
const HEAVY_EDGE_THRESHOLD = 1500
// Импульсы — направляющие точки источник→цель — отключаем когда рёбер слишком
// много (>3500 instance'ов уже даёт заметный CPU-overhead на матрицах).
const PULSE_EDGE_THRESHOLD = 3500
const POINTER_MOVE_THROTTLE_MS = 60

export const BrainGraph3D = forwardRef<BrainGraph3DHandle, Props>(function BrainGraph3D(
  { graph, selectedNodeId, showEdges, onSelect },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null)
  const onSelectRef = useRef(onSelect)
  // Внутренние refs для управления сценой снаружи через handle.
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const nodeIndexRef = useRef<Map<string, BrainNode>>(new Map())
  const selectedRef = useRef<string>(selectedNodeId)

  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    selectedRef.current = selectedNodeId
  }, [selectedNodeId])

  useImperativeHandle(ref, () => ({
    centerOn(nodeId?: string) {
      const camera = cameraRef.current
      const controls = controlsRef.current
      if (!camera || !controls) return
      const targetNode = nodeId ? nodeIndexRef.current.get(nodeId) : null
      const target = targetNode
        ? new THREE.Vector3(...targetNode.position)
        : new THREE.Vector3(0, 0, 0)
      controls.target.copy(target)
      controls.update()
    },
    resetCamera() {
      const camera = cameraRef.current
      const controls = controlsRef.current
      if (!camera || !controls) return
      camera.position.set(0, 80, 760)
      controls.target.set(0, 0, 0)
      controls.update()
    },
  }))

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const nodeCount = graph.nodes.length
    const edgeCount = graph.edges.length
    const heavy = nodeCount > HEAVY_NODE_THRESHOLD || edgeCount > HEAVY_EDGE_THRESHOLD
    const enablePulses = showEdges && edgeCount > 0 && edgeCount <= PULSE_EDGE_THRESHOLD
    // Индекс id → node даёт O(1) lookup в анимационном цикле.
    const nodeIndex = new Map<string, BrainNode>(graph.nodes.map((n) => [n.id, n]))
    nodeIndexRef.current = nodeIndex

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x02040a)
    // Fog отключаем целиком — при отдалении камеры узлы не должны
    // растворяться в фоне (поведение по запросу пользователя).
    scene.fog = null

    const camera = new THREE.PerspectiveCamera(52, 1, 1, 6000)
    camera.position.set(0, 80, 760)
    cameraRef.current = camera

    const renderer = new THREE.WebGLRenderer({
      antialias: !heavy,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: false,
    })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, heavy ? 1 : 1.5))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.autoRotate = !heavy
    controls.autoRotateSpeed = 0.25
    controls.minDistance = 80
    controls.maxDistance = 4500
    controls.zoomSpeed = 1.2
    controlsRef.current = controls

    const brain = new THREE.Group()
    brain.rotation.x = -0.08
    scene.add(brain)

    scene.add(new THREE.AmbientLight(0x426b8f, 1.0))
    if (!heavy) {
      const keyLight = new THREE.PointLight(0x7dd3fc, 1.6, 1500)
      keyLight.position.set(-220, 180, 420)
      scene.add(keyLight)
    }

    // ── INSTANCED nodes ─────────────────────────────────────────────────
    // Один draw call для всех узлов. Per-instance цвет задаётся через
    // setColorAt() — Three.js автоматически добавляет instanceColor uniform
    // в шейдер. ВАЖНО: vertexColors=false (иначе шейдер ждёт color-атрибут
    // в геометрии и без него возвращает чёрный).
    const nodeGeometry = new THREE.SphereGeometry(1, heavy ? 10 : 16, heavy ? 8 : 12)
    const nodeMaterial = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.96 })
    const instancedNodes = new THREE.InstancedMesh(nodeGeometry, nodeMaterial, Math.max(1, nodeCount))
    instancedNodes.instanceMatrix.setUsage(THREE.DynamicDrawUsage)

    const tmpObj = new THREE.Object3D()
    const tmpColor = new THREE.Color()
    const nodeIdByInstance: string[] = new Array(nodeCount)
    const baseScales = new Float32Array(nodeCount)

    for (let i = 0; i < nodeCount; i += 1) {
      const node = graph.nodes[i]
      nodeIdByInstance[i] = node.id
      baseScales[i] = node.radius
      tmpObj.position.set(...node.position)
      tmpObj.scale.setScalar(node.radius)
      tmpObj.updateMatrix()
      instancedNodes.setMatrixAt(i, tmpObj.matrix)
      tmpColor.set(node.color)
      instancedNodes.setColorAt(i, tmpColor)
    }
    instancedNodes.instanceMatrix.needsUpdate = true
    if (instancedNodes.instanceColor) instancedNodes.instanceColor.needsUpdate = true
    brain.add(instancedNodes)

    // ── Edges: цветовой градиент source→target ─────────────────────────
    // Один LineSegments-mesh со всеми рёбрами. Цвет на стороне source
    // насыщенный, на target — тусклее (читается как "поток вытекает").
    // Это даёт визуальное указание направления даже без анимации.
    let edgeLines: THREE.LineSegments | null = null
    if (showEdges && edgeCount > 0) {
      const positions = new Float32Array(edgeCount * 2 * 3)
      const colors = new Float32Array(edgeCount * 2 * 3)
      const srcColor = new THREE.Color()
      const tgtColor = new THREE.Color()
      for (let i = 0; i < edgeCount; i += 1) {
        const e = graph.edges[i]
        const [sx, sy, sz] = e.sourcePosition
        const [tx, ty, tz] = e.targetPosition
        positions[i * 6 + 0] = sx
        positions[i * 6 + 1] = sy
        positions[i * 6 + 2] = sz
        positions[i * 6 + 3] = tx
        positions[i * 6 + 4] = ty
        positions[i * 6 + 5] = tz
        srcColor.set(e.color)
        // Target-end темнее на 55% — градиент читается как "стрелка".
        tgtColor.copy(srcColor).multiplyScalar(0.32)
        colors[i * 6 + 0] = srcColor.r
        colors[i * 6 + 1] = srcColor.g
        colors[i * 6 + 2] = srcColor.b
        colors[i * 6 + 3] = tgtColor.r
        colors[i * 6 + 4] = tgtColor.g
        colors[i * 6 + 5] = tgtColor.b
      }
      const edgeGeometry = new THREE.BufferGeometry()
      edgeGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
      edgeGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
      const edgeMaterial = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: heavy ? 0.4 : 0.6,
        depthWrite: false,
      })
      edgeLines = new THREE.LineSegments(edgeGeometry, edgeMaterial)
      brain.add(edgeLines)
    }

    // ── Импульсы (направляющие точки) source→target ─────────────────────
    // Один InstancedMesh со всеми импульсами. Каждый instance — маленькая
    // светящаяся сфера, ползущая по линейному пути от source к target.
    // Когда t=1 — телепортируется обратно к source (offset разный на разных
    // рёбрах, поэтому импульсы распределены равномерно по длине ребра).
    // Стоимость: O(edges) матрицы/кадр + 1 draw call.
    let pulseMesh: THREE.InstancedMesh | null = null
    let pulseGeometry: THREE.SphereGeometry | null = null
    let pulseMaterial: THREE.MeshBasicMaterial | null = null
    const pulseSourcePos: Float32Array = new Float32Array(enablePulses ? edgeCount * 3 : 0)
    const pulseTargetPos: Float32Array = new Float32Array(enablePulses ? edgeCount * 3 : 0)
    const pulseOffsets: Float32Array = new Float32Array(enablePulses ? edgeCount : 0)
    if (enablePulses) {
      pulseGeometry = new THREE.SphereGeometry(1, 8, 6)
      pulseMaterial = new THREE.MeshBasicMaterial({
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
      pulseMesh = new THREE.InstancedMesh(pulseGeometry, pulseMaterial, edgeCount)
      pulseMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      const pColor = new THREE.Color()
      for (let i = 0; i < edgeCount; i += 1) {
        const e = graph.edges[i]
        pulseSourcePos[i * 3 + 0] = e.sourcePosition[0]
        pulseSourcePos[i * 3 + 1] = e.sourcePosition[1]
        pulseSourcePos[i * 3 + 2] = e.sourcePosition[2]
        pulseTargetPos[i * 3 + 0] = e.targetPosition[0]
        pulseTargetPos[i * 3 + 1] = e.targetPosition[1]
        pulseTargetPos[i * 3 + 2] = e.targetPosition[2]
        // Случайный offset, чтобы импульсы не шли стройным фронтом.
        pulseOffsets[i] = Math.random()
        // Стартовая матрица — на source-конце, размер от веса ребра.
        const baseSize = 3.4 + Number(e.weight || 0.4) * 2.4
        tmpObj.position.set(e.sourcePosition[0], e.sourcePosition[1], e.sourcePosition[2])
        tmpObj.scale.setScalar(baseSize)
        tmpObj.updateMatrix()
        pulseMesh.setMatrixAt(i, tmpObj.matrix)
        pColor.set(e.color)
        pulseMesh.setColorAt(i, pColor)
      }
      pulseMesh.instanceMatrix.needsUpdate = true
      if (pulseMesh.instanceColor) pulseMesh.instanceColor.needsUpdate = true
      brain.add(pulseMesh)
    }

    // ── Picking через InstancedMesh ────────────────────────────────────
    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()

    const pickNodeId = (event: MouseEvent): string | null => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObject(instancedNodes, false)[0]
      if (hit && typeof hit.instanceId === 'number') {
        return nodeIdByInstance[hit.instanceId] ?? null
      }
      return null
    }

    const handleClick = (event: MouseEvent) => {
      const id = pickNodeId(event)
      if (id) onSelectRef.current(id)
    }

    let lastMove = 0
    const handleMove = (event: MouseEvent) => {
      const now = performance.now()
      if (now - lastMove < POINTER_MOVE_THROTTLE_MS) return
      lastMove = now
      const id = pickNodeId(event)
      renderer.domElement.style.cursor = id ? 'pointer' : 'grab'
    }

    renderer.domElement.addEventListener('click', handleClick)
    renderer.domElement.addEventListener('pointermove', handleMove)

    const resize = () => {
      const width = Math.max(1, host.clientWidth)
      const height = Math.max(1, host.clientHeight)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
    }
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(host)
    resize()

    // ── Анимационный цикл ─────────────────────────────────────────────
    const highlightColor = new THREE.Color(0xffffff)
    let prevSelected = ''
    let raf = 0
    let frame = 0
    // Скорость импульсов (доля длины ребра в кадр) — медленно для читаемости.
    const PULSE_SPEED = 0.006

    const tick = () => {
      frame += 1
      // 1) Обновление выделенного узла (срабатывает только при смене selectedRef).
      const sel = selectedRef.current
      if (sel !== prevSelected) {
        if (prevSelected) {
          const prevIdx = nodeIdByInstance.indexOf(prevSelected)
          if (prevIdx >= 0) {
            const node = nodeIndex.get(prevSelected)!
            tmpObj.position.set(...node.position)
            tmpObj.scale.setScalar(baseScales[prevIdx])
            tmpObj.updateMatrix()
            instancedNodes.setMatrixAt(prevIdx, tmpObj.matrix)
            tmpColor.set(node.color)
            instancedNodes.setColorAt(prevIdx, tmpColor)
          }
        }
        if (sel) {
          const idx = nodeIdByInstance.indexOf(sel)
          if (idx >= 0) {
            const node = nodeIndex.get(sel)!
            tmpObj.position.set(...node.position)
            tmpObj.scale.setScalar(baseScales[idx] * 1.9)
            tmpObj.updateMatrix()
            instancedNodes.setMatrixAt(idx, tmpObj.matrix)
            instancedNodes.setColorAt(idx, highlightColor)
          }
        }
        instancedNodes.instanceMatrix.needsUpdate = true
        if (instancedNodes.instanceColor) instancedNodes.instanceColor.needsUpdate = true
        prevSelected = sel
      }

      // 2) Анимация импульсов — линейная интерполяция от source к target.
      //    t = ((frame * speed) + offset) mod 1, позиция = lerp(src, tgt, t).
      //    Размер пульсирует синусом для эффекта "светящейся капли".
      if (pulseMesh) {
        const t0 = frame * PULSE_SPEED
        for (let i = 0; i < edgeCount; i += 1) {
          const t = (t0 + pulseOffsets[i]) % 1
          const sx = pulseSourcePos[i * 3 + 0]
          const sy = pulseSourcePos[i * 3 + 1]
          const sz = pulseSourcePos[i * 3 + 2]
          const tx = pulseTargetPos[i * 3 + 0]
          const ty = pulseTargetPos[i * 3 + 1]
          const tz = pulseTargetPos[i * 3 + 2]
          tmpObj.position.set(sx + (tx - sx) * t, sy + (ty - sy) * t, sz + (tz - sz) * t)
          // Sin-cycle 0.6..1.6 в зависимости от прохода — пик в середине ребра.
          const baseSize = 2.6 + Number(graph.edges[i].weight || 0.4) * 1.8
          const pulse = 0.6 + Math.sin(t * Math.PI) * 1.0
          tmpObj.scale.setScalar(baseSize * pulse)
          tmpObj.updateMatrix()
          pulseMesh.setMatrixAt(i, tmpObj.matrix)
        }
        pulseMesh.instanceMatrix.needsUpdate = true
      }

      controls.update()
      renderer.render(scene, camera)
      raf = window.requestAnimationFrame(tick)
    }
    tick()

    return () => {
      window.cancelAnimationFrame(raf)
      resizeObserver.disconnect()
      renderer.domElement.removeEventListener('click', handleClick)
      renderer.domElement.removeEventListener('pointermove', handleMove)
      controls.dispose()
      nodeGeometry.dispose()
      nodeMaterial.dispose()
      instancedNodes.dispose?.()
      if (edgeLines) {
        edgeLines.geometry.dispose()
        ;(edgeLines.material as THREE.Material).dispose()
      }
      if (pulseMesh) {
        pulseGeometry?.dispose()
        pulseMaterial?.dispose()
        pulseMesh.dispose?.()
      }
      renderer.dispose()
      renderer.domElement.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, showEdges])

  return <div className="brain-stage" ref={hostRef} />
})
