import { useState, useEffect } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'
import { ExternalLink, Twitter, Linkedin, Github, Globe, Image, FileText } from 'lucide-react'

const TYPE_COLORS = {
  Person: '#00e5ff', Organization: '#ff2d78', Concept: '#5b5bff', Method: '#00e676',
  Tool: '#ffab00', Event: '#ff3d3d', Dataset: '#84cc16', Location: '#ec4899',
}

function hashColor(s) {
  let h = 0; for (let i = 0; i < s.length; i++) h = s.charCodeAt(i) + ((h << 5) - h)
  return Object.values(TYPE_COLORS)[Math.abs(h) % Object.values(TYPE_COLORS).length]
}

// Map asset names to icons
function getLinkIcon(name) {
  const n = (name || '').toLowerCase()
  if (n.includes('twitter') || n.includes('x.com')) return Twitter
  if (n.includes('linkedin')) return Linkedin
  if (n.includes('github')) return Github
  if (n.includes('website')) return Globe
  return ExternalLink
}

// Human-readable metadata key labels
const META_LABELS = {
  role: 'Role',
  organization: 'Organization',
  location: 'Location',
  expertise: 'Expertise',
  education: 'Education',
  notable_achievement: 'Notable',
  org_type: 'Type',
  founded: 'Founded',
  headquarters: 'Headquarters',
  ceo: 'CEO',
  key_people: 'Key People',
  products: 'Products',
  funding: 'Funding',
}

