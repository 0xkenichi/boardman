'use client'

/**
 * BoardmanVaultScene — Three.js "fund the wallet" atmosphere.
 *
 * A slow drift of golden USDC coins and gold dust in a dark vault, lit by
 * violet and emerald rims. Deliberately NOT the chess desk: this one is
 * money. CSS coins show until WebGL is ready / on phones / reduced motion.
 */
import { useEffect, useRef } from 'react'

function CssCoins() {
  const spots = [
    { left: '8%', top: '22%', s: 46, d: 0 },
    { left: '18%', top: '64%', s: 30, d: 1.2 },
    { left: '30%', top: '34%', s: 20, d: 0.6 },
    { left: '44%', top: '76%', s: 26, d: 1.8 },
    { left: '58%', top: '18%', s: 38, d: 0.3 },
    { left: '70%', top: '58%', s: 22, d: 1.5 },
    { left: '82%', top: '30%', s: 34, d: 0.9 },
    { left: '91%', top: '70%', s: 24, d: 2.1 },
    { left: '66%', top: '84%', s: 28, d: 0.2 },
    { left: '12%', top: '88%', s: 20, d: 1.1 },
  ]
  return (
    <div className="bm-vault-css" aria-hidden>
      {spots.map((p, i) => (
        <span
          key={i}
          className="bm-vault-coin"
          style={{ left: p.left, top: p.top, fontSize: p.s, animationDelay: `${p.d}s` }}
        >
          🪙
        </span>
      ))}
      <div className="bm-vault-css-shade" />
    </div>
  )
}

export default function BoardmanVaultScene() {
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
      scene.fog = new THREE.FogExp2(0x07060c, 0.03)

      const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80)
      camera.position.set(0, 0.7, 11.5)
      const look = new THREE.Vector3(0, 0.4, 0)
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
      canvas.closest('.bm-vault-stage')?.classList.add('bm-gl-on')
      gl.toneMapping = THREE.ACESFilmicToneMapping
      gl.toneMappingExposure = 1.08

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

      scene.add(new THREE.AmbientLight(0xb8a0ff, 0.32))
      const key = new THREE.DirectionalLight(0xffe0b0, 1.15)
      key.position.set(6, 9, 6)
      scene.add(key)
      const violet = new THREE.PointLight(0x7c3aed, 26, 40)
      violet.position.set(-7, 2.6, 6)
      scene.add(violet)
      const emerald = new THREE.PointLight(0x34d399, 9, 24)
      emerald.position.set(6, -1.5, 3)
      scene.add(emerald)
      const goldGlow = new THREE.PointLight(0xf5d78e, 6, 20)
      goldGlow.position.set(2, 3.5, 1)
      scene.add(goldGlow)

      // Coin: thin gold disc with a darker inner emboss ring.
      const gold = new THREE.MeshStandardMaterial({
        color: 0xf2d488,
        roughness: 0.24,
        metalness: 0.9,
        emissive: 0x4a2f0a,
        emissiveIntensity: 0.16,
      })
      const emboss = new THREE.MeshStandardMaterial({
        color: 0xcaa25e,
        roughness: 0.3,
        metalness: 0.85,
        emissive: 0x2f1c06,
        emissiveIntensity: 0.1,
      })
      const coinGeo = new THREE.CylinderGeometry(1, 1, 0.16, 36)
      const embossGeo = new THREE.CylinderGeometry(0.66, 0.66, 0.17, 36)

      const coins: Array<{
        g: InstanceType<typeof THREE.Object3D>
        baseY: number
        spin: number
        phase: number
        driftX: number
        driftZ: number
        tiltX: number
        tiltZ: number
      }> = []
      const rng = mulberry(0xbead)
      for (let i = 0; i < 18; i++) {
        const g = new THREE.Group()
        const disc = new THREE.Mesh(coinGeo, gold)
        const ring = new THREE.Mesh(embossGeo, emboss)
        ring.rotation.x = Math.PI / 2
        ring.position.y = 0.001
        g.add(disc, ring)
        g.scale.setScalar(0.32 + rng() * 0.55)
        g.position.set(
          -8 + rng() * 16,
          -1.6 + rng() * 5.4,
          -6.5 + rng() * 8.5
        )
        g.rotation.set(rng() * Math.PI, rng() * Math.PI, rng() * Math.PI)
        scene.add(g)
        coins.push({
          g,
          baseY: g.position.y,
          spin: (rng() - 0.5) * 0.9,
          phase: rng() * Math.PI * 2,
          driftX: (rng() - 0.5) * 0.5,
          driftZ: (rng() - 0.5) * 0.5,
          tiltX: (rng() - 0.5) * 0.08,
          tiltZ: (rng() - 0.5) * 0.08,
        })
      }

      // Gold dust
      const dustCount = 260
      const dustPos = new Float32Array(dustCount * 3)
      for (let i = 0; i < dustCount; i++) {
        dustPos[i * 3] = -9 + rng() * 18
        dustPos[i * 3 + 1] = -2.5 + rng() * 7
        dustPos[i * 3 + 2] = -7 + rng() * 9
      }
      const dustGeo = new THREE.BufferGeometry()
      dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3))
      const dustMat = new THREE.PointsMaterial({
        color: 0xf5d78e,
        size: 0.05,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      })
      const dust = new THREE.Points(dustGeo, dustMat)
      scene.add(dust)

      const cloud = new THREE.Group()
      coins.forEach((c) => cloud.add(c.g))
      scene.add(cloud)

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
        cloud.rotation.y = pointer.x * 0.14 + Math.sin(t * 0.12) * 0.06
        for (const c of coins) {
          c.g.rotation.y += c.spin * 0.016
          c.g.rotation.x += c.tiltX * 0.016
          c.g.rotation.z += c.tiltZ * 0.016
          c.g.position.y = c.baseY + Math.sin(t * 0.55 + c.phase) * 0.28
          c.g.position.x += c.driftX * 0.0006
          c.g.position.z += c.driftZ * 0.0006
        }
        dust.rotation.y = t * 0.02
        dust.position.y = Math.sin(t * 0.3) * 0.25
        camera.position.x = pointer.x * 0.55
        camera.position.y = 0.7 + pointer.y * 0.3
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
      <CssCoins />
      <canvas ref={canvasRef} className="bm-gl" aria-hidden />
    </>
  )
}

/** Tiny deterministic PRNG so the scene is stable across reloads. */
function mulberry(seed: number) {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
