import { useState, useEffect, useRef, useCallback } from 'react'
import { DotLottieReact } from '@lottiefiles/dotlottie-react'
import { api } from '../api'
import Aurora from './Aurora'
import { Eye, EyeOff, Maximize2, Minimize2 } from 'lucide-react'

const AGENT_COLORS_HEX = {
  scout: '#00e5ff', analyst: '#5b5bff', verifier: '#00e676',
  profiler: '#ffab00', curator: '#ff2d78', synthesizer: '#b388ff',
  person_profiler: '#ffab00', org_profiler: '#ffab00',
}

// Each agent type gets a unique robot character from LottieFiles (free, same style family)
const AGENT_LOTTIE = {
  // Central mascot — white AI robot with cyan eyes
  default: 'https://assets-v2.lottiefiles.com/a/02fe4bd5-8c88-4351-a78f-353a57ea279a/uD5dnmVYlT.lottie',
  // Scout — green explorer robot
  scout: 'https://assets-v2.lottiefiles.com/a/98a5f1ec-1164-11ee-b120-e331a2c2ea3f/EtrPQsY6eg.lottie',
  // Analyst — robot with data visor
  analyst: 'https://assets-v2.lottiefiles.com/a/668de6b4-55ee-11ee-9f95-af971d099d03/FLYr1XBoWD.lottie',
  // Verifier — shield robot
  verifier: 'https://assets-v2.lottiefiles.com/a/c8e995aa-1d8b-11ef-ac81-e3b945030173/ZyleA2T5ES.lottie',
  // Profiler — search robot
  profiler: 'https://assets-v2.lottiefiles.com/a/e230036a-1179-11ee-b87c-83dd44b3f0ec/rIzjJiQPJO.lottie',
  // Curator — organizer robot
  curator: 'https://assets-v2.lottiefiles.com/a/aa6a52de-1186-11ee-8908-df4910d4b75e/IUTxv2oxIw.lottie',
  // Synthesizer — creative robot
  synthesizer: 'https://assets-v2.lottiefiles.com/a/ad03fc76-955a-11ef-a265-b32c5289eba6/UTOaxjef3d.lottie',
  // Sub-agents — smaller robot variants
  person_profiler: 'https://assets-v2.lottiefiles.com/a/9b5fc1ba-bb90-11ef-abd1-73704bf64ce5/tNkeW2lnOy.lottie',
  org_profiler: 'https://assets-v2.lottiefiles.com/a/8f577fd4-f1aa-11ef-b996-b3631e05cc15/bl3Uy6dgUY.lottie',
}

