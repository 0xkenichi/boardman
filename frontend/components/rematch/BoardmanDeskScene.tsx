'use client'

/**
 * Quiet Three.js desk for /app — same board, lights, and materials as the
 * homepage, idle camera only. CSS board shows until WebGL is ready / on phones.
 */
import { useEffect, useRef } from 'react'

function CssBoard() {
  const squares = Array.from({ length: 64 }, (_, i) => {
    const r = Math.floor(i / 8)
    const c = i % 8
    return (r + c) % 2 === 1
  })
  const back = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook']
  const spots: Array<{ kind: string; side: 'gold' | 'ink'; file: number; rank: number }> = []
  for (let f = 0; f < 8; f++) {
    spots.push({ kind: back[f], side: 'gold', file: f, rank: 0 })
    spots.push({ kind: 'pawn', side: 'gold', file: f, rank: 1 })
    spots.push({ kind: 'pawn', side: 'ink', file: f, rank: 6 })
    spots.push({ kind: back[f], side: 'ink', file: f, rank: 7 })
  }
  return (
    <div className="bm-css-board bm-css-board-app" aria-hidden>
      <div className="bm-css-grid">
        {squares.map((dark, i) => (
          <span key={i} className={dark ? 'bm-sq bm-sq-d' : 'bm-sq bm-sq-l'} />
        ))}
      </div>
      {spots.map((p) => {
        const left = `${(p.file + 0.5) * 12.5}%`
        const top = `${(7 - p.rank + 0.5) * 12.5}%`
        return (
          <span
            key={`${p.side}-${p.kind}-${p.file}-${p.rank}`}
            className={`bm-css-piece bm-css-${p.side}${p.kind !== 'pawn' ? ' bm-css-tall' : ''}`}
            style={{ left, top }}
          />
        )
      })}
    </div>
  )
}

