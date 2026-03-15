import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { ZoomIn, ZoomOut, Maximize, RotateCcw } from 'lucide-react'

const TYPE_COLORS = {
  Person: '#00e5ff', Organization: '#ff2d78', Concept: '#5b5bff', Method: '#00e676',
  Tool: '#ffab00', Event: '#ff3d3d', Dataset: '#84cc16', Location: '#ec4899',
}

// Lucide SVG paths for entity type icons (from lucide.dev)
const TYPE_ICON_PATHS = {
  Person: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z', // User
  Organization: 'M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2 M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2', // Building2
  Tool: 'M4 4h16v16H4z M9 9h6v6H9z M9 1v3 M15 1v3 M9 20v3 M15 20v3 M20 9h3 M20 14h3 M1 9h3 M1 14h3', // Cpu
  Method: 'M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2 M8.5 2h7', // FlaskConical
  Concept: 'M2 12h4 M18 12h4 M12 2v4 M12 18v4 M4.93 4.93l2.83 2.83 M16.24 16.24l2.83 2.83 M4.93 19.07l2.83-2.83 M16.24 7.76l2.83-2.83 M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // Sparkle-ish
  Dataset: 'M12 8a5 3 0 1 0 0-6 5 3 0 0 0 0 6z M17 5v6a5 3 0 0 1-10 0V5 M17 11v6a5 3 0 0 1-10 0v-6', // Database
  Location: 'M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z M12 10m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0', // MapPin
  Event: 'M8 2v4 M16 2v4 M3 10h18 M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z', // Calendar
}

