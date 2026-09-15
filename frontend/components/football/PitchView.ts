'use client'
/**
 * Imperative three.js pitch scene used by the AFM tactics theater.
 * The React shell drives it through a narrow API so the render loop never
 * triggers React re-renders.
 *
 * Three presentation layers over the SAME timeline poses:
 *  - tokens        (tactical / coaching — pickable discs + labels)
 *  - bodies        (broadcast — kit-coloured players with a walk/run cycle)
 *  - stadium life  (crowd stands + LED boards + contact shadows, broadcast)
 * Switching layers is a visibility swap, never a rebuild.
 */
import * as THREE from 'three'
import { HALF_W, HALF_D } from '../../lib/afm'
import type { MinuteState, Pose } from '../../lib/broadcast'

export type CamMode = 'broadcast' | 'tactical' | 'behind'
export type BoardTool = 'select' | 'arrow' | 'zone' | 'cone'
export type PitchStyle = 'classic' | 'night' | 'obsidian' | 'chalkboard' | 'blueprint' | 'winter'

export interface TokenSpec {
  id: string
  name: string
  number: number
  x: number
  z: number
  color: string
  colorDark: string
}

export interface ViewTeamSpec {
  name: string
  color: string
  colorDark: string
  accent: string
  tokens: TokenSpec[]
}

export interface CoachMark {
  kind: 'arrow' | 'zone' | 'cone'
  color: string
  a: Pose
  b: Pose
}

export interface PitchViewCallbacks {
  onTokenDrag?: (side: 'home' | 'away', idx: number, x: number, z: number) => void
  onTokenHover?: (side: 'home' | 'away' | null, idx: number | null) => void
  onCoachCommit?: (mark: CoachMark) => void
  onReady?: () => void
}

const STYLES: Record<PitchStyle, { grass: string; grassAlt: string; line: string; bg: string; fog: string; runway: string }> = {
  classic: { grass: '#39a04f', grassAlt: '#339a49', line: '#f8fafc', bg: '#0e1a2b', fog: '#0e1a2b', runway: '#2a6a3a' },
  night: { grass: '#1d8a45', grassAlt: '#21964c', line: '#f0faf2', bg: '#050b16', fog: '#050b16', runway: '#124f2c' },
  obsidian: { grass: '#0a6b28', grassAlt: '#0b7530', line: '#d3f8e4', bg: '#000000', fog: '#020503', runway: '#0a4a1e' },
  chalkboard: { grass: '#152238', grassAlt: '#172643', line: '#eaf1fa', bg: '#020616', fog: '#020616', runway: '#0f1b30' },
  blueprint: { grass: '#124f9e', grassAlt: '#1355a8', line: '#bfe0ff', bg: '#04101f', fog: '#04101f', runway: '#0d3c74' },
  winter: { grass: '#d9eedd', grassAlt: '#cfe8d6', line: '#0f5c33', bg: '#0d1a2b', fog: '#0d1a2b', runway: '#b8dcc2' },
}

const GOAL_W = 7.32
const GOAL_H = 2.44
const GOAL_DEPTH = 2.0
const TV_NEAR_SIDE_Z = -(HALF_D + 6.5) // camera never crosses onto the pitch

function makeGrassTexture(style: PitchStyle): THREE.CanvasTexture {
  const s = STYLES[style]
  const c = document.createElement('canvas')
  c.width = 64
  c.height = 256
  const ctx = c.getContext('2d')!
  ctx.fillStyle = s.grass
  ctx.fillRect(0, 0, 64, 256)
  ctx.fillStyle = s.grassAlt
  for (let i = 0; i < 8; i++) if (i % 2 === 0) ctx.fillRect(0, i * 32, 64, 32)
  // faint noise so the mowing bands read as grass, not stripes
  for (let i = 0; i < 900; i++) {
    ctx.fillStyle = Math.random() < 0.5 ? 'rgba(255,255,255,0.022)' : 'rgba(0,0,0,0.03)'
    ctx.fillRect(Math.floor(Math.random() * 64), Math.floor(Math.random() * 256), 2, 2)
  }
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

function makeLabelTexture(text: string, font: string, color: string, w = 256, h = 128): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')!
  ctx.font = font
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = color
  ctx.fillText(text, w / 2, h / 2)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

/** Crowd: seated spectators in two tiers — rows of torso blobs with varied
 *  colours, separated by deck gaps. Tiled along each stand. */
function makeCrowdTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 256
  const ctx = c.getContext('2d')!
  ctx.fillStyle = '#10151f'
  ctx.fillRect(0, 0, 512, 256)
  // deck divider bands
  ctx.fillStyle = '#0a0e15'
  ctx.fillRect(0, 112, 512, 34)
  ctx.fillRect(0, 6, 512, 8)
  const colors = ['#a7b0c0', '#d8dde6', '#efeff2', '#c25a3f', '#ad3a2e', '#4566b8', '#2f4a97', '#5f8a5a', '#a05b8f', '#cd9b3c']
  const tiers = [
    { y0: 14, y1: 108 },
    { y0: 148, y1: 248 },
  ]
  for (const tier of tiers) {
    const h = tier.y1 - tier.y0
    const rows = 13
    const rowH = h / rows
    for (let ri = 0; ri < rows; ri++) {
      const y = tier.y0 + (ri + 0.5) * rowH
      const gap = 0.5 + Math.random() * 1.2
      let x = gap
      while (x < 512) {
        const w = 1.4 + Math.random() * 2.6
        const ph = rowH * (0.55 + Math.random() * 0.5)
        ctx.fillStyle = colors[Math.floor(Math.random() * colors.length)]
        ctx.globalAlpha = 0.7 + Math.random() * 0.3
        ctx.fillRect(x, y - ph / 2, w, ph)
        x += w + gap
      }
    }
  }
  ctx.globalAlpha = 1
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  tex.wrapS = THREE.RepeatWrapping
  return tex
}

