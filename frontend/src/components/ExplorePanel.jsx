import { useState, useEffect } from 'react'
import { api } from '../api'

function PathFinder({ hubId, nodes }) {
  const [fromId, setFromId] = useState('')
  const [toId, setToId] = useState('')
  const [fromSearch, setFromSearch] = useState('')
  const [toSearch, setToSearch] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const search = async () => {
    if (!fromId || !toId) return; setLoading(true)
    try { setResult(await api.findPath(hubId, fromId, toId)) }
    catch { setResult({ hops: -1, nodes: [], edges: [], message: 'Error' }) }
    setLoading(false)
  }

  const filteredFrom = nodes.filter(n => n.name.toLowerCase().includes(fromSearch.toLowerCase()))
  const filteredTo = nodes.filter(n => n.name.toLowerCase().includes(toSearch.toLowerCase()))
  const fromNode = nodes.find(n => n.uuid === fromId)
  const toNode = nodes.find(n => n.uuid === toId)

  return (
    <div className="explore-card">
      <div className="explore-card-title">Path Finder</div>
      <div className="explore-card-desc">How are two entities connected?</div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 160, position: 'relative' }}>
          <input className="input" placeholder="From entity..." value={fromNode ? fromNode.name : fromSearch}
            onChange={e => { setFromSearch(e.target.value); setFromId('') }} style={{ fontSize: 12, padding: '8px 12px' }} />
          {fromSearch && !fromId && filteredFrom.length > 0 && (
            <div className="autocomplete-dropdown">
              {filteredFrom.slice(0, 8).map(n => (
                <div key={n.uuid} className="autocomplete-item" onClick={() => { setFromId(n.uuid); setFromSearch('') }}>{n.name}</div>
              ))}
            </div>
          )}
        </div>
        <span style={{ color: 'var(--text-3)', alignSelf: 'flex-start', paddingTop: 8, fontSize: 16 }}>&rarr;</span>
        <div style={{ flex: 1, minWidth: 160, position: 'relative' }}>
          <input className="input" placeholder="To entity..." value={toNode ? toNode.name : toSearch}
            onChange={e => { setToSearch(e.target.value); setToId('') }} style={{ fontSize: 12, padding: '8px 12px' }} />
          {toSearch && !toId && filteredTo.length > 0 && (
            <div className="autocomplete-dropdown">
              {filteredTo.slice(0, 8).map(n => (
                <div key={n.uuid} className="autocomplete-item" onClick={() => { setToId(n.uuid); setToSearch('') }}>{n.name}</div>
              ))}
            </div>
          )}
        </div>
        <button className="btn btn-primary btn-sm" style={{ alignSelf: 'flex-start' }} onClick={search} disabled={loading || !fromId || !toId}>
          {loading ? <span className="spinner" /> : 'Find'}
        </button>
      </div>
      {result && (
        result.hops < 0 ? <div style={{ color: 'var(--text-3)', fontSize: 13 }}>No path found.</div> : (
          <div>
            <div style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--cyan)', marginBottom: 8 }}>{result.hops} hop{result.hops !== 1 ? 's' : ''}</div>
            <div className="path-chain">
              {result.nodes.map((n, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span className="path-node">{n.name}</span>
                  {i < result.nodes.length - 1 && result.edges[i] && (
                    <span className="path-edge">&mdash; {result.edges[i].fact || result.edges[i].name} &rarr;</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      )}
    </div>
  )
}

function Clusters({ hubId }) {
  const [clusters, setClusters] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { api.getClusters(hubId).then(setClusters).catch(() => {}).finally(() => setLoading(false)) }, [hubId])

  if (loading) return <div className="empty">Detecting clusters...</div>
  if (!clusters?.length) return <div style={{ color: 'var(--text-3)', fontSize: 13, padding: 16 }}>No clusters detected.</div>

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="explore-card-title" style={{ marginBottom: 12 }}>Knowledge Clusters</div>
      <div className="card-list">
        {clusters.map((c, i) => (
          <div key={i} className="cluster-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{c.representative}</span>
              <span className="badge badge-cyan">{c.size} entities</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {c.entities.slice(0, 10).map((e, j) => (
                <span key={j} className="cluster-entity-tag">{e.name} <span style={{ color: 'var(--text-3)' }}>({e.connections})</span></span>
              ))}
              {c.entities.length > 10 && <span style={{ fontSize: 10, color: 'var(--text-3)', padding: '3px 4px' }}>+{c.entities.length - 10}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Gaps({ hubId }) {
  const [gaps, setGaps] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { api.getGaps(hubId).then(setGaps).catch(() => {}).finally(() => setLoading(false)) }, [hubId])

  if (loading) return <div className="empty">Scanning for gaps...</div>
  if (!gaps?.length) return <div style={{ color: 'var(--text-3)', fontSize: 13, padding: 16 }}>No knowledge gaps.</div>

  return (
    <div>
      <div className="explore-card-title" style={{ marginBottom: 12 }}>Knowledge Gaps</div>
      <div className="card-list">
        {gaps.map((g, i) => (
          <div key={i} className="gap-card">
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{g.name}</div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {g.reasons.map((r, j) => <span key={j} className="badge badge-amber">{r}</span>)}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div className="gap-score" style={{ color: g.gap_score >= 4 ? 'var(--red)' : g.gap_score >= 2 ? 'var(--amber)' : 'var(--text-3)' }}>{g.gap_score}</div>
              <div className="gap-score-label">Gap</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ExplorePanel({ hubId, nodes }) {
  return (
    <div>
      <PathFinder hubId={hubId} nodes={nodes} />
      <Clusters hubId={hubId} />
      <Gaps hubId={hubId} />
    </div>
  )
}