// Pre-render SVG icons as cached Image objects per type+color combo
const iconCache = {}
function getIconImage(entityType, color) {
  const key = entityType + color
  if (iconCache[key]) return iconCache[key]
  const path = TYPE_ICON_PATHS[entityType]
  if (!path) return null
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${path.split(' M').map((d, i) => `<path d="${i === 0 ? d : 'M' + d}"/>`).join('')}</svg>`
  const img = new Image()
  img.src = 'data:image/svg+xml,' + encodeURIComponent(svg)
  iconCache[key] = img
  return img
}

// Vibrant palette for untyped entities — hashed by name
const ENTITY_PALETTE = ['#00e5ff', '#ff2d78', '#5b5bff', '#00e676', '#ffab00', '#ff3d3d', '#84cc16', '#ec4899']

function getEntityType(labels) {
  return (labels || []).find(l => TYPE_COLORS[l] && l !== 'Entity') || 'Entity'
}
function hashStr(s) {
  let h = 0; for (let i = 0; i < (s || '').length; i++) h = s.charCodeAt(i) + ((h << 5) - h)
  return Math.abs(h)
}
function getColor(labels, name) {
  const type = getEntityType(labels)
  if (TYPE_COLORS[type]) return TYPE_COLORS[type]
  return ENTITY_PALETTE[hashStr(name) % ENTITY_PALETTE.length]
}

export default function GraphView({ nodes, edges, onSelectEntity, selectedEntityUuid, searchHighlight }) {
  const fgRef = useRef()
  const containerRef = useRef()
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [tooltip, setTooltip] = useState(null)

  // Refs for paint callbacks (stable — no re-creation)
  const selectedRef = useRef(null)
  const hoveredRef = useRef(null)
  const adjRef = useRef(null)
  const hlRef = useRef(null)

  useEffect(() => {
    selectedRef.current = selectedEntityUuid
    if (selectedEntityUuid) {
      const set = new Set([selectedEntityUuid])
      for (const e of edges) {
        if (e.source_node_uuid === selectedEntityUuid) set.add(e.target_node_uuid)
        if (e.target_node_uuid === selectedEntityUuid) set.add(e.source_node_uuid)
      }
      adjRef.current = set
    } else {
      adjRef.current = null
    }
  }, [selectedEntityUuid, edges])

  useEffect(() => {
    hlRef.current = searchHighlight ? new Set(searchHighlight) : null
  }, [searchHighlight])

  // Container sizing
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width: Math.floor(width), height: Math.floor(height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Edge counts
  const edgeCounts = useMemo(() => {
    const c = {}
    for (const e of edges) {
      c[e.source_node_uuid] = (c[e.source_node_uuid] || 0) + 1
      c[e.target_node_uuid] = (c[e.target_node_uuid] || 0) + 1
    }
    return c
  }, [edges])

  // Graph data — stable
  const graphData = useMemo(() => {
    const ns = new Set(nodes.map(n => n.uuid))
    return {
      nodes: nodes.map(n => ({
        id: n.uuid, name: n.name, labels: n.labels,
        summary: n.summary, confidence: n.confidence,
        entityType: getEntityType(n.labels),
        _ec: edgeCounts[n.uuid] || 0,
      })),
      links: edges
        .filter(e => ns.has(e.source_node_uuid) && ns.has(e.target_node_uuid))
        .map(e => ({ source: e.source_node_uuid, target: e.target_node_uuid, name: e.name, fact: e.fact }))
    }
  }, [nodes, edges, edgeCounts])

  // Forces
  useEffect(() => {
    if (!fgRef.current) return
    const n = graphData.nodes.length
    const charge = n < 30 ? -60 : n < 80 ? -40 : -30
    fgRef.current.d3Force('charge')?.strength(charge).distanceMax(200)
    fgRef.current.d3Force('link')?.distance(35).strength(0.7)
    fgRef.current.d3Force('center')?.strength(0.12)
  }, [graphData])

  // Auto-fit
  const prevCount = useRef(0)
  useEffect(() => {
    if (nodes.length > 0 && Math.abs(nodes.length - prevCount.current) > 2) {
      prevCount.current = nodes.length
      setTimeout(() => fgRef.current?.zoomToFit(300, 50), 300)
      setTimeout(() => fgRef.current?.zoomToFit(500, 50), 1500)
      setTimeout(() => fgRef.current?.zoomToFit(500, 50), 3000)
    }
  }, [nodes.length])

  // ─── NODE PAINTER ───
  const paintNode = useCallback((node, ctx, globalScale) => {
    if (!isFinite(node.x) || !isFinite(node.y)) return
    const color = getColor(node.labels, node.name)
    const ec = node._ec || 0
    const r = 4 + Math.min(6, ec * 0.8)
    const sel = selectedRef.current
    const hov = hoveredRef.current
    const adj = adjRef.current
    const hl = hlRef.current

    const isSelected = sel === node.id
    const isHovered = hov === node.id
    const isAdj = adj?.has(node.id)
    const isHighlighted = hl?.has(node.id)
    const hasSelection = !!adj
    const hasHighlight = !!hl
    const isFocused = isSelected || isHovered
    // Dim logic: dim when selection active + not adjacent, OR search active + not highlighted
    const dimAlpha = (hasSelection && !isAdj) ? 0.12
      : (hasHighlight && !isHighlighted && !isFocused) ? 0.15
      : 1

    ctx.globalAlpha = dimAlpha

    // ── Neon glow halo (all nodes) ──
    const glowR = r + (isFocused ? 16 : 6)
    const glow = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, glowR)
    glow.addColorStop(0, color + (isFocused ? '55' : '20'))
    glow.addColorStop(1, color + '00')
    ctx.beginPath()
    ctx.arc(node.x, node.y, glowR, 0, Math.PI * 2)
    ctx.fillStyle = glow
    ctx.fill()

    // ── Outer ring (all nodes — gives structure) ──
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 1.5, 0, Math.PI * 2)
    ctx.strokeStyle = color + (isFocused ? '80' : '35')
    ctx.lineWidth = (isFocused ? 1.2 : 0.6) / globalScale
    ctx.stroke()

    // ── Inner filled circle ──
    ctx.beginPath()
    ctx.arc(node.x, node.y, r * 0.65, 0, Math.PI * 2)
    ctx.fillStyle = color + (isFocused ? 'ee' : 'cc')
    ctx.fill()

    // ── Entity type icon (Lucide SVG drawn inside node) ──
    const iconImg = getIconImage(node.entityType, isFocused ? '#ffffff' : color)
    if (iconImg && iconImg.complete && r > 4 && globalScale > 0.5) {
      const iconSize = Math.min(r * 1.2, 12)
      ctx.globalAlpha = dimAlpha * (isFocused ? 0.95 : 0.7)
      try {
        ctx.drawImage(iconImg, node.x - iconSize / 2, node.y - iconSize / 2, iconSize, iconSize)
      } catch {}
      ctx.globalAlpha = dimAlpha
    } else if (r > 4 && globalScale > 0.4) {
      // Fallback cross pattern for generic entities
      const cr = r * 0.45
      ctx.strokeStyle = color + (isFocused ? 'aa' : '55')
      ctx.lineWidth = 0.8 / globalScale
      ctx.beginPath()
      ctx.moveTo(node.x - cr, node.y); ctx.lineTo(node.x + cr, node.y)
      ctx.moveTo(node.x, node.y - cr); ctx.lineTo(node.x, node.y + cr)
      ctx.stroke()
    }

    // ── Search highlight ring ──
    if (isHighlighted && !isFocused) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, r + 5, 0, Math.PI * 2)
      ctx.strokeStyle = '#ffffff50'
      ctx.lineWidth = 1.2 / globalScale
      ctx.setLineDash([3 / globalScale, 3 / globalScale])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // ── Focus: extra bright center + pulse ring ──
    if (isFocused) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, r * 0.25, 0, Math.PI * 2)
      ctx.fillStyle = '#ffffff'
      ctx.fill()
    }

    // ── Labels ──
    const showLabel =
      isFocused || isHighlighted ||
      (hasSelection && isAdj) ||
      (!hasSelection && !hasHighlight && ec >= 5) ||
      (!hasSelection && !hasHighlight && globalScale > 1.8 && ec >= 2) ||
      globalScale > 3.5

    if (showLabel) {
      const fs = isFocused
        ? Math.min(13, Math.max(10, 12 / globalScale))
        : Math.min(10, Math.max(7, 9 / globalScale))
      const maxLen = globalScale > 2 ? 28 : globalScale > 1 ? 18 : 14
      const name = node.name.length > maxLen ? node.name.slice(0, maxLen - 1) + '..' : node.name

      ctx.font = `${isFocused ? '600' : '400'} ${fs}px 'Space Grotesk', sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = isFocused ? '#ffffffee' : isHighlighted ? '#ddddee' : isAdj ? '#bbbbcc' : '#777790'
      ctx.fillText(name, node.x, node.y + r + 4 / globalScale)

      if (isFocused && node.entityType !== 'Entity') {
        ctx.font = `700 ${Math.max(6, 7 / globalScale)}px 'JetBrains Mono', monospace`
        ctx.fillStyle = color + '88'
        ctx.fillText(node.entityType, node.x, node.y + r + fs + 6 / globalScale)
      }
    }
    ctx.globalAlpha = 1
  }, [])

  // ─── LINK PAINTER — bright neon edges with glow ───
  const paintLink = useCallback((link, ctx) => {
    if (!isFinite(link.source.x) || !isFinite(link.target.x)) return
    const adj = adjRef.current
    const sid = link.source.id, tid = link.target.id
    const hasSelection = !!adj
    const isAdj = adj && adj.has(sid) && adj.has(tid)
    const isDimmed = hasSelection && !isAdj

    const sx = link.source.x, sy = link.source.y
    const tx = link.target.x, ty = link.target.y
    const sc = getColor(link.source.labels, link.source.name)
    const tc = getColor(link.target.labels, link.target.name)

    if (isDimmed) {
      ctx.beginPath()
      ctx.moveTo(sx, sy); ctx.lineTo(tx, ty)
      ctx.strokeStyle = 'rgba(255,255,255,0.02)'
      ctx.lineWidth = 0.3
      ctx.stroke()
      return
    }

    const g = ctx.createLinearGradient(sx, sy, tx, ty)

    // ── Glow layer (thick, low opacity — creates neon bloom) ──
    g.addColorStop(0, sc + (isAdj ? '40' : '18'))
    g.addColorStop(1, tc + (isAdj ? '40' : '18'))
    ctx.beginPath()
    ctx.moveTo(sx, sy); ctx.lineTo(tx, ty)
    ctx.strokeStyle = g
    ctx.lineWidth = isAdj ? 6 : 3
    ctx.stroke()

    // ── Core line (thin, bright — the actual edge) ──
    const g2 = ctx.createLinearGradient(sx, sy, tx, ty)
    g2.addColorStop(0, sc + (isAdj ? 'cc' : '70'))
    g2.addColorStop(1, tc + (isAdj ? 'cc' : '70'))
    ctx.beginPath()
    ctx.moveTo(sx, sy); ctx.lineTo(tx, ty)
    ctx.strokeStyle = g2
    ctx.lineWidth = isAdj ? 1.5 : 0.8
    ctx.stroke()
  }, [])

  // ─── HOVER ───
  const handleHover = useCallback((node, prevNode) => {
    hoveredRef.current = node?.id || null
    if (containerRef.current) containerRef.current.style.cursor = node ? 'pointer' : 'default'
    if (node) {
      const el = containerRef.current
      if (!el) return
      // Get screen coordinates of the node
      const coords = fgRef.current?.graph2ScreenCoords(node.x, node.y)
      if (!coords) return
      setTooltip({
        x: coords.x, y: coords.y,
        name: node.name,
        type: node.entityType,
        color: getColor(node.labels, node.name),
        summary: node.summary,
        ec: node._ec || 0,
        confidence: node.confidence,
      })
    } else {
      setTooltip(null)
    }
  }, [])

  const handleClick = useCallback((node) => {
    onSelectEntity?.(node.id)
    setTooltip(null)
  }, [onSelectEntity])

  // Legend
  const legendTypes = useMemo(() => {
    const m = new Map()
    for (const n of nodes) { const t = getEntityType(n.labels); m.set(t, (m.get(t) || 0) + 1) }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]).slice(0, 8)
  }, [nodes])

  if (nodes.length === 0) {
    return (
      <div className="graph-full-container" ref={containerRef}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)', fontSize: 14 }}>
          Knowledge graph is building...
        </div>
      </div>
    )
  }

  return (
    <div className="graph-full-container" ref={containerRef}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="#08080e"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          if (!isFinite(node.x) || !isFinite(node.y)) return
          ctx.beginPath()
          ctx.arc(node.x, node.y, 12 + Math.min(7, (node._ec || 0) * 0.9), 0, Math.PI * 2)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkCanvasObject={paintLink}
        onNodeClick={handleClick}
        onNodeHover={handleHover}
        onBackgroundClick={() => { onSelectEntity?.(null); setTooltip(null) }}
        d3AlphaDecay={0.03}
        d3VelocityDecay={0.4}
        cooldownTime={3000}
        warmupTicks={100}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
        minZoom={0.3}
        maxZoom={6}
      />

      {/* Hover popover */}
      {tooltip && !selectedEntityUuid && (
        <div className="graph-popover" style={{
          left: Math.min(tooltip.x + 16, dimensions.width - 280),
          top: Math.max(tooltip.y - 20, 8),
        }}>
          <div className="graph-popover-header">
            <span className="graph-popover-type" style={{ color: tooltip.color }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: tooltip.color, display: 'inline-block' }} />
              {tooltip.type}
            </span>
            <span className="graph-popover-ec">{tooltip.ec} links</span>
          </div>
          <div className="graph-popover-name">{tooltip.name}</div>
          {tooltip.summary && (
            <div className="graph-popover-summary">
              {tooltip.summary.length > 120 ? tooltip.summary.slice(0, 118) + '...' : tooltip.summary}
            </div>
          )}
          {tooltip.confidence != null && (
            <div className="graph-popover-conf">
              <div className="graph-popover-conf-bar">
                <div style={{
                  width: `${Math.round(tooltip.confidence * 100)}%`, height: '100%', borderRadius: 2,
                  background: tooltip.confidence >= 0.7 ? 'var(--green)' : tooltip.confidence >= 0.4 ? 'var(--amber)' : 'var(--red)',
                }} />
              </div>
              <span>{Math.round(tooltip.confidence * 100)}%</span>
            </div>
          )}
          <div className="graph-popover-hint">Click to view details</div>
        </div>
      )}

      {/* Legend */}
      <div className="graph-legend">
        {legendTypes.map(([type, count]) => (
          <div key={type} className="graph-legend-item">
            <span className="graph-legend-dot" style={{ background: TYPE_COLORS[type] || '#00e5ff' }} />
            <span className="graph-legend-label">{type === 'Entity' ? 'General' : type}</span>
            <span className="graph-legend-count">{count}</span>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="graph-controls">
        <button className="graph-ctrl" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.5, 300)}><ZoomIn size={16} strokeWidth={1.8} /></button>
        <button className="graph-ctrl" onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 0.65, 300)}><ZoomOut size={16} strokeWidth={1.8} /></button>
        <button className="graph-ctrl" onClick={() => fgRef.current?.zoomToFit(400, 80)}><Maximize size={16} strokeWidth={1.8} /></button>
        <button className="graph-ctrl" onClick={() => { fgRef.current?.d3ReheatSimulation(); setTimeout(() => fgRef.current?.zoomToFit(400, 80), 1500) }}><RotateCcw size={16} strokeWidth={1.8} /></button>
      </div>

      <div className="graph-info">{nodes.length} entities &middot; {edges.length} relationships</div>
    </div>
  )
}