/** LED board band: text is baked twice so a scrolling texture offset loops seamlessly. */
function makeLedTexture(left: string, right: string, accent: string): THREE.CanvasTexture {
  const c = document.createElement('canvas')
  c.width = 1536
  c.height = 64
  const ctx = c.getContext('2d')!
  ctx.fillStyle = '#070b12'
  ctx.fillRect(0, 0, 1536, 64)
  ctx.font = '700 40px Inter, system-ui, sans-serif'
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'left'
  // split the phrase so club names render in their accent colour
  const parts: { t: string; col: string }[] = [
    { t: 'AFM LIVE', col: '#fbbf24' },
    { t: left, col: accent },
    { t: 'vs', col: '#94a3b8' },
    { t: right, col: '#e2e8f0' },
    { t: 'AGENTIC FOOTBALL MANAGERS', col: '#64748b' },
  ]
  const spacing = '   ·   '
  for (let rep = 0; rep < 3; rep++) {
    let cursor = rep * 512
    for (const p of parts) {
      ctx.fillStyle = p.col
      ctx.fillText(p.t, cursor, 32)
      cursor += ctx.measureText(p.t).width
      ctx.fillStyle = '#334155'
      ctx.fillText(spacing, cursor, 32)
      cursor += ctx.measureText(spacing).width
    }
  }
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.wrapS = THREE.RepeatWrapping
  tex.anisotropy = 4
  return tex
}

function shortName(name: string): string {
  const clean = name.replace(/[^a-zA-Z0-9]/g, ' ').trim().split(/\s+/)
  const head = (clean[0] ?? 'AFC').toUpperCase().slice(0, 4)
  return clean.length > 1 ? `${head} ${clean[1].toUpperCase().slice(0, 2)}` : head
}

function groundPoint(evt: PointerEvent, el: HTMLElement, camera: THREE.PerspectiveCamera): Pose | null {
  const rect = el.getBoundingClientRect()
  const ndc = new THREE.Vector2(
    ((evt.clientX - rect.left) / rect.width) * 2 - 1,
    -((evt.clientY - rect.top) / rect.height) * 2 + 1,
  )
  const ray = new THREE.Raycaster()
  ray.setFromCamera(ndc, camera)
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
  const out = new THREE.Vector3()
  return ray.ray.intersectPlane(plane, out) ? { x: out.x, z: out.z } : null
}

/* ------------------------------------------------------------ actor body */
interface BodyRig {
  root: THREE.Group
  tokenViz: THREE.Group
  bodyGroup: THREE.Group
  legL: THREE.Group
  legR: THREE.Group
  armL: THREE.Group
  armR: THREE.Group
  lean: THREE.Group
  phase: number
  heading: number
}

const BODY_SKIN = '#d9a066'

function buildActor(spec: TokenSpec): BodyRig {
  const root = new THREE.Group()
  root.rotation.order = 'YXZ'

  /* --- token layer (disc + labels) --- */
  const tokenViz = new THREE.Group()
  const disc = new THREE.Mesh(
    new THREE.CylinderGeometry(1.0, 1.2, 0.3, 30),
    new THREE.MeshStandardMaterial({ color: spec.color, roughness: 0.5, metalness: 0.08 }),
  )
  disc.position.y = 0.15
  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(1.36, 0.09, 8, 48),
    new THREE.MeshStandardMaterial({ color: spec.colorDark, roughness: 0.4, metalness: 0.35 }),
  )
  ring.rotation.x = Math.PI / 2
  ring.position.y = 0.3
  tokenViz.add(disc, ring)
  const numTex = makeLabelTexture(String(spec.number), '700 76px Inter, system-ui, sans-serif', '#ffffff')
  const num = new THREE.Sprite(new THREE.SpriteMaterial({ map: numTex, transparent: true, depthWrite: false }))
  num.scale.set(2.0, 1.0, 1)
  num.position.y = 1.25
  tokenViz.add(num)
  const nameTex = makeLabelTexture(spec.name.toUpperCase(), '600 32px Inter, system-ui, sans-serif', '#ffffff')
  const name = new THREE.Sprite(new THREE.SpriteMaterial({ map: nameTex, transparent: true, depthWrite: false, opacity: 0.85 }))
  name.scale.set(4.2, 2.1, 1)
  name.position.y = -0.95
  tokenViz.add(name)
  root.add(tokenViz)

  /* --- body layer (built facing +z; yaw comes from heading) --- */
  const bodyGroup = new THREE.Group()
  const kit = new THREE.Color(spec.color)
  // a touch of emissive keeps the kit hue true even where shadows/ACES dull it
  const jersey = new THREE.MeshStandardMaterial({ color: spec.color, roughness: 0.66, emissive: kit, emissiveIntensity: 0.32 })
  const sockMat = new THREE.MeshStandardMaterial({ color: spec.color, roughness: 0.7, emissive: kit, emissiveIntensity: 0.14 })
  const shorts = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.75 })
  const skinMat = new THREE.MeshStandardMaterial({ color: BODY_SKIN, roughness: 0.65 })
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x1c2026, roughness: 0.85 })

  const legGeo = new THREE.BoxGeometry(0.3, 1.06, 0.34)
  const legL = new THREE.Group()
  legL.position.set(-0.15, 0.94, 0)
  const mL = new THREE.Mesh(legGeo, sockMat)
  mL.position.y = -0.52
  const bootL = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.2, 0.44), darkMat)
  bootL.position.set(0, -1.03, 0.05)
  legL.add(mL, bootL)
  const legR = new THREE.Group()
  legR.position.set(0.15, 0.94, 0)
  const mR = new THREE.Mesh(legGeo, sockMat)
  mR.position.y = -0.52
  const bootR = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.2, 0.44), darkMat)
  bootR.position.set(0, -1.03, 0.05)
  legR.add(mR, bootR)

  const lean = new THREE.Group()
  const hips = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.28, 0.4), shorts)
  hips.position.y = 1.02
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.66, 0.8, 0.46), jersey)
  torso.position.y = 1.5
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.25, 16, 12), skinMat)
  head.position.y = 1.98
  const hair = new THREE.Mesh(new THREE.SphereGeometry(0.23, 12, 10), darkMat)
  hair.position.set(0, 2.02, 0.02)
  lean.add(hips, torso, head, hair)
  bodyGroup.add(legL, legR, lean)

  // arms (jersey-coloured) swing opposite the legs — the biggest run signal
  const armGeo = new THREE.BoxGeometry(0.24, 0.72, 0.26)
  const armMat = new THREE.MeshStandardMaterial({ color: spec.color, roughness: 0.66, emissive: kit, emissiveIntensity: 0.22 })
  const armL = new THREE.Group()
  armL.position.set(-0.47, 1.82, 0)
  const aL = new THREE.Mesh(armGeo, armMat)
  aL.position.y = -0.36
  armL.add(aL)
  const armR = new THREE.Group()
  armR.position.set(0.47, 1.82, 0)
  const aR = new THREE.Mesh(armGeo, armMat)
  aR.position.y = -0.36
  armR.add(aR)
  lean.add(armL, armR)
  root.add(tokenViz, bodyGroup)

  for (const m of [mL, bootL, mR, bootR, hips, torso, head, hair, aL, aR]) m.castShadow = true
  return { root, tokenViz, bodyGroup, legL, legR, armL, armR, lean, phase: Math.random() * Math.PI * 2, heading: 0 }
}