export default function PlaygroundView({ hubId }) {
  const canvasRef = useRef(null)
  const frameRef = useRef(null)
  const stateRef = useRef({
    agents: [], agentNodes: [], particles: [], connections: [],
    floatingActions: [], // live event toasts
    mouse: { x: -1, y: -1 }, hoveredAgent: null, time: 0, width: 0, height: 0,
    activityPulse: 0, // screen pulse on events
    shakeAmount: 0,    // screen shake on errors
  })
  const [agents, setAgents] = useState([])
  const [showLabels, setShowLabels] = useState(true)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [auroraIntensity, setAuroraIntensity] = useState(1.0)
  const [recentEvents, setRecentEvents] = useState([]) // for event feed overlay
  const [flashAgents, setFlashAgents] = useState({})   // agent_id -> timestamp for flash effect
  const containerRef = useRef(null)

  const loadAgents = useCallback(async () => {
    try {
      const data = await api.getHubAgents(hubId)
      const list = data.agents || []
      setAgents(list)
      stateRef.current.agents = list
      syncAgentNodes(list)
      const working = list.filter(a => a.status === 'working').length
      setAuroraIntensity(1.0 + working * 0.3)
    } catch {}
  }, [hubId])

  // WebSocket — the heart of event reactivity
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${proto}://${window.location.host}/api/engine/hubs/${hubId}/ws`
    let ws, retryTimeout
    function connect() {
      ws = new WebSocket(wsUrl)
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'init') {
            setAgents(msg.agents || [])
            stateRef.current.agents = msg.agents || []
            syncAgentNodes(msg.agents || [])
          } else if (msg.type === 'agent_action') {
            const action = msg.action
            const node = stateRef.current.agentNodes.find(n => n.id === action?.agent_id)

            if (node) {
              // 1. Particle burst from the agent
              const isFailed = action.status === 'failed'
              emitBurst(node.x, node.y, isFailed ? '#ff3d3d' : node.color, isFailed ? 15 : 8)

              // 2. Floating action label that rises from the agent
              stateRef.current.floatingActions.push({
                x: node.x, y: node.y - node.radius - 10,
                text: `${action.action_type}: ${(action.description || '').slice(0, 35)}`,
                color: node.color,
                life: 1,
                agentName: node.name,
              })

              // 3. Screen pulse
              stateRef.current.activityPulse = 1.0

              // 4. Screen shake on error
              if (isFailed) stateRef.current.shakeAmount = 8

              // 5. Flash the agent card
              setFlashAgents(prev => ({ ...prev, [action.agent_id]: Date.now() }))
            }

            // 6. Add to recent events feed
            setRecentEvents(prev => [
              { id: Date.now(), ...action, agentName: node?.name || action.agent_id?.slice(0, 8) },
              ...prev.slice(0, 5)
            ])

            loadAgents()
          }
        } catch {}
      }
      ws.onclose = () => { retryTimeout = setTimeout(connect, 3000) }
    }
    connect()
    return () => { clearTimeout(retryTimeout); if (ws) ws.close() }
  }, [hubId, loadAgents])

  useEffect(() => {
    loadAgents()
    const iv = setInterval(loadAgents, 8000)
    return () => clearInterval(iv)
  }, [loadAgents])

  function syncAgentNodes(agentList) {
    const s = stateRef.current
    const existing = s.agentNodes
    const mains = agentList.filter(a => !a.parent_agent_id)
    const newNodes = agentList.map((a, i) => {
      const prev = existing.find(n => n.id === a.id)
      const color = AGENT_COLORS_HEX[a.agent_type] || '#888'
      const mainIdx = mains.findIndex(m => m.id === a.id)
      const isSub = !!a.parent_agent_id
      const angle = isSub
        ? (i / Math.max(agentList.length, 1)) * Math.PI * 2
        : (mainIdx / Math.max(mains.length, 1)) * Math.PI * 2
      const dist = isSub ? s.width * 0.35 : s.width * 0.22
      return {
        id: a.id, name: a.name, type: a.agent_type, status: a.status,
        events: a.events_handled || 0, errors: a.errors || 0, color,
        x: prev?.x ?? s.width / 2 + Math.cos(angle) * dist,
        y: prev?.y ?? s.height / 2 + Math.sin(angle) * (s.height * (isSub ? 0.3 : 0.22)),
        vx: prev?.vx ?? (Math.random() - 0.5) * 0.2,
        vy: prev?.vy ?? (Math.random() - 0.5) * 0.2,
        radius: isSub ? 12 : 26,
        pulsePhase: prev?.pulsePhase ?? Math.random() * Math.PI * 2,
        isSub, parentId: a.parent_agent_id,
        flashIntensity: prev?.flashIntensity ?? 0, // for event flash
      }
    })
    s.agentNodes = newNodes
    s.connections = []
    for (const n of newNodes) {
      if (n.parentId) {
        const parent = newNodes.find(p => p.id === n.parentId)
        if (parent) s.connections.push({ from: parent, to: n, color: n.color })
      }
    }
    const mainNodes = newNodes.filter(n => !n.isSub)
    for (let i = 0; i < mainNodes.length; i++) {
      const next = mainNodes[(i + 1) % mainNodes.length]
      if (mainNodes.length > 1) s.connections.push({ from: mainNodes[i], to: next, color: 'rgba(0,229,255,0.08)' })
    }
  }

  function emitBurst(x, y, color, count) {
    const s = stateRef.current
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2
      const speed = 0.5 + Math.random() * 2.5
      s.particles.push({
        x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 1, decay: 0.005 + Math.random() * 0.01, color, size: 1.5 + Math.random() * 3,
      })
    }
  }

  // Canvas animation loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const s = stateRef.current

    function resize() {
      const rect = canvas.parentElement.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      canvas.style.width = rect.width + 'px'
      canvas.style.height = rect.height + 'px'
      ctx.scale(dpr, dpr)
      s.width = rect.width
      s.height = rect.height
    }
    resize()
    window.addEventListener('resize', resize)

    function onMouseMove(e) {
      const rect = canvas.getBoundingClientRect()
      s.mouse.x = e.clientX - rect.left
      s.mouse.y = e.clientY - rect.top
    }
    function onClick() {
      if (s.hoveredAgent) setSelectedAgent(prev => prev?.id === s.hoveredAgent.id ? null : s.hoveredAgent)
      else setSelectedAgent(null)
    }
    canvas.addEventListener('mousemove', onMouseMove)
    canvas.addEventListener('click', onClick)

    function draw() {
      const W = s.width, H = s.height
      const dpr = window.devicePixelRatio || 1
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Screen shake
      if (s.shakeAmount > 0.1) {
        const sx = (Math.random() - 0.5) * s.shakeAmount
        const sy = (Math.random() - 0.5) * s.shakeAmount
        ctx.translate(sx, sy)
        s.shakeAmount *= 0.9
      }

      ctx.clearRect(-10, -10, W + 20, H + 20)
      s.time += 0.008

      // Activity pulse decay
      if (s.activityPulse > 0) s.activityPulse *= 0.97

      // Ambient particles — rising gently
      if (s.particles.length < 100 && Math.random() < 0.12) {
        s.particles.push({
          x: Math.random() * W, y: H + 5,
          vx: (Math.random() - 0.5) * 0.3, vy: -0.3 - Math.random() * 0.5,
          life: 1, decay: 0.002 + Math.random() * 0.004,
          color: ['#00e5ff', '#5b5bff', '#ff2d78', '#00e676'][Math.floor(Math.random() * 4)],
          size: 0.8 + Math.random() * 1.5,
        })
      }

      // Update & draw particles
      for (let i = s.particles.length - 1; i >= 0; i--) {
        const p = s.particles[i]
        p.x += p.vx; p.y += p.vy; p.life -= p.decay
        if (p.life <= 0) { s.particles.splice(i, 1); continue }
        ctx.globalAlpha = p.life * 0.6
        ctx.fillStyle = p.color
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1

      // Connections — animated energy lines
      for (const c of s.connections) {
        const dx = c.to.x - c.from.x, dy = c.to.y - c.from.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        const alpha = Math.max(0.04, 0.2 - dist / 1500)
        ctx.strokeStyle = c.color; ctx.lineWidth = 1; ctx.globalAlpha = alpha
        ctx.setLineDash([4, 8]); ctx.lineDashOffset = -s.time * 40
        ctx.beginPath(); ctx.moveTo(c.from.x, c.from.y)
        const mx = (c.from.x + c.to.x) / 2, my = (c.from.y + c.to.y) / 2 - 40 * Math.sin(s.time)
        ctx.quadraticCurveTo(mx, my, c.to.x, c.to.y); ctx.stroke()
        ctx.setLineDash([]); ctx.lineDashOffset = 0

        // Traveling energy dot
        const progress = (s.time * 0.3 + dist * 0.001) % 1
        const ex = (1-progress)*(1-progress)*c.from.x + 2*(1-progress)*progress*mx + progress*progress*c.to.x
        const ey = (1-progress)*(1-progress)*c.from.y + 2*(1-progress)*progress*my + progress*progress*c.to.y
        ctx.globalAlpha = alpha * 2.5
        ctx.fillStyle = c.color
        ctx.beginPath(); ctx.arc(ex, ey, 2.5, 0, Math.PI * 2); ctx.fill()
      }
      ctx.globalAlpha = 1

      // Agent nodes
      s.hoveredAgent = null
      for (const node of s.agentNodes) {
        const wave = Math.sin(s.time * 1.5 + node.pulsePhase) * 0.12
        node.vy += wave * 0.008
        node.x += node.vx; node.y += node.vy
        node.vx *= 0.997; node.vy *= 0.997
        const margin = 80
        if (node.x < margin) node.vx += 0.04
        if (node.x > W - margin) node.vx -= 0.04
        if (node.y < margin) node.vy += 0.04
        if (node.y > H - margin) node.vy -= 0.04
        node.vx += (W / 2 - node.x) * 0.00003
        node.vy += (H / 2 - node.y) * 0.00003
        for (const other of s.agentNodes) {
          if (other === node) continue
          const ddx = node.x - other.x, ddy = node.y - other.y
          const dd = Math.sqrt(ddx * ddx + ddy * ddy)
          if (dd < 100) {
            const force = (100 - dd) * 0.0004
            node.vx += (ddx / dd) * force; node.vy += (ddy / dd) * force
          }
        }
        const mdx = s.mouse.x - node.x, mdy = s.mouse.y - node.y
        const mDist = Math.sqrt(mdx * mdx + mdy * mdy)
        const isHovered = mDist < node.radius + 12
        if (isHovered) { s.hoveredAgent = node; canvas.style.cursor = 'pointer' }

        // Flash intensity decay
        if (node.flashIntensity > 0) node.flashIntensity *= 0.95

        drawAgent(ctx, node, s.time, isHovered, showLabels)

        if (node.status === 'working' && Math.random() < 0.06) emitBurst(node.x, node.y, node.color, 1)
      }
      if (!s.hoveredAgent) canvas.style.cursor = 'default'

      // === FLOATING ACTION LABELS (event toasts) ===
      for (let i = s.floatingActions.length - 1; i >= 0; i--) {
        const fa = s.floatingActions[i]
        fa.y -= 0.6 // rise up
        fa.life -= 0.008
        if (fa.life <= 0) { s.floatingActions.splice(i, 1); continue }

        ctx.globalAlpha = Math.min(fa.life, 0.8)
        // Background pill
        ctx.font = '9px "JetBrains Mono", monospace'
        const tw = ctx.measureText(fa.text).width + 16
        ctx.fillStyle = 'rgba(6,6,10,0.85)'
        roundRect(ctx, fa.x - tw / 2, fa.y - 8, tw, 18, 9)
        ctx.fill()
        ctx.strokeStyle = fa.color + '40'; ctx.lineWidth = 1
        roundRect(ctx, fa.x - tw / 2, fa.y - 8, tw, 18, 9)
        ctx.stroke()
        // Agent name + action text
        ctx.fillStyle = fa.color
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
        ctx.fillText(fa.text, fa.x, fa.y + 1)
      }
      ctx.globalAlpha = 1

      // === ACTIVITY PULSE — full screen flash on events ===
      if (s.activityPulse > 0.01) {
        ctx.fillStyle = `rgba(0,229,255,${s.activityPulse * 0.04})`
        ctx.fillRect(0, 0, W, H)
      }

      frameRef.current = requestAnimationFrame(draw)
    }

    frameRef.current = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frameRef.current)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('mousemove', onMouseMove)
      canvas.removeEventListener('click', onClick)
    }
  }, [showLabels])

  // When flashAgents changes, set the flash intensity on the corresponding node
  useEffect(() => {
    for (const [agentId, ts] of Object.entries(flashAgents)) {
      const node = stateRef.current.agentNodes.find(n => n.id === agentId)
      if (node) node.flashIntensity = 1.0
    }
  }, [flashAgents])

  const toggleFullscreen = () => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {})
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {})
    }
  }

  const workingCount = agents.filter(a => a.status === 'working').length
  const mainAgents = agents.filter(a => !a.parent_agent_id)

  return (
    <div className="pv-container" ref={containerRef}>
      {/* Layer 1: Aurora WebGL */}
      <Aurora colorStops={['#00e5ff', '#5b5bff', '#ff2d78']} amplitude={auroraIntensity} blend={0.6} speed={0.8} />

      {/* Layer 2: Canvas — agents, particles, connections, floating actions */}
      <div className="pv-canvas-wrap">
        <canvas ref={canvasRef} />
      </div>

      {/* Layer 3: Central Lottie character */}
      <div className="pv-lottie-center">
        <DotLottieReact src={AGENT_LOTTIE.default} loop autoplay
          style={{ width: 180, height: 180, opacity: 0.85 }} />
        <div className="pv-lottie-label">
          {workingCount > 0 ? `${workingCount} agent${workingCount > 1 ? 's' : ''} active` : agents.length > 0 ? 'Agents idle' : 'No agents running'}
        </div>
      </div>

      {/* Toolbar */}
      <div className="pv-toolbar">
        <div className="pv-toolbar-left">
          <span className="pv-title">Agent Playground</span>
          <span className="pv-subtitle">
            {agents.length > 0
              ? <>{agents.length} agent{agents.length !== 1 ? 's' : ''}{workingCount > 0 && <span className="pv-working"> &middot; {workingCount} working</span>}</>
              : 'Waiting for agents'}
          </span>
        </div>
        <div className="pv-toolbar-right">
          <button className="pv-tool-btn" onClick={() => setShowLabels(!showLabels)}
            title={showLabels ? 'Hide labels' : 'Show labels'}>
            {showLabels ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>
          <button className="pv-tool-btn" onClick={toggleFullscreen}
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Live event feed — floating action labels */}
      <div className="pv-event-feed">
        {recentEvents.map(evt => {
          const color = AGENT_COLORS_HEX[evt.agent_type] || '#888'
          const isFailed = evt.status === 'failed'
          return (
            <div key={evt.id} className={`pv-event-item ${isFailed ? 'error' : ''}`}>
              <span className="pv-event-dot" style={{ background: isFailed ? '#ff3d3d' : color }} />
              <span className="pv-event-agent" style={{ color }}>{evt.agentName}</span>
              <span className="pv-event-type">{evt.action_type}</span>
              <span className="pv-event-desc">{(evt.description || '').slice(0, 40)}</span>
            </div>
          )
        })}
      </div>

      {/* Agent character strip */}
      {mainAgents.length > 0 && <div className="pv-agent-strip">
        {mainAgents.map(a => {
          const color = AGENT_COLORS_HEX[a.agent_type] || '#888'
          const isWorking = a.status === 'working'
          const isFlashing = flashAgents[a.id] && Date.now() - flashAgents[a.id] < 2000
          const lottieUrl = AGENT_LOTTIE[a.agent_type] || AGENT_LOTTIE.default
          return (
            <div key={a.id}
              className={`pv-agent-card ${selectedAgent?.id === a.id ? 'selected' : ''} ${isWorking ? 'working' : ''} ${isFlashing ? 'flash' : ''}`}
              onClick={() => setSelectedAgent(prev => prev?.id === a.id ? null : a)}
            >
              <div className="pv-agent-lottie" style={isFlashing ? { boxShadow: `0 0 20px ${color}40` } : {}}>
                <DotLottieReact src={lottieUrl} loop autoplay
                  speed={isWorking ? 1.5 : 0.5}
                  style={{ width: 48, height: 48 }} />
              </div>
              <div className="pv-agent-card-info">
                <div className="pv-agent-card-name" style={{ color }}>{a.name}</div>
                <div className={`pv-agent-card-status ${isWorking ? 'active' : ''}`}>
                  <span className="pv-status-dot" style={{ background: isWorking ? color : 'var(--text-3)' }} />
                  {a.status}
                </div>
              </div>
              {a.events_handled > 0 && (
                <div className="pv-agent-card-badge" style={{ background: color }}>{a.events_handled}</div>
              )}
            </div>
          )
        })}
      </div>}

      {/* Legend */}
      {mainAgents.length > 0 && <div className="pv-legend">
        {mainAgents.map(a => {
          const color = AGENT_COLORS_HEX[a.agent_type] || '#888'
          return (
            <div key={a.id} className="pv-legend-item">
              <span className="pv-legend-dot" style={{ background: color }} />
              <span className="pv-legend-name">{a.name}</span>
              <span className={`pv-legend-status status-${a.status}`}>{a.status}</span>
            </div>
          )
        })}
      </div>}
    </div>
  )
}

