import { useState, useEffect } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'

const TYPE_COLORS = { paper: 'cyan', url: 'green', text: 'electric', document: 'amber', api: 'magenta' }
const STATUS_COLORS = { pending: '', ingesting: 'amber', ingested: 'green', failed: 'red' }

export default function SourcesPanel({ hubId }) {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [addType, setAddType] = useState('text')
  const [addName, setAddName] = useState('')
  const [addContent, setAddContent] = useState('')
  const [addUrl, setAddUrl] = useState('')
  const [adding, setAdding] = useState(false)

  const load = () => { api.listSources(hubId).then(d => { setSources(d || []); setLoading(false) }).catch(() => setLoading(false)) }
  useEffect(() => { load(); const iv = setInterval(load, 10000); return () => clearInterval(iv) }, [hubId])

  const handleAdd = async () => {
    if (!addName.trim()) return; setAdding(true)
    try {
      await api.addSource(hubId, {
        source_type: addType, name: addName.trim(),
        content: addType === 'text' ? addContent : '',
        url: addType === 'url' ? addUrl : null,
        metadata: addType === 'paper' ? { topic: addName, limit: 15 } : null,
      })
      setAddName(''); setAddContent(''); setAddUrl(''); setShowAdd(false); load()
    } catch (e) { alert(e.message) }
    setAdding(false)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <span className="drawer-label">Sources ({sources.length})</span>
        <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(!showAdd)}>{showAdd ? 'Cancel' : 'Add Source'}</button>
      </div>

      {showAdd && (
        <div className="source-add-form">
          <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
            {['text', 'url', 'paper'].map(t => (
              <button key={t} className={`source-type-btn ${addType === t ? 'active' : ''}`}
                style={addType === t ? { color: `var(--${TYPE_COLORS[t]})`, borderColor: `var(--${TYPE_COLORS[t]})` } : {}}
                onClick={() => setAddType(t)}>{t}</button>
            ))}
          </div>
          <div style={{ marginBottom: 12 }}>
            <input className="input" placeholder={addType === 'paper' ? 'Research topic...' : 'Source name...'} value={addName} onChange={e => setAddName(e.target.value)} />
          </div>
          {addType === 'url' && <div style={{ marginBottom: 12 }}><input className="input" placeholder="https://..." value={addUrl} onChange={e => setAddUrl(e.target.value)} /></div>}
          {addType === 'text' && <div style={{ marginBottom: 12 }}><textarea className="input" placeholder="Paste content..." rows={5} value={addContent} onChange={e => setAddContent(e.target.value)} style={{ resize: 'vertical' }} /></div>}
          <button className="btn btn-primary" onClick={handleAdd} disabled={adding || !addName.trim()}>
            {adding ? <><span className="spinner" /> Ingesting...</> : 'Ingest Source'}
          </button>
        </div>
      )}

      {loading ? <div className="empty">Loading...</div> : sources.length === 0 ? (
        <div className="empty-state" style={{ padding: '40px 24px' }}>
          <div className="empty-state-title">No sources yet</div>
          <div className="empty-state-desc">Add text, URLs, or papers to build the knowledge graph.</div>
        </div>
      ) : (
        <div className="card-list">
          {sources.map(s => (
            <div key={s.id} className="source-card">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span className={`badge badge-${TYPE_COLORS[s.source_type] || ''}`}>{s.source_type}</span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{s.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 10, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-3)' }}>
                  {s.agent_name && <span>{s.agent_name}</span>}
                  <span>{timeAgo(s.created_at)}</span>
                  {s.entity_count > 0 && <span style={{ color: 'var(--cyan)' }}>+{s.entity_count} entities</span>}
                  {s.edge_count > 0 && <span style={{ color: 'var(--magenta)' }}>+{s.edge_count} edges</span>}
                </div>
                {s.error && <div style={{ fontSize: 11, color: 'var(--red)', marginTop: 4 }}>{s.error}</div>}
              </div>
              <span className={`badge badge-${STATUS_COLORS[s.status] || ''}`}>{s.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