export class PitchView {
  private renderer!: THREE.WebGLRenderer
  private scene!: THREE.Scene
  private camera!: THREE.PerspectiveCamera
  private container: HTMLElement
  private style: PitchStyle
  private cb: PitchViewCallbacks
  private raf = 0
  private disposed = false
  private contextLost = false
  private ro: ResizeObserver | null = null
  private nowMs = 0

  private pitchGroup = new THREE.Group()
  private stadiumGroup = new THREE.Group()
  private playersGroup = new THREE.Group()
  private coachGroup = new THREE.Group()
  private ledMeshes: THREE.Mesh[] = []
  private ledTextures: THREE.CanvasTexture[] = []
  private ballMesh!: THREE.Mesh
  private actors: { home: BodyRig[]; away: BodyRig[] } = { home: [], away: [] }
  private idleFrom: { home: Pose[]; away: Pose[] } = { home: [], away: [] }
  private prevTargets: { home: Pose[]; away: Pose[] } = { home: [], away: [] }

  private camMode: CamMode = 'tactical'
  private camFrom = new THREE.Vector3(0, 60, 34)
  private camTo = new THREE.Vector3()
  private camLook = new THREE.Vector3()
  private playDir = 1
  private playDirHold = 0
  private heat = 0
  private ballPos: Pose = { x: 0, z: 0 }
  private teamShort: { home: string; away: string } = { home: 'HOME', away: 'AWAY' }
  private teamAccent: { home: string; away: string } = { home: '#dc2626', away: '#eab308' }

  private editable: 'home' | 'away' | null = null
  private tool: BoardTool = 'select'
  private hovered: { side: 'home' | 'away'; idx: number } | null = null
  private drag: { side: 'home' | 'away'; idx: number; moved: boolean } | null = null
  private drawStart: Pose | null = null

  private timeline: MinuteState[] | null = null
  private simTime = 0
  private lastT = performance.now()
  private lastCoachMarks: CoachMark[] = []
  private previewMark: CoachMark | null = null

  constructor(container: HTMLElement, style: PitchStyle = 'night', cb: PitchViewCallbacks = {}) {
    this.container = container
    this.style = style
    this.cb = cb
  }

  /** Mount the renderer. Throws when WebGL is unavailable — catch in the shell. */
  init(): this {
    const s = STYLES[this.style]
    let renderer: THREE.WebGLRenderer | null = null
    try {
      renderer = this.createRenderer()
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
      renderer.setSize(this.container.clientWidth || 960, this.container.clientHeight || 560)
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.toneMapping = THREE.ACESFilmicToneMapping
      renderer.toneMappingExposure = 1.35
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFSoftShadowMap
      this.container.appendChild(renderer.domElement)
      this.renderer = renderer
    } catch (e) {
      // WebGL unavailable (lost context, context exhaustion, GPU blocklist).
      // Clean up anything already attached so no canvas/context leaks, then
      // let the shell surface the failure instead of crashing the page.
      if (renderer) {
        try {
          renderer.dispose()
        } catch {
          /* ignore */
        }
        renderer.domElement.remove()
      }
      throw e instanceof Error ? e : new Error(`WebGL unavailable: ${String(e)}`)
    }

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(s.bg)
    scene.fog = new THREE.Fog(s.fog, 160, 520)
    this.scene = scene

    const camera = new THREE.PerspectiveCamera(42, (this.container.clientWidth || 960) / (this.container.clientHeight || 560), 0.1, 900)
    camera.position.copy(this.camFrom)
    camera.lookAt(this.camTo)
    this.camera = camera

    this.buildStadium()
    this.buildPitch()
    this.buildGoals()
    this.buildBall()
    this.buildSun()
    this.scene.add(this.stadiumGroup, this.pitchGroup, this.playersGroup, this.coachGroup)

    const el = renderer.domElement
    el.style.touchAction = 'none'
    el.style.cursor = 'grab'
    el.addEventListener('pointerdown', this.onPointerDown)
    el.addEventListener('pointermove', this.onPointerMove)
    el.addEventListener('pointerup', this.onPointerUp)
    el.addEventListener('pointerleave', this.onPointerLeave)
    el.addEventListener('dblclick', this.onDoubleClick)
    el.addEventListener('webglcontextlost', this.onContextLost)
    el.addEventListener('webglcontextrestored', this.onContextRestored)

    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(this.container)
    this.loop()
    this.cb.onReady?.()
    return this
  }

  /**
   * Create the WebGL renderer, retrying with progressively lighter context
   * attributes if the first attempt is refused (antialias + high-performance
   * is the combination most likely to fail — macOS multi-GPU, context
   * pressure, GPU blocklist). Throws when every attempt fails.
   */
  private createRenderer(): THREE.WebGLRenderer {
    const attempts: THREE.WebGLRendererParameters[] = [
      { antialias: true, powerPreference: 'high-performance' },
      { antialias: false, powerPreference: 'high-performance' },
      { antialias: false, powerPreference: 'default' },
    ]
    let lastErr: unknown = null
    for (const opts of attempts) {
      try {
        return new THREE.WebGLRenderer(opts)
      } catch (e) {
        lastErr = e
      }
    }
    throw lastErr instanceof Error ? lastErr : new Error('WebGL context could not be created')
  }

