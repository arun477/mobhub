import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import mobHero from '../assets/mob-hero.png'
import { Plus, ArrowRight, Bot, Zap } from 'lucide-react'

export default function AgentPanel() {
  const [hubs, setHubs] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  // Create hub form
  const [newName, setNewName] = useState('')
  const [newTopic, setNewTopic] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  useEffect(() => {
    api.listHubs().then(d => setHubs(d || [])).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newName.trim() || !newTopic.trim()) return
    setCreating(true); setCreateError('')
    try {
      const hub = await api.createHub(newName.trim(), newTopic.trim(), newDesc.trim())
      navigate(`/hubs/${hub.id}`)
    } catch (err) {
      setCreateError(err.message || 'Failed to create hub')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 600, paddingTop: 40, margin: '0 auto' }}>
      {/* Hero */}
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <img src={mobHero} alt="" style={{ width: 120, marginBottom: 16, filter: 'drop-shadow(0 0 40px rgba(0,229,255,0.1))' }} />
        <h1 style={{ fontSize: 32, fontWeight: 900, letterSpacing: '-1.5px', marginBottom: 8 }}>
          Create a Knowledge Hub
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.6, maxWidth: 400, margin: '0 auto' }}>
          Name any topic. A team of autonomous agents will discover, analyze, verify, and build the knowledge graph for you.
        </p>
      </div>

      {/* How it works */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 32 }}>
        {[
          { icon: Plus, color: 'var(--cyan)', label: 'Create', desc: 'Name a topic' },
          { icon: Bot, color: 'var(--electric)', label: 'Agents spawn', desc: '6 autonomous agents' },
          { icon: Zap, color: 'var(--green)', label: 'Knowledge builds', desc: 'Search, verify, enrich' },
        ].map(step => (
          <div key={step.label} style={{
            background: 'var(--surface)', border: '1px solid var(--glass-border)',
            borderRadius: 14, padding: '16px 14px', textAlign: 'center',
          }}>
            <step.icon size={20} style={{ color: step.color, marginBottom: 8 }} />
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 2 }}>{step.label}</div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>{step.desc}</div>
          </div>
        ))}
      </div>

      {/* Create form */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--glass-border)',
        borderRadius: 20, padding: '28px 28px 24px', marginBottom: 32,
      }}>
        {createError && <div className="auth-error">{createError}</div>}
        <form onSubmit={handleCreate}>
          <div className="input-group">
            <label className="input-label">Hub name</label>
            <input
              className="input" autoFocus
              placeholder="e.g. Tesla, Rust Programming, Climate Tech, NousResearch"
              value={newName} onChange={e => setNewName(e.target.value)}
            />
          </div>
          <div className="input-group">
            <label className="input-label">Topic</label>
            <input
              className="input"
              placeholder="e.g. electric vehicles, systems programming, AI research"
              value={newTopic} onChange={e => setNewTopic(e.target.value)}
            />
          </div>
          <div className="input-group">
            <label className="input-label">
              Description <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(optional — guides what agents focus on)</span>
            </label>
            <textarea
              className="input"
              placeholder="e.g. Focus on key people, recent developments, and competitive landscape"
              value={newDesc} onChange={e => setNewDesc(e.target.value)}
              rows={2} style={{ resize: 'vertical' }}
            />
          </div>
          <button
            type="submit" className="btn btn-primary"
            style={{ width: '100%', padding: '12px', fontSize: 14, fontWeight: 700 }}
            disabled={creating || !newName.trim() || !newTopic.trim()}
          >
            {creating ? 'Spawning agents...' : 'Create Hub & Launch Agents'}
          </button>
        </form>
      </div>

      {/* Recent hubs */}
      {hubs.length > 0 && (
        <>
          <div style={{
            fontSize: 11, fontFamily: 'var(--mono)', fontWeight: 700,
            color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.12em',
            marginBottom: 12,
          }}>
            Recent Hubs
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {hubs.slice(0, 5).map(h => (
              <div
                key={h.id}
                onClick={() => navigate(`/hubs/${h.id}`)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  background: 'var(--surface)', border: '1px solid var(--glass-border)',
                  borderRadius: 12, padding: '12px 16px', cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(0,229,255,0.2)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--glass-border)'}
              >
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>{h.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
                    {h.entity_count} entities &middot; {h.edge_count} edges
                  </div>
                </div>
                <ArrowRight size={14} style={{ color: 'var(--text-3)' }} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
