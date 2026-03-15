import { useEffect, useRef } from 'react'

export default function NetworkBg() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    let W, H, particles, animId

    function resize() {
      W = canvas.parentElement.offsetWidth
      H = canvas.parentElement.offsetHeight
      canvas.width = W * dpr
      canvas.height = H * dpr
      canvas.style.width = W + 'px'
      canvas.style.height = H + 'px'
      ctx.scale(dpr, dpr)
    }

    function init() {
      resize()
      const count = Math.floor((W * H) / 12000)
      particles = Array.from({ length: Math.min(count, 80) }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 1.5 + 0.5,
        // Random psychic color
        color: ['#00e5ff', '#5b5bff', '#ff2d78', '#00e676'][Math.floor(Math.random() * 4)],
        pulse: Math.random() * Math.PI * 2,
      }))
    }

    function draw() {
      ctx.clearRect(0, 0, W, H)

      const connectDist = 140
      const time = Date.now() * 0.001

      // Draw connections
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i], b = particles[j]
          const dx = a.x - b.x, dy = a.y - b.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < connectDist) {
            const alpha = (1 - dist / connectDist) * 0.12
            // Gradient line between two particle colors
            const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y)
            grad.addColorStop(0, a.color)
            grad.addColorStop(1, b.color)
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.strokeStyle = grad
            ctx.globalAlpha = alpha
            ctx.lineWidth = 0.6
            ctx.stroke()
            ctx.globalAlpha = 1
          }
        }
      }

      // Draw particles with glow
      for (const p of particles) {
        const pulseAlpha = 0.4 + Math.sin(time * 1.5 + p.pulse) * 0.3

        // Outer glow
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 8)
        glow.addColorStop(0, p.color + '18')
        glow.addColorStop(1, p.color + '00')
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r * 8, 0, Math.PI * 2)
        ctx.fillStyle = glow
        ctx.fill()

        // Core dot
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = p.color
        ctx.globalAlpha = pulseAlpha
        ctx.fill()
        ctx.globalAlpha = 1

        // Move
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > W) p.vx *= -1
        if (p.y < 0 || p.y > H) p.vy *= -1
      }

      // Occasional energy sparks — random short lines
      if (Math.random() < 0.03) {
        const sx = Math.random() * W
        const sy = Math.random() * H
        const angle = Math.random() * Math.PI * 2
        const len = 20 + Math.random() * 40
        const color = ['#00e5ff', '#ff2d78', '#5b5bff'][Math.floor(Math.random() * 3)]
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(sx + Math.cos(angle) * len, sy + Math.sin(angle) * len)
        ctx.strokeStyle = color
        ctx.globalAlpha = 0.15
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.globalAlpha = 1
      }

      animId = requestAnimationFrame(draw)
    }

    init()
    draw()

    const onResize = () => { cancelAnimationFrame(animId); init(); draw() }
    window.addEventListener('resize', onResize)
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', onResize) }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute', inset: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none', zIndex: 1,
      }}
    />
  )
}
