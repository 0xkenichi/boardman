'use client'

/**
 * One Three.js scene for the whole homepage.
 * Scroll moves camera + worlds: chess → human game cards → agent network.
 * Skips WebGL on phones / reduced motion / weak CPUs.
 */
import { useEffect, useRef } from 'react'
import type { Mesh, MeshStandardMaterial, Object3D, Vector3 } from 'three'

function kf(p: number, frames: Array<[number, number]>) {
  if (p <= frames[0][0]) return frames[0][1]
  const last = frames[frames.length - 1]
  if (p >= last[0]) return last[1]
  for (let i = 0; i < frames.length - 1; i++) {
    const a = frames[i]
    const b = frames[i + 1]
    if (p >= a[0] && p <= b[0]) {
      const u = (p - a[0]) / Math.max(b[0] - a[0], 1e-6)
      const s = u * u * (3 - 2 * u)
      return a[1] + (b[1] - a[1]) * s
    }
  }
  return last[1]
}

export default function BoardmanScrollScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const weak =
      window.innerWidth < 720 ||
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
      scene.fog = new THREE.FogExp2(0x07060c, 0.032)

      const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 90)
      camera.position.set(1.6, 6.6, 10.4)
      const look = new THREE.Vector3(-0.4, 0.35, 0)
      camera.lookAt(look)

      const gl = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      })
      renderer = gl
      gl.setClearColor(0x000000, 0)
      gl.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
      canvas.closest('.bm-story-stage')?.classList.add('bm-gl-on')
      document.querySelector('.bm-story')?.classList.add('bm-gl-on')
      gl.toneMapping = THREE.ACESFilmicToneMapping
      gl.toneMappingExposure = 1.1

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

      scene.add(new THREE.AmbientLight(0xb8a0ff, 0.36))
      const key = new THREE.DirectionalLight(0xfff4e0, 1.2)
      key.position.set(6, 11, 5)
      scene.add(key)
      const rim = new THREE.PointLight(0x7c3aed, 34, 34)
      rim.position.set(-6, 3.4, 5)
      scene.add(rim)
      const warm = new THREE.PointLight(0xf59e0b, 11, 20)
      warm.position.set(5, 2.2, -3)
      scene.add(warm)
      const emerald = new THREE.PointLight(0x34d399, 0, 22)
      emerald.position.set(6, 3, 2)
      scene.add(emerald)

      const root = new THREE.Group()
      scene.add(root)

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
        new THREE.CylinderGeometry(5.6, 6.1, 0.55, 48),
        new THREE.MeshStandardMaterial({
          color: 0x120c1c,
          roughness: 0.55,
          metalness: 0.28,
          emissive: 0x1a0a30,
          emissiveIntensity: 0.18,
        })
      )
      plinth.position.y = -0.48
      board.add(plinth)
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(5.85, 0.035, 8, 64),
        new THREE.MeshStandardMaterial({
          color: 0x7c3aed,
          roughness: 0.25,
          metalness: 0.7,
          emissive: 0x7c3aed,
          emissiveIntensity: 0.55,
        })
      )
      ring.rotation.x = Math.PI / 2
      ring.position.y = -0.18
      board.add(ring)
      root.add(board)

      const gold = new THREE.MeshStandardMaterial({
        color: 0xf3e6c4,
        roughness: 0.26,
        metalness: 0.38,
        emissive: 0x3b2a10,
        emissiveIntensity: 0.16,
      })
      const ink = new THREE.MeshStandardMaterial({
        color: 0x161018,
        roughness: 0.38,
        metalness: 0.28,
        emissive: 0x2a1048,
        emissiveIntensity: 0.22,
      })
      const sphere = new THREE.SphereGeometry(1, 16, 12)
      const cone = new THREE.ConeGeometry(1, 2, 12)
      const box = new THREE.BoxGeometry(1, 1, 1)
      const cyl = new THREE.CylinderGeometry(1, 1, 1, 12)

      type Mat = MeshStandardMaterial
      function pawn(mat: Mat) {
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
      function king(mat: Mat) {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.32, 0.14, 0.32)
        const body = new THREE.Mesh(cone, mat)
        body.scale.set(0.26, 0.72, 0.26)
        body.position.y = 0.5
        const cross = new THREE.Mesh(box, mat)
        cross.scale.set(0.08, 0.28, 0.08)
        cross.position.y = 1.02
        const bar = new THREE.Mesh(box, mat)
        bar.scale.set(0.2, 0.08, 0.08)
        bar.position.y = 1.02
        g.add(base, body, cross, bar)
        return g
      }
      function queen(mat: Mat) {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.3, 0.13, 0.3)
        const body = new THREE.Mesh(cone, mat)
        body.scale.set(0.25, 0.66, 0.25)
        body.position.y = 0.46
        const crown = new THREE.Mesh(cyl, mat)
        crown.scale.set(0.2, 0.1, 0.2)
        crown.position.y = 0.92
        const tip = new THREE.Mesh(sphere, mat)
        tip.scale.setScalar(0.09)
        tip.position.y = 1.04
        g.add(base, body, crown, tip)
        return g
      }
      function rook(mat: Mat) {
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
      function bishop(mat: Mat) {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.28, 0.12, 0.28)
        const body = new THREE.Mesh(cone, mat)
        body.scale.set(0.2, 0.78, 0.2)
        body.position.y = 0.52
        const mitre = new THREE.Mesh(sphere, mat)
        mitre.scale.set(0.12, 0.16, 0.12)
        mitre.position.y = 1.02
        g.add(base, body, mitre)
        return g
      }
      function knight(mat: Mat) {
        const g = new THREE.Group()
        const base = new THREE.Mesh(cyl, mat)
        base.scale.set(0.3, 0.12, 0.3)
        const body = new THREE.Mesh(box, mat)
        body.scale.set(0.26, 0.42, 0.32)
        body.position.y = 0.32
        const neck = new THREE.Mesh(box, mat)
        neck.scale.set(0.18, 0.28, 0.22)
        neck.position.set(0.04, 0.62, -0.06)
        neck.rotation.x = -0.35
        const head = new THREE.Mesh(box, mat)
        head.scale.set(0.16, 0.16, 0.3)
        head.position.set(0.08, 0.78, 0.08)
        g.add(base, body, neck, head)
        return g
      }

      const pieces: Array<{ obj: Object3D; baseY: number; phase: number; file: number; rank: number }> =
        []
      const place = (obj: Object3D, file: number, rank: number, y = 0.12) => {
        obj.position.set(file - 3.5, y, rank - 3.5)
        board.add(obj)
        pieces.push({ obj, baseY: y, phase: file * 0.7 + rank * 0.35, file, rank })
      }
      const back = [rook, knight, bishop, queen, king, bishop, knight, rook]
      for (let f = 0; f < 8; f++) {
        place(back[f](gold), f, 0)
        place(pawn(gold), f, 1)
        place(pawn(ink), f, 6)
        place(back[f](ink), f, 7)
      }
      const mover = pieces.find((p) => p.file === 4 && p.rank === 1)

      const screens = new THREE.Group()
      screens.visible = false
      root.add(screens)

      const net = new THREE.Group()
      net.position.set(-5.2, 3.4, -1)
      root.add(net)
      const nodeMat = new THREE.MeshStandardMaterial({
        color: 0x7c3aed,
        emissive: 0x7c3aed,
        emissiveIntensity: 0.7,
        roughness: 0.3,
        metalness: 0.4,
      })
      const nodeMat2 = new THREE.MeshStandardMaterial({
        color: 0x34d399,
        emissive: 0x059669,
        emissiveIntensity: 0.55,
        roughness: 0.35,
        metalness: 0.35,
      })
      const nodeGeo = new THREE.SphereGeometry(0.18, 14, 12)
      const nodePos: Vector3[] = []
      for (let i = 0; i < 10; i++) {
        const a = (i / 10) * Math.PI * 2
        const r = i % 2 === 0 ? 2.4 : 1.45
        const v = new THREE.Vector3(Math.cos(a) * r, Math.sin(a * 1.4) * 0.55, Math.sin(a) * r)
        nodePos.push(v)
        const n = new THREE.Mesh(nodeGeo, i % 3 === 0 ? nodeMat2 : nodeMat)
        n.position.copy(v)
        net.add(n)
      }
      const linePos: number[] = []
      for (let i = 0; i < nodePos.length; i++) {
        const j = (i + 3) % nodePos.length
        linePos.push(nodePos[i].x, nodePos[i].y, nodePos[i].z, nodePos[j].x, nodePos[j].y, nodePos[j].z)
      }
      const lineGeo = new THREE.BufferGeometry()
      lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePos, 3))
      net.add(
        new THREE.LineSegments(
          lineGeo,
          new THREE.LineBasicMaterial({ color: 0xa78bfa, transparent: true, opacity: 0.45 })
        )
      )

      const dustCount = 280
      const dustGeo = new THREE.BufferGeometry()
      const dustPos = new Float32Array(dustCount * 3)
      for (let i = 0; i < dustCount; i++) {
        dustPos[i * 3] = (Math.random() - 0.5) * 26
        dustPos[i * 3 + 1] = Math.random() * 12 - 1
        dustPos[i * 3 + 2] = (Math.random() - 0.5) * 26
      }
      dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3))
      const dust = new THREE.Points(
        dustGeo,
        new THREE.PointsMaterial({
          color: 0xc4b5fd,
          size: 0.032,
          transparent: true,
          opacity: 0.4,
          depthWrite: false,
        })
      )
      scene.add(dust)

      const pointer = { x: 0, y: 0 }
      const onMove = (e: PointerEvent) => {
        pointer.x = (e.clientX / window.innerWidth) * 2 - 1
        pointer.y = (e.clientY / window.innerHeight) * 2 - 1
      }
      window.addEventListener('pointermove', onMove, { passive: true })
      cleanups.push(() => window.removeEventListener('pointermove', onMove))

      const progress = { v: 0 }
      const readScroll = () => {
        const story = canvas.closest('.bm-story') as HTMLElement | null
        if (!story) return
        const total = story.offsetHeight - window.innerHeight
        progress.v = THREE.MathUtils.clamp(-story.getBoundingClientRect().top / Math.max(total, 1), 0, 1)
      }
      window.addEventListener('scroll', readScroll, { passive: true })
      cleanups.push(() => window.removeEventListener('scroll', readScroll))
      readScroll()

      const camT = new THREE.Vector3()
      const lookT = new THREE.Vector3()
      const clock = new THREE.Clock()
      const tick = () => {
        if (dead) return
        const t = clock.getElapsedTime()
        const p = progress.v

        camT.set(
          kf(p, [
            [0, 1.6],
            [0.22, 6.4],
            [0.45, 0.5],
            [0.68, -4.2],
            [0.92, 0.2],
          ]),
          kf(p, [
            [0, 6.6],
            [0.22, 4.8],
            [0.45, 5.1],
            [0.68, 6.8],
            [0.92, 8.4],
          ]),
          kf(p, [
            [0, 10.4],
            [0.22, 10.2],
            [0.45, 7.4],
            [0.68, 11.5],
            [0.92, 15.5],
          ])
        )
        lookT.set(
          kf(p, [
            [0, -0.4],
            [0.22, 5.4],
            [0.45, 0.1],
            [0.68, -4.6],
            [0.92, 0],
          ]),
          kf(p, [
            [0, 0.35],
            [0.22, 2.0],
            [0.45, 0.35],
            [0.68, 3.2],
            [0.92, 0.6],
          ]),
          kf(p, [
            [0, 0],
            [0.22, 0],
            [0.45, 0],
            [0.68, -0.6],
            [0.92, 0],
          ])
        )
        camT.x += pointer.x * 0.55
        camT.y += pointer.y * 0.25
        camera.position.lerp(camT, 0.07)
        look.lerp(lookT, 0.07)
        camera.lookAt(look)

        board.rotation.y = pointer.x * 0.12
        board.position.y = Math.sin(t * 0.55) * 0.08
        board.position.x = kf(p, [
          [0, 0],
          [0.22, -3.2],
          [0.45, 0.2],
          [0.68, 2.4],
          [0.92, 0],
        ])
        const boardA = kf(p, [
          [0, 1],
          [0.2, 0.22],
          [0.42, 1],
          [0.62, 0.18],
          [0.9, 0.35],
        ])
        board.traverse((o) => {
          const m = o as Mesh
          if (m.material && !Array.isArray(m.material) && 'opacity' in m.material) {
            const mat = m.material as MeshStandardMaterial
            mat.transparent = boardA < 0.98
            mat.opacity = boardA
          }
        })

        pieces.forEach((pc) => {
          pc.obj.position.y = pc.baseY + Math.sin(t * 0.85 + pc.phase) * 0.028
        })
        if (mover) {
          mover.obj.position.z = 1 - 3.5 + (Math.sin(t * 0.35) * 0.5 + 0.5) * 1.85
        }

        const screenA = kf(p, [
          [0, 0],
          [0.12, 0],
          [0.2, 1],
          [0.36, 1],
          [0.46, 0],
        ])
        screens.visible = screenA > 0.02
        const spin = kf(p, [
          [0.12, 0],
          [0.38, Math.PI * 2],
        ])
        const nCards = screens.children.length || 1
        screens.children.forEach((card, i) => {
          const a = (i / nCards) * Math.PI * 2 + spin
          card.position.set(Math.sin(a) * 2.55, Math.cos(a) * 0.42, Math.cos(a) * 1.15)
          card.rotation.y = -a + 0.15
          card.rotation.x = 0.06
        })
        screens.position.y = 2.05
        screens.traverse((o) => {
          const m = o as Mesh
          if (!m.material) return
          const list = Array.isArray(m.material) ? m.material : [m.material]
          list.forEach((mat) => {
            const mm = mat as MeshStandardMaterial
            if ('opacity' in mm) {
              mm.transparent = true
              mm.opacity = screenA
            }
          })
        })

        const netA = kf(p, [
          [0, 0],
          [0.52, 0],
          [0.66, 1],
          [0.88, 0.55],
          [1, 0.25],
        ])
        net.visible = netA > 0.02
        net.rotation.y = t * 0.12
        net.traverse((o) => {
          const m = o as Mesh
          if (m.material && !Array.isArray(m.material) && 'opacity' in m.material) {
            const mat = m.material as MeshStandardMaterial
            mat.transparent = true
            mat.opacity = netA
          }
        })

        rim.intensity = 26 + Math.sin(t * 0.8) * 5
        emerald.intensity = kf(p, [
          [0, 0],
          [0.2, 16],
          [0.4, 2],
          [0.68, 8],
          [1, 0],
        ])
        dust.rotation.y = t * 0.016
        gl.render(scene, camera)
        raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)

      cleanups.push(() => {
        squareGeo.dispose()
        sphere.dispose()
        cone.dispose()
        box.dispose()
        cyl.dispose()
        nodeGeo.dispose()
        lineGeo.dispose()
        dustGeo.dispose()
        cream.dispose()
        darkSq.dispose()
        gold.dispose()
        ink.dispose()
        nodeMat.dispose()
        nodeMat2.dispose()
      })
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

  return <canvas ref={canvasRef} className="bm-gl" aria-hidden />
}