  /* ------------------------------------------------------------ environment */

  private buildSun() {
    // neutral, broadcast-grade daylight — warm light is what kills kit colours
    const hemi = new THREE.HemisphereLight(0xeef4ff, 0x1d2a20, 1.15)
    this.scene.add(hemi)
    const sun = new THREE.DirectionalLight(0xfff8ef, 2.7)
    sun.position.set(60, 150, 46)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    sun.shadow.camera.left = -75
    sun.shadow.camera.right = 75
    sun.shadow.camera.top = 75
    sun.shadow.camera.bottom = -75
    sun.shadow.camera.near = 10
    sun.shadow.camera.far = 420
    sun.shadow.bias = -0.0005
    this.scene.add(sun)
    // soft fill from the opposite side so the far-side kits don't go black
    const fill = new THREE.DirectionalLight(0xc9d8ff, 0.65)
    fill.position.set(-80, 60, -60)
    this.scene.add(fill)
  }

  private buildStadium() {
    const s = STYLES[this.style]
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(460, 64),
      new THREE.MeshStandardMaterial({ color: s.fog, roughness: 1 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.position.y = -0.7
    this.stadiumGroup.add(floor)

    const crowdTex = makeCrowdTexture()
    crowdTex.repeat.set(5, 1)
    const standMat = () => {
      const m = new THREE.MeshLambertMaterial({ map: crowdTex, emissiveMap: crowdTex })
      m.emissive = new THREE.Color(0xffffff)
      m.emissiveIntensity = 0.58
      return m
    }
    const roofMat = new THREE.MeshStandardMaterial({ color: 0x151b28, roughness: 0.6, metalness: 0.25 })

    // side stands (long touchlines), camera sits in front of the near one
    const sideStand = new THREE.PlaneGeometry(150, 17)
    for (const sz of [-1, 1] as const) {
      const wall = new THREE.Mesh(sideStand, standMat())
      wall.position.set(0, 7.6, sz * (HALF_D + 22))
      wall.lookAt(0, 7.6, 0)
      this.stadiumGroup.add(wall)
      const roof = new THREE.Mesh(new THREE.BoxGeometry(156, 1.1, 11), roofMat)
      roof.position.set(0, 17.4, sz * (HALF_D + 22))
      this.stadiumGroup.add(roof)
    }
    // goal-end stands
    const endStand = new THREE.PlaneGeometry(104, 17)
    for (const sx of [-1, 1] as const) {
      const wall = new THREE.Mesh(endStand, standMat())
      wall.position.set(sx * (HALF_W + 22), 7.6, 0)
      wall.lookAt(0, 7.6, 0)
      this.stadiumGroup.add(wall)
      const roof = new THREE.Mesh(new THREE.BoxGeometry(104, 1.1, 11), roofMat)
      roof.position.set(sx * (HALF_W + 22), 17.4, 0)
      this.stadiumGroup.add(roof)
    }

    // floodlight pylons, one per corner, clear of the stands
    for (const [lx, lz] of [[-86, -66], [86, -66], [-86, 66], [86, 66]] as const) {
      const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.7, 1.1, 38, 8),
        new THREE.MeshStandardMaterial({ color: 0x232b38, roughness: 0.9 }),
      )
      pole.position.set(lx, 19, lz)
      this.stadiumGroup.add(pole)
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(20, 3, 5),
        new THREE.MeshStandardMaterial({ color: 0x141a24, emissive: 0x9db8ff, emissiveIntensity: 0.7 }),
      )
      head.position.set(lx, 38.4, lz)
      this.stadiumGroup.add(head)
    }

