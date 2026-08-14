'use client'

/**
 * Three.js Boardman hero — Meng To style: product floating in space.
 * Loads three only in the browser. Skips on small screens / reduced motion.
 */
import { useEffect, useRef } from 'react'
import type { MeshStandardMaterial, Object3D } from 'three'

export default function BoardmanHero3D() {
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
      scene.fog = new THREE.FogExp2(0x07060c, 0.038)

      const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 80)
      camera.position.set(1.6, 6.6, 10.4)
      camera.lookAt(-0.4, 0.35, 0)

      const gl = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      })
      renderer = gl
      gl.setClearColor(0x000000, 0)
      gl.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6))
      canvas.parentElement?.classList.add('bm-gl-on')
      gl.toneMapping = THREE.ACESFilmicToneMapping
      gl.toneMappingExposure = 1.12

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

      scene.add(new THREE.AmbientLight(0xb8a0ff, 0.38))
      const key = new THREE.DirectionalLight(0xfff4e0, 1.25)
      key.position.set(6, 11, 5)
      scene.add(key)
      const rim = new THREE.PointLight(0x7c3aed, 36, 32)
      rim.position.set(-6, 3.4, 5)
      scene.add(rim)
      const warm = new THREE.PointLight(0xf59e0b, 12, 20)
      warm.position.set(5, 2.2, -3)
      scene.add(warm)
      const fill = new THREE.PointLight(0x60a5fa, 6, 18)
      fill.position.set(0, 1.2, 6)
      scene.add(fill)

      const world = new THREE.Group()
      world.rotation.x = -0.38
      scene.add(world)

      const cream = new THREE.MeshStandardMaterial({
        color: 0xe8d9b8,
        roughness: 0.36,
        metalness: 0.1,
      })
      const dark = new THREE.MeshStandardMaterial({
        color: 0x2a2118,
        roughness: 0.44,
        metalness: 0.14,
      })
      const squareGeo = new THREE.BoxGeometry(0.92, 0.12, 0.92)
      const board = new THREE.Group()
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const mesh = new THREE.Mesh(squareGeo, (r + c) % 2 ? dark : cream)
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
      world.add(board)

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

      const sphere = new THREE.SphereGeometry(1, 18, 14)
      const cone = new THREE.ConeGeometry(1, 2, 14)
      const box = new THREE.BoxGeometry(1, 1, 1)
      const cyl = new THREE.CylinderGeometry(1, 1, 1, 14)

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

      const pieces: Array<{ obj: Object3D; baseY: number; phase: number }> = []
      const place = (obj: Object3D, file: number, rank: number, y = 0.12) => {
        obj.position.set(file - 3.5, y, rank - 3.5)
        world.add(obj)
        pieces.push({ obj, baseY: y, phase: file * 0.7 + rank * 0.35 })
      }
      place(rook(gold), 0, 0)
      place(knight(gold), 1, 0)
      place(bishop(gold), 2, 0)
      place(queen(gold), 3, 0)
      place(king(gold), 4, 0)
      place(pawn(gold), 0, 1)
      place(pawn(gold), 3, 1)
      place(pawn(gold), 5, 1)
      place(rook(ink), 7, 7)
      place(knight(ink), 6, 7)
      place(bishop(ink), 5, 7)
      place(queen(ink), 3, 7)
      place(king(ink), 4, 7)
      place(pawn(ink), 4, 6)
      place(pawn(ink), 5, 6)
      place(pawn(ink), 7, 6)

      const mover = pawn(gold)
      place(mover, 4, 1)

      const dustCount = 420
      const dustGeo = new THREE.BufferGeometry()
      const dustPos = new Float32Array(dustCount * 3)
      for (let i = 0; i < dustCount; i++) {
        dustPos[i * 3] = (Math.random() - 0.5) * 22
        dustPos[i * 3 + 1] = Math.random() * 10 - 1
        dustPos[i * 3 + 2] = (Math.random() - 0.5) * 22
      }
      dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3))
      const dust = new THREE.Points(
        dustGeo,
        new THREE.PointsMaterial({
          color: 0xc4b5fd,
          size: 0.035,
          transparent: true,
          opacity: 0.45,
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

      const clock = new THREE.Clock()
      const tick = () => {
        if (dead) return
        const t = clock.getElapsedTime()
        world.rotation.y = THREE.MathUtils.lerp(world.rotation.y, pointer.x * 0.42, 0.045)
        world.rotation.x = -0.38 + pointer.y * 0.09
        world.position.y = Math.sin(t * 0.55) * 0.1
        world.position.x = THREE.MathUtils.lerp(world.position.x, pointer.x * 0.25, 0.03)
        pieces.forEach((p) => {
          p.obj.position.y = p.baseY + Math.sin(t * 0.85 + p.phase) * 0.04
        })
        mover.position.z = 1 - 3.5 + (Math.sin(t * 0.35) * 0.5 + 0.5) * 1.85
        dust.rotation.y = t * 0.018
        rim.intensity = 32 + Math.sin(t * 0.8) * 6
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
        dustGeo.dispose()
        cream.dispose()
        dark.dispose()
        gold.dispose()
        ink.dispose()
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