export default function BoardmanDeskScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const weak =
      window.innerWidth < 640 ||
      (navigator.hardwareConcurrency || 8) <= 4 ||
      /Android|iPhone|iPad/i.test(navigator.userAgent)
    if (reduce || weak) {
      canvas.dataset.fallback = '1'
      return
    }

    let dead = false
    let raf = 0
    let renderer: { dispose: () => void; forceContextLoss?: () => void } | null = null
    const cleanups: Array<() => void> = []

    ;(async () => {
      const THREE = await import('three')
      if (dead || !canvas.isConnected) return

      const scene = new THREE.Scene()
      scene.fog = new THREE.FogExp2(0x07060c, 0.034)

      const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 80)
      camera.position.set(2.1, 5.8, 9.2)
      const look = new THREE.Vector3(-0.8, 0.2, 0)
      camera.lookAt(look)

      const gl = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      })
      renderer = gl
      gl.setClearColor(0x000000, 0)
      gl.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.4))
      canvas.closest('.bm-app-stage')?.classList.add('bm-gl-on')
      canvas.closest('.bm-app')?.classList.add('bm-gl-on')
      gl.toneMapping = THREE.ACESFilmicToneMapping
      gl.toneMappingExposure = 1.05

      const fit = () => {
        const w = canvas.clientWidth || window.innerWidth
        const h = canvas.clientHeight || window.innerHeight
        gl.setSize(w, h, false)
        camera.aspect = w / Math.max(h, 1)
        camera.updateProjectionMatrix()
      }
      fit()
      window.addEventListener('resize', fit)
      cleanups.push(() => window.removeEventListener('resize', fit))

      scene.add(new THREE.AmbientLight(0xb8a0ff, 0.34))
      const key = new THREE.DirectionalLight(0xfff4e0, 1.1)
      key.position.set(6, 11, 5)
      scene.add(key)
      const rim = new THREE.PointLight(0x7c3aed, 28, 32)
      rim.position.set(-6, 3.2, 5)
      scene.add(rim)
      const emerald = new THREE.PointLight(0x34d399, 10, 22)
      emerald.position.set(5.5, 2.8, 2)
      scene.add(emerald)

      const cream = new THREE.MeshStandardMaterial({
        color: 0xe8d9b8,
        roughness: 0.36,
        metalness: 0.1,
      })
      const darkSq = new THREE.MeshStandardMaterial({
        color: 0x2a2118,
        roughness: 0.44,
        metalness: 0.14,
      })
      const squareGeo = new THREE.BoxGeometry(0.92, 0.12, 0.92)
      const board = new THREE.Group()
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const mesh = new THREE.Mesh(squareGeo, (r + c) % 2 ? darkSq : cream)
          mesh.position.set(c - 3.5, 0, r - 3.5)
          board.add(mesh)
        }
      }
      const frame = new THREE.Mesh(
        new THREE.BoxGeometry(8.2, 0.2, 8.2),
        new THREE.MeshStandardMaterial({ color: 0x1a1030, roughness: 0.48, metalness: 0.22 })
      )
      frame.position.y = -0.13
      board.add(frame)
      const plinth = new THREE.Mesh(
        new THREE.CylinderGeometry(5.6, 6.1, 0.55, 40),
        new THREE.MeshStandardMaterial({
          color: 0x120c1c,
          roughness: 0.55,
          metalness: 0.28,
          emissive: 0x1a0a30,
          emissiveIntensity: 0.16,
        })
      )
      plinth.position.y = -0.48
      board.add(plinth)
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(5.85, 0.035, 8, 48),
        new THREE.MeshStandardMaterial({
          color: 0x7c3aed,
          roughness: 0.25,
          metalness: 0.7,
          emissive: 0x7c3aed,
          emissiveIntensity: 0.5,
        })
      )
      ring.rotation.x = Math.PI / 2
      ring.position.y = -0.18
      board.add(ring)
      scene.add(board)

      const gold = new THREE.MeshStandardMaterial({
        color: 0xf3e6c4,
        roughness: 0.26,
        metalness: 0.38,
        emissive: 0x3b2a10,
        emissiveIntensity: 0.14,
      })
      const ink = new THREE.MeshStandardMaterial({
        color: 0x161018,
        roughness: 0.38,
        metalness: 0.28,
        emissive: 0x2a1048,
        emissiveIntensity: 0.2,
      })
      const sphere = new THREE.SphereGeometry(1, 12, 10)
      const cone = new THREE.ConeGeometry(1, 2, 10)
      const box = new THREE.BoxGeometry(1, 1, 1)
      const cyl = new THREE.CylinderGeometry(1, 1, 1, 10)

      const pawn = (mat: typeof gold) => {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.28, 0.12, 0.28)
        const body = new THREE.Mesh(cone, mat)
        body.scale.set(0.22, 0.38, 0.22)
        body.position.y = 0.32
        const head = new THREE.Mesh(sphere, mat)
        head.scale.setScalar(0.16)
        head.position.y = 0.62
        g.add(base, body, head)
        return g
      }
      const king = (mat: typeof gold) => {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.32, 0.14, 0.32)
        const body = new THREE.Mesh(cone, mat)
        body.scale.set(0.26, 0.72, 0.26)
        body.position.y = 0.5
        const cross = new THREE.Mesh(box, mat)
        cross.scale.set(0.08, 0.28, 0.08)
        cross.position.y = 1.02
        g.add(base, body, cross)
        return g
      }
      const rook = (mat: typeof gold) => {
        const g = new THREE.Group()
        const tower = new THREE.Mesh(box, mat)
        tower.scale.set(0.38, 0.62, 0.38)
        tower.position.y = 0.38
        const top = new THREE.Mesh(box, mat)
        top.scale.set(0.46, 0.12, 0.46)
        top.position.y = 0.74
        g.add(tower, top)
        return g
      }

      const place = (obj: InstanceType<typeof THREE.Object3D>, file: number, rank: number) => {
        obj.position.set(file - 3.5, 0.12, rank - 3.5)
        board.add(obj)
      }
      for (let f = 0; f < 8; f++) {
        place(pawn(gold), f, 1)
        place(pawn(ink), f, 6)
      }
      place(rook(gold), 0, 0)
      place(rook(gold), 7, 0)
      place(rook(ink), 0, 7)
      place(rook(ink), 7, 7)
      place(king(gold), 4, 0)
      place(king(ink), 4, 7)

      const pointer = { x: 0, y: 0 }
      const onMove = (e: PointerEvent) => {
        pointer.x = (e.clientX / window.innerWidth) * 2 - 1
        pointer.y = (e.clientY / window.innerHeight) * 2 - 1
      }
      window.addEventListener('pointermove', onMove, { passive: true })
      cleanups.push(() => window.removeEventListener('pointermove', onMove))

      const clock = new THREE.Clock()
      const tick = () => {
        if (dead) return
        const t = clock.getElapsedTime()
        board.rotation.y = pointer.x * 0.14 + Math.sin(t * 0.18) * 0.08
        board.position.y = Math.sin(t * 0.5) * 0.07
        camera.position.x = 2.1 + pointer.x * 0.35
        camera.position.y = 5.8 + pointer.y * 0.18
        camera.lookAt(look)
        gl.render(scene, camera)
        raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
    })()

    return () => {
      dead = true
      cancelAnimationFrame(raf)
      cleanups.forEach((fn) => fn())
      try {
        renderer?.forceContextLoss?.()
        renderer?.dispose()
      } catch {
        /* ignore */
      }
    }
  }, [])

  return (
    <>
      <CssBoard />
      <canvas ref={canvasRef} className="bm-gl" aria-hidden />
    </>
  )
}