    // LED boards along both touchlines
    for (const sz of [-1, 1] as const) {
      const tex = makeLedTexture('HOME', 'AWAY', '#fbbf24')
      tex.wrapS = THREE.RepeatWrapping
      const mat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0xffffff,
        emissiveMap: tex,
        emissiveIntensity: 1.4,
        roughness: 0.6,
      })
      const board = new THREE.Mesh(new THREE.BoxGeometry(96, 1.05, 0.3), mat)
      board.position.set(0, 1.05, sz * (HALF_D + 2.6))
      this.stadiumGroup.add(board)
      this.ledMeshes.push(board)
      this.ledTextures.push(tex)
    }
  }

  private buildPitch() {
    const s = STYLES[this.style]
    const apron = new THREE.Mesh(
      new THREE.PlaneGeometry(118, 82),
      new THREE.MeshBasicMaterial({ color: s.runway }),
    )
    apron.rotation.x = -Math.PI / 2
    apron.position.y = -0.012
    this.pitchGroup.add(apron)

    const grass = new THREE.Mesh(
      new THREE.PlaneGeometry(105, 68),
      new THREE.MeshStandardMaterial({ map: makeGrassTexture(this.style), roughness: 0.92 }),
    )
    grass.rotation.x = -Math.PI / 2
    grass.position.y = 0
    grass.receiveShadow = true
    this.pitchGroup.add(grass)

    const pts: number[] = []
    const seg = (ax: number, az: number, bx: number, bz: number) => pts.push(ax, 0.02, az, bx, 0.02, bz)
    const W = HALF_W
    const D = HALF_D
    // border + halfway + centre circle/spot
    seg(-W, -D, W, -D)
    seg(W, -D, W, D)
    seg(W, D, -W, D)
    seg(-W, D, -W, -D)
    seg(0, -D, 0, D)
    arcSeg(0, 0, 9.15, 0, Math.PI * 2, seg)
    dotSeg(0, 0, seg)

    for (const sign of [1, -1] as const) {
      const bx = sign * W
      boxSeg(bx - sign * 16.5, -20.16, bx, 20.16, seg)
      boxSeg(bx - sign * 5.5, -9.16, bx, 9.16, seg)
      dotSeg(bx - sign * 11, 0, seg)
      const cosLimit = 5.5 / 9.15
      const aLimit = Math.acos(cosLimit)
      const a0 = sign > 0 ? Math.PI - aLimit : -aLimit
      const a1 = sign > 0 ? Math.PI + aLimit : aLimit
      arcSeg(bx - sign * 11, 0, 9.15, a0, a1, seg, 24)
    }
    const cornerStart = (sx: number, sz: number) => (sx > 0 ? (sz > 0 ? Math.PI : Math.PI / 2) : sz > 0 ? (3 * Math.PI) / 2 : 0)
    for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]] as const) {
      arcSeg(sx * (W - 0.15), sz * (D - 0.15), 1.1, cornerStart(sx, sz), cornerStart(sx, sz) + Math.PI / 2, seg, 10)
    }

    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    this.pitchGroup.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: new THREE.Color(s.line) })))
  }

  private buildGoals() {
    const postMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3, metalness: 0.7 })
    const postGeo = new THREE.BoxGeometry(0.14, GOAL_H, 0.14)
    const barGeo = new THREE.BoxGeometry(0.14, 0.14, GOAL_W + 0.14)
    for (const sign of [1, -1] as const) {
      const gx = sign * (HALF_W + 0.1)
      const g = new THREE.Group()
      const lp = new THREE.Mesh(postGeo, postMat)
      lp.position.set(gx, GOAL_H / 2, -GOAL_W / 2)
      const rp = new THREE.Mesh(postGeo, postMat)
      rp.position.set(gx, GOAL_H / 2, GOAL_W / 2)
      const bar = new THREE.Mesh(barGeo, postMat)
      bar.position.set(gx, GOAL_H, 0)
      g.add(lp, rp, bar)
      const netMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.05,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
      const back = new THREE.Mesh(new THREE.PlaneGeometry(GOAL_W, GOAL_H), netMat)
      back.position.set(sign * (HALF_W + GOAL_DEPTH), GOAL_H / 2, 0)
      back.rotation.y = Math.PI / 2
      const side = (dz: number) => {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(GOAL_DEPTH, GOAL_H), netMat)
        m.position.set(sign * (HALF_W + GOAL_DEPTH / 2), GOAL_H / 2, dz)
        m.rotation.y = Math.PI / 2
        m.rotation.z = Math.PI / 2
        return m
      }
      g.add(back, side(-GOAL_W / 2), side(GOAL_W / 2))
      this.pitchGroup.add(g)
    }
  }

  private buildBall() {
    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.5, 24, 18),
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.28, metalness: 0.08 }),
    )
    ball.position.set(0, 0.5, 0)
    ball.castShadow = true
    this.scene.add(ball)
    this.ballMesh = ball
  }

  /* ------------------------------------------------------------ public API */

  setTeams(home: ViewTeamSpec, away: ViewTeamSpec) {
    for (const child of [...this.playersGroup.children]) {
      this.playersGroup.remove(child)
      this.disposeObj(child)
    }
    this.actors = { home: [], away: [] }
    this.idleFrom = { home: [], away: [] }
    this.prevTargets = { home: [], away: [] }
    this.timeline = null
    this.simTime = 0
    this.heat = 0

    this.teamShort = { home: shortName(home.name), away: shortName(away.name) }
    this.teamAccent = { home: home.color, away: away.color }
    if (this.ledTextures.length) this.bakeLed()

    for (const side of ['home', 'away'] as const) {
      const spec = side === 'home' ? home : away
      this.idleFrom[side] = spec.tokens.map((t) => ({ x: t.x, z: t.z }))
      this.actors[side] = spec.tokens.map((t, i) => {
        const rig = buildActor(t)
        rig.root.position.set(t.x, 0, t.z)
        rig.root.userData = { side, idx: i, id: t.id }
        this.playersGroup.add(rig.root)
        return rig
      })
    }
    this.applyLook(this.camMode)
    this.setBall({ x: 0, z: 0 })
  }

  setBall(p: Pose) {
    this.ballPos = p
    this.ballMesh.position.set(p.x, 0.5, p.z)
  }

  setTimeline(tl: MinuteState[] | null) {
    this.timeline = tl
    this.simTime = 0
    this.heat = 0
    this.lastCoachMarks = []
    this.previewMark = null
  }

  setSimTime(minute: number) {
    const n = this.timeline?.length ?? 91
    this.simTime = Math.max(0, Math.min(n - 1, minute))
  }

  setEditable(side: 'home' | 'away' | null) {
    this.editable = side
    if (!side) this.drag = null
  }

  setTool(tool: BoardTool) {
    this.tool = tool
    this.drawStart = null
    this.previewMark = null
    this.renderer.domElement.style.cursor = tool === 'select' ? 'grab' : tool === 'cone' ? 'copy' : 'crosshair'
  }

  /** Replace the full set of coach marks; preview is the in-progress draw. */
  setCoachMarks(marks: CoachMark[], preview: CoachMark | null = null) {
    this.lastCoachMarks = marks
    this.previewMark = preview
    for (const child of [...this.coachGroup.children]) {
      this.coachGroup.remove(child)
      this.disposeObj(child)
    }
    for (const m of marks) this.coachGroup.add(this.buildCoachMark(m))
    if (preview) this.coachGroup.add(this.buildCoachMark(preview))
  }

  setCamera(mode: CamMode) {
    if (mode === this.camMode) return
    this.camMode = mode
    this.applyLook(mode)
  }

  /** token look (pickable) vs body look (broadcast) */
  private applyLook(mode: CamMode) {
    const bodies = mode === 'broadcast'
    for (const side of ['home', 'away'] as const) {
      for (const rig of this.actors[side]) {
        rig.tokenViz.visible = !bodies
        rig.bodyGroup.visible = bodies
      }
    }
    this.renderer.shadowMap.enabled = bodies
    // broadcast runs a tele lens (TV main cam is a long zoom, not a wide)
    this.camera.fov = mode === 'broadcast' ? 26 : mode === 'tactical' ? 44 : 58
    this.camera.updateProjectionMatrix()
    // camera teleport to the new rig so the switch is instant, not a swoop
    this.snapCamera()
  }

  private snapCamera() {
    const pos = new THREE.Vector3()
    const look = new THREE.Vector3()
    this.rigTargets(pos, look)
    this.camFrom.copy(pos)
    this.camTo.copy(look)
    this.camLook.copy(look)
    this.camera.position.copy(pos)
    this.camera.lookAt(look)
  }

  setStyle(style: PitchStyle) {
    if (style === this.style) return
    this.style = style
    const s = STYLES[style]
    this.scene.background = new THREE.Color(s.bg)
    if (this.scene.fog) (this.scene.fog as THREE.Fog).color = new THREE.Color(s.fog)
    for (const group of [this.pitchGroup, this.stadiumGroup]) {
      this.scene.remove(group)
      this.disposeObj(group)
    }
    this.pitchGroup = new THREE.Group()
    this.stadiumGroup = new THREE.Group()
    this.ledMeshes = []
    this.ledTextures = []
    this.buildStadium()
    this.buildPitch()
    this.buildGoals()
    this.scene.add(this.stadiumGroup, this.pitchGroup)
    this.bakeLed()
  }

  resize() {
    const w = this.container.clientWidth || 960
    const h = this.container.clientHeight || 560
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    if (!this.renderer) return // init never completed
    this.ro?.disconnect()
    const el = this.renderer.domElement
    el.removeEventListener('pointerdown', this.onPointerDown)
    el.removeEventListener('pointermove', this.onPointerMove)
    el.removeEventListener('pointerup', this.onPointerUp)
    el.removeEventListener('pointerleave', this.onPointerLeave)
    el.removeEventListener('dblclick', this.onDoubleClick)
    el.removeEventListener('webglcontextlost', this.onContextLost)
    el.removeEventListener('webglcontextrestored', this.onContextRestored)
    el.remove()
    try {
      this.renderer.dispose()
    } catch {
      // dispose() can throw on a lost context — nothing left to do.
    }
  }

  private disposeObj(o: THREE.Object3D) {
    o.traverse((child) => {
      const mesh = child as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const mat = mesh.material as THREE.Material | THREE.Material[] | undefined
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
      else if (mat) mat.dispose()
    })
  }

  /* ------------------------------------------------------------ interaction */

  private onContextLost = (e: Event) => {
    // Prevent default so the browser offers the context back on restore.
    e.preventDefault()
    this.contextLost = true
    cancelAnimationFrame(this.raf)
  }

  private onContextRestored = () => {
    this.contextLost = false
    this.lastT = performance.now()
    this.resize()
    this.raf = requestAnimationFrame(this.loop)
  }

  private onPointerDown = (evt: PointerEvent) => {
    if (evt.button !== 0) return
    const p = groundPoint(evt, this.renderer.domElement, this.camera)
    if (!p) return
    if (this.tool !== 'select') {
      this.drawStart = p
      return
    }
    const side = this.editable
    if (!side) return
    const idx = this.nearestToken(side, p, 2.8)
    if (idx == null) return
    this.drag = { side, idx, moved: false }
    this.renderer.domElement.setPointerCapture(evt.pointerId)
  }

  private onPointerMove = (evt: PointerEvent) => {
    const p = groundPoint(evt, this.renderer.domElement, this.camera)
    if (!p) return
    if (this.tool !== 'select' && this.drawStart) {
      this.setCoachMarks(this.lastCoachMarks, this.buildDrawMark(this.drawStart, p))
      return
    }
    if (this.drag) {
      const { side, idx } = this.drag
      this.drag.moved = true
      const x = Math.max(-HALF_W + 0.8, Math.min(HALF_W - 0.8, p.x))
      const z = Math.max(-HALF_D + 0.8, Math.min(HALF_D - 0.8, p.z))
      const rig = this.actors[side][idx]
      if (rig) rig.root.position.set(x, 0, z)
      if (this.idleFrom[side][idx]) this.idleFrom[side][idx] = { x, z }
      this.cb.onTokenDrag?.(side, idx, x, z)
      return
    }
    const side = this.editable
    if (!side) return
    const idx = this.nearestToken(side, p, 2.8)
    this.setHover(idx == null ? null : { side, idx })
  }

  private onPointerUp = (evt: PointerEvent) => {
    const p = groundPoint(evt, this.renderer.domElement, this.camera)
    if (this.tool !== 'select' && this.drawStart && p) {
      const mark = this.buildDrawMark(this.drawStart, p)
      this.setCoachMarks(this.lastCoachMarks)
      this.drawStart = null
      this.cb.onCoachCommit?.(mark)
      return
    }
    if (this.drag) {
      if (!this.drag.moved) this.cb.onTokenHover?.(this.drag.side, this.drag.idx)
      this.drag = null
    }
    this.renderer.domElement.releasePointerCapture?.(evt.pointerId)
  }

  private onPointerLeave = () => {
    this.drag = null
    this.drawStart = null
    this.setCoachMarks(this.lastCoachMarks)
    this.setHover(null)
  }

  private onDoubleClick = () => {
    this.setCamera(this.camMode === 'broadcast' ? 'tactical' : 'broadcast')
  }

  private setHover(h: { side: 'home' | 'away'; idx: number } | null) {
    if (this.hovered?.side === h?.side && this.hovered?.idx === h?.idx) return
    this.hovered = h
    this.cb.onTokenHover?.(h?.side ?? null, h?.idx ?? null)
    const el = this.renderer?.domElement
    if (el) el.style.cursor = h ? 'move' : this.tool === 'select' ? 'grab' : 'crosshair'
  }

  private nearestToken(side: 'home' | 'away', p: Pose, maxDist: number): number | null {
    let best = -1
    let bestD = maxDist
    this.actors[side].forEach((rig, i) => {
      const d = Math.hypot(rig.root.position.x - p.x, rig.root.position.z - p.z)
      if (d < bestD) {
        bestD = d
        best = i
      }
    })
    return best >= 0 ? best : null
  }

  /* ------------------------------------------------------------ LED boards */

  private bakeLed() {
    const tex = makeLedTexture(this.teamShort.home, this.teamShort.away, this.teamAccent.home)
    tex.wrapS = THREE.RepeatWrapping
    for (const old of this.ledTextures) old.dispose()
    this.ledTextures = [tex]
    this.ledMeshes.forEach((m) => {
      const mat = m.material as THREE.MeshStandardMaterial
      mat.emissiveMap?.dispose()
      mat.emissiveMap = tex
      mat.needsUpdate = true
    })
  }

  /* ------------------------------------------------------------ coach marks */

  private buildDrawMark(a: Pose, b: Pose): CoachMark {
    const colors: Record<BoardTool, string> = { select: '#38bdf8', arrow: '#38bdf8', zone: '#fbbf24', cone: '#fb923c' }
    const color = colors[this.tool] ?? '#38bdf8'
    if (this.tool === 'cone') return { kind: 'cone', color, a, b: a }
    if (this.tool === 'zone') return { kind: 'zone', color, a, b }
    return { kind: 'arrow', color, a, b }
  }

  private buildCoachMark(mark: CoachMark): THREE.Object3D {
    const root = new THREE.Group()
    if (mark.kind === 'arrow') {
      const a = new THREE.Vector3(mark.a.x, 0.08, mark.a.z)
      const b = new THREE.Vector3(mark.b.x, 0.08, mark.b.z)
      const dir = new THREE.Vector3().subVectors(b, a)
      const len = dir.length()
      if (len < 0.4) return root
      dir.normalize()
      const headLen = Math.min(1.6, len * 0.35)
      const tail = new THREE.Vector3().copy(b).addScaledVector(dir, -headLen)
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([a, tail]),
        new THREE.LineBasicMaterial({ color: mark.color, transparent: true, opacity: 0.95 }),
      )
      root.add(line)
      const head = new THREE.Mesh(
        new THREE.ConeGeometry(0.42, headLen, 10),
        new THREE.MeshBasicMaterial({ color: mark.color }),
      )
      head.position.copy(tail).addScaledVector(dir, headLen / 2)
      head.position.y = 0.3
      head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir)
      root.add(head)
    } else if (mark.kind === 'zone') {
      const w = Math.max(1.2, Math.abs(mark.b.x - mark.a.x))
      const d = Math.max(1.2, Math.abs(mark.b.z - mark.a.z))
      const cx = (mark.a.x + mark.b.x) / 2
      const cz = (mark.a.z + mark.b.z) / 2
      const fill = new THREE.Mesh(
        new THREE.PlaneGeometry(w, d),
        new THREE.MeshBasicMaterial({ color: mark.color, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false }),
      )
      fill.rotation.x = -Math.PI / 2
      fill.position.set(cx, 0.06, cz)
      root.add(fill)
      const hw = w / 2
      const hd = d / 2
      const border = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(cx - hw, 0.09, cz - hd),
          new THREE.Vector3(cx + hw, 0.09, cz - hd),
          new THREE.Vector3(cx + hw, 0.09, cz + hd),
          new THREE.Vector3(cx - hw, 0.09, cz + hd),
          new THREE.Vector3(cx - hw, 0.09, cz - hd),
        ]),
        new THREE.LineBasicMaterial({ color: mark.color }),
      )
      root.add(fill, border)
    } else {
      const cone = new THREE.Mesh(
        new THREE.ConeGeometry(0.5, 1.2, 12),
        new THREE.MeshBasicMaterial({ color: mark.color }),
      )
      cone.position.set(mark.a.x, 0.6, mark.a.z)
      root.add(cone)
    }
    return root
  }

  /* ------------------------------------------------------------ camera rigs */

  /** Desired camera pos + look-at for the current mode (may follow the ball). */
  private rigTargets(outPos: THREE.Vector3, outLook: THREE.Vector3) {
    const b = this.ballPos
    const havePlay = Boolean(this.timeline)
    const heat = this.heat
    const zoom = 1 - heat * 0.13

    if (this.camMode === 'tactical') {
      const fx = havePlay ? b.x * 0.38 : 0
      const fz = havePlay ? b.z * 0.42 : 0
      outPos.set(fx, 60 * zoom, 36 + fz)
      outLook.set(fx, 0, fz)
      return
    }

    if (this.camMode === 'behind') {
      // behind the goal the ball is heading for (hysteresis keeps it stable)
      let s = this.playDir
      if (!havePlay) s = 1
      const gx = s * (HALF_W + 9)
      const relX = havePlay ? b.x - s * HALF_W : 0
      const bx = havePlay ? s * 14 + relX * 0.55 : s * 4
      const bz = havePlay ? b.z * 0.7 : 0
      outPos.set(gx, 10.5 * zoom, bz)
      outLook.set(bx, 0.8, bz * 1.3)
      return
    }

    // broadcast: TV gantry rig — up in the stand, damped along the play
    const d = havePlay ? b.x : 0
    // infer attack direction from ball movement with hysteresis
    if (havePlay) {
      const last = this.camLook.x
      const vel = d - last
      if (vel > 0.5) {
        this.playDir = 1
        this.playDirHold = 0
      } else if (vel < -0.5) {
        this.playDir = -1
        this.playDirHold = 0
      } else {
        this.playDirHold++
        if (this.playDirHold > 24 && Math.abs(vel) < 0.08) this.playDir = this.playDir || 1
      }
    }
    const lead = this.playDir * 8
    // pan a little toward the ball's side of the pitch, but stay off the grass
    const panZ = Math.max(-6, Math.min(9, b.z * 0.28))
    // up in the stand; punch in low & tight for chances/goals, wide for build-up
    const standOff = HALF_D + 12 - heat * 3.6 // metres back from the touchline
    const yOff = (14.5 - heat * 1.8) * zoom
    outPos.set(b.x - this.playDir * 4, yOff, -(standOff) + panZ)
    outLook.set(b.x + lead, 0.75, b.z * 0.85)
    void d
  }

  /* ------------------------------------------------------------ frame loop */

  private loop = () => {
    if (this.disposed) return
    if (this.contextLost) return // paused while the context is lost; onContextRestored reschedules
    this.raf = requestAnimationFrame(this.loop)
    const now = performance.now()
    const dt = Math.min(0.05, (now - this.lastT) / 1000)
    this.lastT = now
    this.nowMs = now
    this.step(dt)
    // LED ticker
    if (this.ledTextures[0]) {
      this.ledTextures[0].offset.x = ((now / 1000) * 0.055) % 0.5
    }
    this.renderer.render(this.scene, this.camera)
  }

  private step(dt: number) {
    let targets: { home: Pose[]; away: Pose[] } = this.idleFrom
    let ball = this.ballPos
    let heat = 0
    let flash: 'home' | 'away' | null = null
    if (this.timeline) {
      const n = this.timeline.length
      const t = Math.max(0, Math.min(n - 1, this.simTime))
      const i = Math.floor(t)
      const j = Math.min(n - 1, i + 1)
      const f = t - i
      const a = this.timeline[i]
      const b = this.timeline[j]
      targets = {
        home: a.home.map((p, k) => lerp(p, b.home[k], f)),
        away: a.away.map((p, k) => lerp(p, b.away[k], f)),
      }
      ball = lerp(a.ball, b.ball, f)
      heat = Math.max(lerpNum(a.heat, b.heat, f), a.flash || b.flash ? 0.9 : 0)
      flash = a.flash ?? b.flash
    }
    this.heat += (heat - this.heat) * Math.min(1, dt * 3)
    this.animate('home', targets.home, dt)
    this.animate('away', targets.away, dt)

    // ball: ease to its pose; small flight bob on chances, roll in broadcast
    const k = Math.min(1, dt * (3 + this.heat * 6))
    const vx = ball.x - this.ballMesh.position.x
    const vz = ball.z - this.ballMesh.position.z
    this.ballMesh.position.x += vx * k
    this.ballMesh.position.z += vz * k
    const bob = this.heat > 0.45 ? Math.abs(Math.sin(this.nowMs / 100)) * this.heat : 0
    this.ballMesh.position.y = 0.5 + bob * 0.8
    if (this.camMode === 'broadcast') {
      this.ballMesh.rotation.x -= (vx * k * 3.4) / 0.5
      this.ballMesh.rotation.z += (vz * k * 3.4) / 0.5
    }
    this.ballPos = { x: this.ballMesh.position.x, z: this.ballMesh.position.z }

    const pos = new THREE.Vector3()
    const look = new THREE.Vector3()
    this.rigTargets(pos, look)
    // camera damping: position slow, look-at fast — the TV "locked on" feel
    const posK = Math.min(1, dt * 1.6)
    const lookK = Math.min(1, dt * 4)
    this.camFrom.lerp(pos, posK)
    this.camTo.lerp(look, lookK)
    this.camLook.copy(this.camTo)
    this.camera.position.copy(this.camFrom)
    this.camera.lookAt(this.camTo)
    void flash
  }

  private animate(side: 'home' | 'away', targets: Pose[], dt: number) {
    const rigs = this.actors[side]
    const prev = this.prevTargets[side]
    for (let i = 0; i < rigs.length; i++) {
      const rig = rigs[i]
      const t = targets[i]
      if (!rig || !t) continue
      if (this.drag && this.drag.side === side && this.drag.idx === i) continue
      const last = prev[i] ?? rig.root.position
      const k = Math.min(1, dt * 4.5)
      const nx = rig.root.position.x + (t.x - rig.root.position.x) * k
      const nz = rig.root.position.z + (t.z - rig.root.position.z) * k
      rig.root.position.set(nx, 0, nz)

      if (this.camMode === 'broadcast') {
        // speed from the *target* delta so the gait matches the choreography
        const tdx = t.x - last.x
        const tdz = t.z - last.z
        const tSpeed = dt > 0 ? Math.hypot(tdx, tdz) / dt : 0
        const speedN = Math.min(1, Math.max(0, (tSpeed - 0.1) / 7))
        if (tSpeed > 0.35) {
          const want = Math.atan2(tdx, tdz)
          let dh = want - rig.heading
          while (dh > Math.PI) dh -= Math.PI * 2
          while (dh < -Math.PI) dh += Math.PI * 2
          rig.heading += dh * Math.min(1, dt * 9)
        } else {
          // idle: face the goal you're attacking
          const want = side === 'home' ? Math.PI / 2 : -Math.PI / 2
          let dh = want - rig.heading
          while (dh > Math.PI) dh -= Math.PI * 2
          while (dh < -Math.PI) dh += Math.PI * 2
          rig.heading += dh * Math.min(1, dt * 2.2)
        }
        rig.root.rotation.y = rig.heading
        rig.phase += dt * (2.2 + speedN * 11)
        // gait: idle players barely sway; running legs drive through a real stride
        const swing = Math.sin(rig.phase) * (0.09 + speedN * 0.95)
        rig.legL.rotation.x = swing
        rig.legR.rotation.x = -swing
        // arms counter-swing the opposite leg, elbow bend baked in
        rig.armL.rotation.x = -swing * 0.7
        rig.armR.rotation.x = swing * 0.7
        rig.lean.rotation.x = -speedN * 0.14
        rig.lean.position.y = Math.abs(Math.sin(rig.phase)) * speedN * 0.05
        rig.root.position.y = 0
      }
      if (prev[i]) prev[i] = { x: t.x, z: t.z }
    }
  }
}

