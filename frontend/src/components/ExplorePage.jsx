import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import LiveFeed from './LiveFeed'
import SearchBar from './SearchBar'
import Pagination from './Pagination'
import NetworkBg from './NetworkBg'
import mobAngry from '../assets/mob-angry.png'
import mobAura from '../assets/mob-aura.png'
import { Plus, X } from 'lucide-react'

const PAGE_SIZE = 10

export default function ExplorePage() {
  const [hubs, setHubs] = useState([])
  const [activity, setActivity] = useState([])
  const [stats, setStats] = useState(null)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [imgLoaded, setImgLoaded] = useState(false)
  const navigate = useNavigate()

  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newTopic, setNewTopic] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newName.trim() || !newTopic.trim()) return
    setCreating(true); setCreateError('')
    try {
      const hub = await api.createHub(newName.trim(), newTopic.trim(), newDesc.trim())
      setNewName(''); setNewTopic(''); setNewDesc(''); setShowCreate(false)
      navigate(`/hubs/${hub.id}`)
    } catch (err) {
      setCreateError(err.message || 'Failed to create hub')
    } finally { setCreating(false) }
  }

  const load = useCallback(() => {
    api.listHubs().then(d => setHubs(d || [])).catch(console.error).finally(() => setLoading(false))
    api.getGlobalActivity(40).then(d => setActivity(d || [])).catch(() => {})
    api.getStats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    let iv = setInterval(load, 15000)
    const onVis = () => { clearInterval(iv); if (!document.hidden) { load(); iv = setInterval(load, 15000) } }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', onVis) }
  }, [load])

  const filtered = hubs.filter(h =>
    h.name.toLowerCase().includes(search.toLowerCase()) ||
    (h.topic || '').toLowerCase().includes(search.toLowerCase()) ||
    (h.description || '').toLowerCase().includes(search.toLowerCase())
  )

  useEffect(() => { setPage(1) }, [search])
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <>
      {/* HERO BANNER */}
      <div className="hero-banner">
        <NetworkBg />
        <div className="hero-content">
          <div className="hero-left">
            <div className="hero-eyebrow">
              <span className="hero-eyebrow-dot" />
              Agent-Powered Knowledge
            </div>
            <h1 className="hero-title">
              <span className="line-1">Graphs that</span><br />
              <span className="line-2">think, grow & evolve</span>
            </h1>
            <p className="hero-sub">
              Drop a topic. Agents swarm it — scouting sources, extracting entities, wiring relationships, and deepening the graph while you watch.
            </p>
            {stats && (
              <div className="hero-counters">
                <div className="hero-counter">
                  <div className="hero-counter-value c-cyan">{stats.hubs || 0}</div>
                  <div className="hero-counter-label">Hubs</div>
                </div>
                <div className="hero-counter">
                  <div className="hero-counter-value c-magenta">{stats.agents || 0}</div>
                  <div className="hero-counter-label">Agents</div>
                </div>
                <div className="hero-counter">
                  <div className="hero-counter-value c-green">{stats.events || 0}</div>
                  <div className="hero-counter-label">Events</div>
                </div>
              </div>
            )}
          </div>
          <div className="hero-right">
            <div className="hero-mob-glow" />
            <img
              src={mobAngry}
              alt="MobHub"
              className="hero-mob-img"
              style={{ opacity: imgLoaded ? 1 : 0, transition: 'opacity 0.8s ease-in' }}
              onLoad={() => setImgLoaded(true)}
            />
          </div>
        </div>
      </div>

      {/* EXPLORE */}
      <div className="explore-section">
        <div className="explore-header">
          <span className="explore-title">Knowledge Hubs</span>
          <button className="hero-cta" style={{ fontSize: 11, padding: '6px 14px' }} onClick={() => setShowCreate(true)}>
            <Plus size={13} /> New Hub
          </button>
        </div>

        <div className="explore-cols">
          <div className="explore-main">
            <div style={{ marginBottom: 16 }}>
              <SearchBar value={search} onChange={setSearch} placeholder="Search hubs..." resultCount={search ? filtered.length : undefined} />
            </div>

            {loading ? (
              Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton skeleton-card" />)
            ) : paged.length === 0 ? (
              <div className="empty-state">
                <img src={mobAura} alt="" className="empty-img" />
                <div className="empty-state-title">{search ? 'No matching hubs' : 'No hubs yet'}</div>
                <div className="empty-state-desc">
                  {search ? 'Try a different search.' : (
                    <button className="hero-cta" style={{ fontSize: 12, padding: '8px 16px', marginTop: 12 }} onClick={() => setShowCreate(true)}>
                      <Plus size={14} /> Create your first hub
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="hub-list">
                {paged.map(h => (
                  <div key={h.id} className="hub-card" onClick={() => navigate(`/hubs/${h.id}`)}>
                    <div className={`hub-card-accent ${h.status === 'seeding' ? 'seeding' : ''}`} />
                    <div className="hub-card-body">
                      <div className="hub-card-top">
                        <div className="hub-card-name">{h.name}</div>
                        <span className={`status status-${h.status}`}><span className="status-dot" />{h.status}</span>
                      </div>
                      {h.topic && <div className="hub-card-topic">{h.topic}</div>}
                      {h.description && <div className="hub-card-desc">{h.description}</div>}
                      <div className="hub-card-bar-wrap">
                        <div className="hub-card-bar">
                          <div className="hub-card-bar-fill" style={{ width: `${Math.min(100, (h.entity_count || 0) * 1.5)}%` }} />
                        </div>
                        <div className="hub-card-stats">
                          <span>{h.entity_count} entities</span>
                          <span>{h.edge_count} edges</span>
                        </div>
                      </div>
                    </div>
                    <div className="hub-card-side">
                      <div className="hub-card-side-value">{h.entity_count}</div>
                      <div className="hub-card-side-label">Nodes</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Pagination totalItems={filtered.length} pageSize={PAGE_SIZE} currentPage={page} onPageChange={setPage} />
          </div>

          <div className="explore-side">
            <LiveFeed entries={activity} title="Live Activity" />
          </div>
        </div>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 className="modal-title" style={{ margin: 0 }}>Create Knowledge Hub</h2>
              <button onClick={() => setShowCreate(false)} style={{ color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.5 }}>
              Give it a name and topic — agents will automatically discover, analyze, and build the knowledge graph.
            </p>
            {createError && <div className="auth-error">{createError}</div>}
            <form onSubmit={handleCreate}>
              <div className="input-group">
                <label className="input-label">Hub name</label>
                <input className="input" placeholder="e.g. Tesla, Rust Programming, Climate Tech" value={newName} onChange={e => setNewName(e.target.value)} autoFocus />
              </div>
              <div className="input-group">
                <label className="input-label">Topic</label>
                <input className="input" placeholder="e.g. electric vehicles and energy, systems programming" value={newTopic} onChange={e => setNewTopic(e.target.value)} />
              </div>
              <div className="input-group">
                <label className="input-label">Description <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(optional)</span></label>
                <textarea className="input" placeholder="What should the agents focus on?" value={newDesc} onChange={e => setNewDesc(e.target.value)} rows={2} style={{ resize: 'vertical' }} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn" onClick={() => setShowCreate(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={creating || !newName.trim() || !newTopic.trim()}>
                  {creating ? 'Creating...' : 'Create Hub'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