// === DRAWING ===

function drawAgent(ctx, node, t, isHovered, showLabels) {
  const { x, y, radius, color, name, status, events, errors, isSub, pulsePhase, flashIntensity } = node
  const pulse = Math.sin(t * 3 + pulsePhase) * 0.5 + 0.5
  const isWorking = status === 'working'
  const isPaused = status === 'paused'
  const flash = flashIntensity || 0

  // Event flash — big expanding ring
  if (flash > 0.05) {
    const ringR = radius + 30 * (1 - flash)
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.globalAlpha = flash * 0.6
    ctx.beginPath(); ctx.arc(x, y, ringR, 0, Math.PI * 2); ctx.stroke()
    ctx.globalAlpha = 1
  }

  // Outer glow — boosted during flash
  const glowR = radius + (isWorking ? 18 + pulse * 12 : 8) + flash * 20
  const glow = ctx.createRadialGradient(x, y, radius * 0.3, x, y, glowR)
  glow.addColorStop(0, color + (isWorking || flash > 0.1 ? '40' : '18'))
  glow.addColorStop(0.6, color + '08')
  glow.addColorStop(1, color + '00')
  ctx.fillStyle = glow
  ctx.beginPath(); ctx.arc(x, y, glowR, 0, Math.PI * 2); ctx.fill()

  // Working: spinning arcs
  if (isWorking) {
    ctx.strokeStyle = color + '50'; ctx.lineWidth = 2
    ctx.globalAlpha = 0.4 + pulse * 0.4
    ctx.beginPath(); ctx.arc(x, y, radius + 8 + pulse * 6, t * 2.5, t * 2.5 + Math.PI * 1.2); ctx.stroke()
    ctx.strokeStyle = color + '25'
    ctx.beginPath(); ctx.arc(x, y, radius + 12 + pulse * 4, -t * 1.8, -t * 1.8 + Math.PI * 0.8); ctx.stroke()
    ctx.globalAlpha = 1
  }

  // Main orb — brighter during flash
  const grad = ctx.createRadialGradient(x - radius * 0.25, y - radius * 0.25, 0, x, y, radius)
  const flashBoost = Math.min(flash * 0.3, 0.3)
  grad.addColorStop(0, color + hex(0x50 + flashBoost * 255))
  grad.addColorStop(0.5, color + hex(0x25 + flashBoost * 128))
  grad.addColorStop(1, color + hex(0x0a + flashBoost * 64))
  ctx.fillStyle = grad
  ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill()

  // Border
  ctx.strokeStyle = isHovered ? color + 'dd' : flash > 0.1 ? color + 'bb' : color + '70'
  ctx.lineWidth = isHovered ? 2.5 : flash > 0.1 ? 2 : 1.5
  ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.stroke()

  // Initials
  ctx.fillStyle = color
  ctx.globalAlpha = isPaused ? 0.3 : 0.9
  ctx.font = `bold ${isSub ? 8 : 13}px "Space Grotesk", sans-serif`
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  const initials = name.replace(/[^A-Z]/g, '').slice(0, 2) || name.slice(0, 2).toUpperCase()
  ctx.fillText(initials, x, y)
  ctx.globalAlpha = 1

  // Labels
  if (showLabels && !isSub) {
    ctx.font = '11px "Space Grotesk", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillStyle = isHovered ? '#fff' : 'rgba(255,255,255,0.55)'
    ctx.fillText(name, x, y + radius + 16)
    ctx.font = '8px "JetBrains Mono", monospace'
    ctx.fillStyle = isWorking ? color : 'rgba(255,255,255,0.25)'
    ctx.fillText(status.toUpperCase(), x, y + radius + 28)
  }

  // Event badge
  if (events > 0 && !isSub) {
    const bx = x + radius * 0.7, by = y - radius * 0.7
    ctx.fillStyle = 'rgba(6,6,10,0.85)'
    ctx.beginPath(); ctx.arc(bx, by, 9, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = color
    ctx.font = 'bold 7px "JetBrains Mono", monospace'
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(events > 99 ? '99+' : events, bx, by)
  }

  // Error dot
  if (errors > 0) {
    ctx.fillStyle = '#ff3d3d'
    ctx.beginPath(); ctx.arc(x - radius * 0.7, y - radius * 0.7, 4, 0, Math.PI * 2); ctx.fill()
  }

  // Hover tooltip
  if (isHovered) {
    const ty = y - radius - 24
    const text = `${name} — ${status} (${events} events)`
    ctx.font = '11px "Space Grotesk", sans-serif'
    const tw = ctx.measureText(text).width + 20; const th = 26
    ctx.fillStyle = 'rgba(6,6,10,0.92)'
    roundRect(ctx, x - tw / 2, ty - th / 2, tw, th, 8); ctx.fill()
    ctx.strokeStyle = color + '40'; ctx.lineWidth = 1
    roundRect(ctx, x - tw / 2, ty - th / 2, tw, th, 8); ctx.stroke()
    ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(text, x, ty)
  }
}

function hex(n) {
  return Math.min(255, Math.max(0, Math.round(n))).toString(16).padStart(2, '0')
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r); ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath()
}