/* ------------------------------------------------------------ geometry helpers */

function arcSeg(
  cx: number,
  cz: number,
  r: number,
  a0: number,
  a1: number,
  emit: (ax: number, az: number, bx: number, bz: number) => void,
  steps = 40,
) {
  for (let i = 0; i < steps; i++) {
    const t0 = i / steps
    const t1 = (i + 1) / steps
    const x0 = cx + Math.cos(a0 + (a1 - a0) * t0) * r
    const z0 = cz + Math.sin(a0 + (a1 - a0) * t0) * r
    const x1 = cx + Math.cos(a0 + (a1 - a0) * t1) * r
    const z1 = cz + Math.sin(a0 + (a1 - a0) * t1) * r
    emit(x0, z0, x1, z1)
  }
}

function dotSeg(x: number, z: number, emit: (ax: number, az: number, bx: number, bz: number) => void) {
  const r = 0.09
  emit(x - r, z, x + r, z)
  emit(x, z - r, x, z + r)
}

function boxSeg(x0: number, z0: number, x1: number, z1: number, emit: (ax: number, az: number, bx: number, bz: number) => void) {
  emit(x0, z0, x1, z0)
  emit(x1, z0, x1, z1)
  emit(x1, z1, x0, z1)
}

function lerp(a: Pose, b: Pose, f: number): Pose {
  return { x: a.x + (b.x - a.x) * f, z: a.z + (b.z - a.z) * f }
}
function lerpNum(a: number, b: number, f: number): number {
  return a + (b - a) * f
}