export default function EntityProfile({ hubId, uuid, onClose, onNavigate }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [imgError, setImgError] = useState(false)

  useEffect(() => {
    if (!uuid) return
    setLoading(true)
    setImgError(false)
    api.getEntityDetail(hubId, uuid).then(d => { setDetail(d); setLoading(false) }).catch(() => setLoading(false))
  }, [hubId, uuid])

  if (loading) return (
    <div className="entity-profile">
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>Loading entity...</div>
    </div>
  )

  if (!detail) return (
    <div className="entity-profile">
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>Entity not found</div>
    </div>
  )

  const entityType = (detail.labels || []).find(l => TYPE_COLORS[l]) || 'Concept'
  const otherLabels = (detail.labels || []).filter(l => l !== entityType)
  const color = TYPE_COLORS[entityType] || hashColor(detail.name)
  const meta = detail.metadata || {}
  const assets = detail.assets || []
  const neighbors = detail.neighbors || []
  const provenance = detail.provenance || []
  const confidence = detail.confidence

  const imageAssets = assets.filter(a => a.asset_type === 'image')
  const urlAssets = assets.filter(a => a.asset_type === 'url')
  const otherAssets = assets.filter(a => a.asset_type !== 'url' && a.asset_type !== 'image')
  const profileImage = imageAssets[0]?.content

  // Sort metadata by our preferred order
  const metaEntries = Object.entries(meta).sort((a, b) => {
    const order = Object.keys(META_LABELS)
    const ai = order.indexOf(a[0]); const bi = order.indexOf(b[0])
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })

  return (
    <div className="entity-profile">
      {/* HEADER */}
      <div className="entity-profile-header">
        {/* Avatar — use image if available */}
        {profileImage && !imgError ? (
          <img
            src={profileImage} alt={detail.name}
            onError={() => setImgError(true)}
            style={{
              width: 64, height: 64, borderRadius: 16, objectFit: 'cover', flexShrink: 0,
              border: `2px solid ${color}20`,
            }}
          />
        ) : (
          <div className="entity-profile-avatar" style={{ backgroundColor: color }}>
            {detail.name.charAt(0).toUpperCase()}
          </div>
        )}

        <div className="entity-profile-info">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {onClose && (
              <button onClick={onClose} style={{ color: 'var(--text-3)', fontSize: 14, background: 'none', border: 'none', cursor: 'pointer', marginRight: 4 }}>&larr;</button>
            )}
            <div className="entity-profile-name">{detail.name}</div>
          </div>
          <div className="entity-profile-type" style={{ color }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
            {entityType}
            {otherLabels.map(l => (
              <span key={l} className="badge" style={{ marginLeft: 4 }}>{l}</span>
            ))}
          </div>

          {/* Quick role/org line for persons */}
          {(meta.role || meta.organization) && (
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4, fontFamily: 'var(--mono)' }}>
              {meta.role}{meta.role && meta.organization ? ' at ' : ''}{meta.organization}
            </div>
          )}

          {detail.summary && <div className="entity-profile-summary">{detail.summary}</div>}

          {/* Social links — inline row */}
          {urlAssets.length > 0 && (
            <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
              {urlAssets.map((a, i) => {
                const Icon = getLinkIcon(a.name)
                return (
                  <a key={i} href={a.content} target="_blank" rel="noopener noreferrer"
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '3px 10px', borderRadius: 6,
                      background: 'rgba(255,255,255,0.04)', border: '1px solid var(--glass-border)',
                      color: 'var(--text-2)', fontSize: 11, fontFamily: 'var(--mono)', fontWeight: 600,
                      textDecoration: 'none', transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(0,229,255,0.3)'; e.currentTarget.style.color = 'var(--cyan)' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--glass-border)'; e.currentTarget.style.color = 'var(--text-2)' }}
                  >
                    <Icon size={12} /> {a.name}
                  </a>
                )
              })}
            </div>
          )}

          {/* Confidence */}
          {confidence != null && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
              <div style={{ width: 80, height: 4, background: 'rgba(255,255,255,0.04)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ width: `${Math.round(confidence * 100)}%`, height: '100%', borderRadius: 2,
                  background: confidence >= 0.7 ? 'var(--green)' : confidence >= 0.4 ? 'var(--amber)' : 'var(--red)' }} />
              </div>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)', fontWeight: 700 }}>{Math.round(confidence * 100)}%</span>
              <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
                {detail.vote_counts?.agree || 0}&#x2191; {detail.vote_counts?.disagree || 0}&#x2193;
              </span>
            </div>
          )}
        </div>
      </div>

      {/* IMAGES — gallery */}
      {imageAssets.length > 1 && (
        <div className="entity-profile-section">
          <div className="entity-profile-section-title">Images ({imageAssets.length})</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {imageAssets.map((a, i) => (
              <img key={i} src={a.content} alt={a.name}
                style={{
                  width: 80, height: 80, borderRadius: 10, objectFit: 'cover',
                  border: '1px solid var(--glass-border)', cursor: 'pointer',
                }}
                onError={e => e.currentTarget.style.display = 'none'}
                onClick={() => window.open(a.content, '_blank')}
              />
            ))}
          </div>
        </div>
      )}

      {/* METADATA — structured fields */}
      {metaEntries.length > 0 && (
        <div className="entity-profile-section">
          <div className="entity-profile-section-title">Details</div>
          <div className="entity-meta-grid">
            {metaEntries.map(([key, value]) => (
              <div key={key} className="entity-meta-item">
                <div className="entity-meta-key">{META_LABELS[key] || key.replace(/_/g, ' ')}</div>
                <div className="entity-meta-value">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CONNECTIONS */}
      {neighbors.length > 0 && (
        <div className="entity-profile-section">
          <div className="entity-profile-section-title">Connections ({neighbors.length})</div>
          {neighbors.slice(0, 15).map((n, i) => (
            <div key={i} className="entity-neighbor-item"
              style={{ cursor: onNavigate ? 'pointer' : 'default' }}
              onClick={() => onNavigate && onNavigate(n.neighbor_uuid)}>
              <span style={{ width: 28, height: 28, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, color: 'white', background: hashColor(n.neighbor_name || ''), flexShrink: 0 }}>
                {(n.neighbor_name || '?').charAt(0).toUpperCase()}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="entity-neighbor-name">{n.neighbor_name}</div>
                <div className="entity-neighbor-edge">{n.edge_fact || n.edge_name}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* OTHER ASSETS */}
      {otherAssets.length > 0 && (
        <div className="entity-profile-section">
          <div className="entity-profile-section-title">Assets ({otherAssets.length})</div>
          {otherAssets.map((a, i) => (
            <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid var(--glass-border)', fontSize: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
              {a.asset_type === 'note' ? <FileText size={14} style={{ color: 'var(--text-3)' }} /> : <Image size={14} style={{ color: 'var(--text-3)' }} />}
              <span style={{ fontWeight: 600 }}>{a.name}</span>
              <span className={`badge badge-${a.asset_type === 'image' ? 'magenta' : 'amber'}`}>{a.asset_type}</span>
            </div>
          ))}
        </div>
      )}

      {/* PROVENANCE */}
      {provenance.length > 0 && (
        <div className="entity-profile-section">
          <div className="entity-profile-section-title">Provenance ({provenance.length})</div>
          {provenance.slice(0, 8).map((p, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--glass-border)', fontSize: 12 }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 2 }}>
                <span className={`badge ${(p.source_type || '').includes('seed') ? 'badge-cyan' : 'badge-green'}`}>
                  {(p.source_type || '').replace(/_/g, ' ')}
                </span>
                {p.agent_name && <span style={{ color: 'var(--cyan)', fontFamily: 'var(--mono)', fontWeight: 600, fontSize: 11 }}>{p.agent_name}</span>}
                <span style={{ color: 'var(--text-3)', fontFamily: 'var(--mono)', fontSize: 10 }}>{timeAgo(p.created_at)}</span>
              </div>
              {p.paper_title && <div style={{ color: 'var(--text-2)', fontSize: 11 }}>{p.paper_title}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
