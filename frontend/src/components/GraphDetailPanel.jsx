import { useState, useEffect } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'
import { X, ExternalLink, Twitter, Linkedin, Github, Globe, Bot } from 'lucide-react'

const TYPE_COLORS = {
  Person: '#00e5ff', Organization: '#ff2d78', Concept: '#5b5bff', Method: '#00e676',
  Tool: '#ffab00', Event: '#ff3d3d', Dataset: '#84cc16', Location: '#ec4899',
}

const META_LABELS = {
  role: 'Role', organization: 'Organization', location: 'Location',
  expertise: 'Expertise', org_type: 'Type', founded: 'Founded',
  headquarters: 'HQ', ceo: 'CEO', key_people: 'Key People', products: 'Products',
}

function hashColor(s) {
  let h = 0; for (let i = 0; i < s.length; i++) h = s.charCodeAt(i) + ((h << 5) - h)
  return Object.values(TYPE_COLORS)[Math.abs(h) % Object.values(TYPE_COLORS).length]
}

function getLinkIcon(name) {
  const n = (name || '').toLowerCase()
  if (n.includes('twitter') || n.includes('x')) return Twitter
  if (n.includes('linkedin')) return Linkedin
  if (n.includes('github')) return Github
  if (n.includes('website')) return Globe
  return ExternalLink
}

export default function GraphDetailPanel({ hubId, uuid, onClose, onNavigate }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    if (!uuid) return
    setLoading(true)
    setImgError(false)
    api.getEntityDetail(hubId, uuid)
      .then(d => { setDetail(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [hubId, uuid])

  if (loading) {
    return (
      <div className="graph-detail-panel">
        <div className="graph-detail-header">
          <span style={{ color: 'var(--text-3)', fontSize: 13 }}>Loading...</span>
          <button className="graph-detail-close" onClick={onClose}><X size={16} /></button>
        </div>
      </div>
    )
  }

  if (!detail) {
    return (
      <div className="graph-detail-panel">
        <div className="graph-detail-header">
          <span style={{ color: 'var(--text-3)', fontSize: 13 }}>Entity not found</span>
          <button className="graph-detail-close" onClick={onClose}><X size={16} /></button>
        </div>
      </div>
    )
  }

  const entityType = (detail.labels || []).find(l => TYPE_COLORS[l]) || 'Concept'
  const color = TYPE_COLORS[entityType] || hashColor(detail.name)
  const meta = detail.metadata || {}
  const assets = detail.assets || []
  const neighbors = detail.neighbors || []
  const provenance = detail.provenance || []
  const confidence = detail.confidence

  const imageAssets = assets.filter(a => a.asset_type === 'image')
  const urlAssets = assets.filter(a => a.asset_type === 'url')
  const profileImage = imageAssets[0]?.content
  const isEnriched = Object.keys(meta).length > 0 || urlAssets.length > 0

  // Sort metadata
  const metaEntries = Object.entries(meta).sort((a, b) => {
    const order = Object.keys(META_LABELS)
    return (order.indexOf(a[0]) === -1 ? 99 : order.indexOf(a[0])) - (order.indexOf(b[0]) === -1 ? 99 : order.indexOf(b[0]))
  })

  return (
    <div className="graph-detail-panel">
      {/* Header */}
      <div className="graph-detail-header">
        <div style={{ display: 'flex', gap: 12, flex: 1, minWidth: 0, alignItems: 'flex-start' }}>
          {/* Avatar / Image */}
          {profileImage && !imgError ? (
            <img src={profileImage} alt={detail.name} onError={() => setImgError(true)}
              style={{ width: 48, height: 48, borderRadius: 12, objectFit: 'cover', flexShrink: 0, border: `2px solid ${color}20` }}
            />
          ) : (
            <div style={{
              width: 48, height: 48, borderRadius: 12, background: color,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18, fontWeight: 800, color: 'white', flexShrink: 0
            }}>
              {detail.name.charAt(0).toUpperCase()}
            </div>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="graph-detail-type" style={{ color }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block', flexShrink: 0 }} />
              {entityType}
              {isEnriched && (
                <span style={{ marginLeft: 4, fontSize: 8, color: 'var(--green)', background: 'rgba(0,230,118,0.08)', padding: '1px 5px', borderRadius: 3 }}>
                  <Bot size={8} style={{ marginRight: 2 }} />PROFILED
                </span>
              )}
            </div>
            <div className="graph-detail-name">{detail.name}</div>
            {/* Role/org subtitle */}
            {(meta.role || meta.organization) && (
              <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--mono)', marginTop: 2 }}>
                {meta.role}{meta.role && meta.organization ? ' at ' : ''}{meta.organization}
              </div>
            )}
            {/* Org type subtitle */}
            {meta.org_type && !meta.role && (
              <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--mono)', marginTop: 2 }}>
                {meta.org_type}{meta.founded ? ` · Founded ${meta.founded}` : ''}{meta.headquarters ? ` · ${meta.headquarters}` : ''}
              </div>
            )}
          </div>
        </div>
        <button className="graph-detail-close" onClick={onClose}><X size={16} /></button>
      </div>

      <div className="graph-detail-body">
        {/* Summary */}
        {detail.summary && (
          <div className="graph-detail-summary">{detail.summary}</div>
        )}

        {/* Social links — icon pills */}
        {urlAssets.length > 0 && (
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 16 }}>
            {urlAssets.map((a, i) => {
              const Icon = getLinkIcon(a.name)
              return (
                <a key={i} href={a.content} target="_blank" rel="noopener noreferrer"
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '3px 8px', borderRadius: 5,
                    background: 'rgba(255,255,255,0.04)', border: '1px solid var(--glass-border)',
                    color: 'var(--text-2)', fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600,
                    textDecoration: 'none', transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(0,229,255,0.3)'; e.currentTarget.style.color = 'var(--cyan)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--glass-border)'; e.currentTarget.style.color = 'var(--text-2)' }}
                >
                  <Icon size={10} /> {a.name}
                </a>
              )
            })}
          </div>
        )}

        {/* Confidence */}
        {confidence != null && (
          <div className="graph-detail-confidence">
            <div className="graph-detail-conf-bar">
              <div className="graph-detail-conf-fill" style={{
                width: `${Math.round(confidence * 100)}%`,
                background: confidence >= 0.7 ? 'var(--green)' : confidence >= 0.4 ? 'var(--amber)' : 'var(--red)'
              }} />
            </div>
            <span className="graph-detail-conf-text">{Math.round(confidence * 100)}%</span>
          </div>
        )}

        {/* Metadata grid */}
        {metaEntries.length > 0 && (
          <div className="graph-detail-section">
            <div className="graph-detail-section-title">Details</div>
            {metaEntries.map(([key, value]) => (
              <div key={key} className="graph-detail-meta-row">
                <span className="graph-detail-meta-key">{META_LABELS[key] || key.replace(/_/g, ' ')}</span>
                <span className="graph-detail-meta-val">{value}</span>
              </div>
            ))}
          </div>
        )}

        {/* Connections */}
        {neighbors.length > 0 && (
          <div className="graph-detail-section">
            <div className="graph-detail-section-title">Connections ({neighbors.length})</div>
            {neighbors.slice(0, 20).map((n, i) => (
              <div key={i} className="graph-detail-neighbor"
                onClick={() => onNavigate?.(n.neighbor_uuid)}>
                <span className="graph-detail-neighbor-avatar" style={{ background: hashColor(n.neighbor_name || '') }}>
                  {(n.neighbor_name || '?').charAt(0).toUpperCase()}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="graph-detail-neighbor-name">{n.neighbor_name}</div>
                  <div className="graph-detail-neighbor-edge">{n.edge_fact || n.edge_name}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Provenance */}
        {provenance.length > 0 && (
          <div className="graph-detail-section">
            <div className="graph-detail-section-title">Sources ({provenance.length})</div>
            {provenance.slice(0, 6).map((p, i) => (
              <div key={i} className="graph-detail-prov">
                <span className={`badge ${(p.source_type || '').includes('seed') ? 'badge-cyan' : 'badge-green'}`}>
                  {(p.source_type || '').replace(/_/g, ' ')}
                </span>
                {p.agent_name && <span style={{ color: 'var(--cyan)', fontFamily: 'var(--mono)', fontWeight: 600, fontSize: 10 }}>{p.agent_name}</span>}
                <span style={{ color: 'var(--text-3)', fontFamily: 'var(--mono)', fontSize: 10 }}>{timeAgo(p.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
