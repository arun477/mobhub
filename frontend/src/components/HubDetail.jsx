import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { timeAgo } from '../utils'
import GraphView from './GraphView'
import GraphDetailPanel from './GraphDetailPanel'
import GraphSearch from './GraphSearch'
import SearchBar from './SearchBar'
import Pagination from './Pagination'
import ChatPanel from './ChatPanel'
import Timeline from './Timeline'
import EntityProfile from './EntityProfile'
import mobAura from '../assets/mob-aura.png'
import AgentPlayground from './AgentPlayground'
import PlaygroundView from './PlaygroundView'
import {
  CircleDot, MessageSquare, Diamond, ArrowLeftRight,
  Database, Clock, Users, Bot,
  User, Building2, Cpu, FlaskConical, MapPin, Calendar, Box, Layers,
  Waves
} from 'lucide-react'

const ENTITY_PAGE = 20
const EDGE_PAGE = 25
const MEMBER_PAGE = 20

const COLORS = ['#00e5ff', '#ff2d78', '#5b5bff', '#00e676', '#ffab00', '#ff3d3d']
function hashColor(s) {
  let h = 0; for (let i = 0; i < s.length; i++) h = s.charCodeAt(i) + ((h << 5) - h)
  return COLORS[Math.abs(h) % COLORS.length]
}

const TYPE_CONFIG = {
  Person:       { Icon: User, color: '#00e5ff', bg: 'rgba(0,229,255,0.08)' },
  Organization: { Icon: Building2, color: '#ff2d78', bg: 'rgba(255,45,120,0.08)' },
  Tool:         { Icon: Cpu, color: '#ffab00', bg: 'rgba(255,171,0,0.08)' },
  Method:       { Icon: FlaskConical, color: '#5b5bff', bg: 'rgba(91,91,255,0.08)' },
  Concept:      { Icon: Layers, color: '#5b5bff', bg: 'rgba(91,91,255,0.08)' },
  Dataset:      { Icon: Database, color: '#00e676', bg: 'rgba(0,230,118,0.08)' },
  Location:     { Icon: MapPin, color: '#ff3d3d', bg: 'rgba(255,61,61,0.08)' },
  Event:        { Icon: Calendar, color: '#ffab00', bg: 'rgba(255,171,0,0.08)' },
}
const DEFAULT_TYPE = { Icon: Box, color: '#666', bg: 'rgba(255,255,255,0.04)' }

const SECTION_TITLES = {
  entities: 'Entities',
  relationships: 'Relationships',
  agents: 'Agents',
  timeline: 'Timeline',
  members: 'Members',
  chat: 'Chat',
}

const NAV_SECTIONS = [
  { type: 'section', label: 'Analyze' },
  { id: 'graph', Icon: CircleDot, label: 'Graph View' },
  { id: 'chat', Icon: MessageSquare, label: 'Chat' },
  { type: 'section', label: 'Knowledge' },
  { id: 'entities', Icon: Diamond, label: 'Entities' },
  { id: 'relationships', Icon: ArrowLeftRight, label: 'Relationships' },
  { type: 'section', label: 'System' },
  { id: 'playground', Icon: Waves, label: 'Playground' },
  { id: 'agents', Icon: Bot, label: 'Agents' },
]

function ConfidenceBar({ confidence, voteCount, provenanceCount, assetCount }) {
  const pct = confidence != null ? Math.round(confidence * 100) : null
  const color = pct == null ? 'var(--text-3)' : pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--amber)' : 'var(--red)'
  return (
    <div className="confidence-row">
      {pct != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div className="confidence-track"><div className="confidence-fill" style={{ width: `${pct}%`, background: color }} /></div>
          <span style={{ color }}>{pct}%</span>
        </div>
      )}
      {voteCount > 0 && <span>{voteCount} vote{voteCount !== 1 ? 's' : ''}</span>}
      {provenanceCount > 0 && <span>{provenanceCount} source{provenanceCount !== 1 ? 's' : ''}</span>}
      {assetCount > 0 && <span>{assetCount} asset{assetCount !== 1 ? 's' : ''}</span>}
    </div>
  )
}

export default function HubDetail() {
  const { id } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [hub, setHub] = useState(null)
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const section = searchParams.get('tab') || 'agents'
  const setSection = (s) => setSearchParams({ tab: s }, { replace: true })
  const [entityPage, setEntityPage] = useState(1)
  const [edgePage, setEdgePage] = useState(1)
  const [memberPage, setMemberPage] = useState(1)
  // Entity profile
  const [profileUuid, setProfileUuid] = useState(null)
  // Graph state
  const [selectedGraphEntity, setSelectedGraphEntity] = useState(null)
  const [graphHighlight, setGraphHighlight] = useState(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searchLoading, setSearchLoading] = useState(false)

  const load = useCallback(() => {
    api.getHub(id).then(setHub).catch(console.error)
    api.getNodes(id).then(d => setNodes(d || [])).catch(() => {})
    api.getEdges(id).then(d => setEdges(d || [])).catch(() => {})
  }, [id])

  useEffect(() => {
    load()
    let iv = setInterval(load, 15000)
    const onVis = () => { clearInterval(iv); if (!document.hidden) { load(); iv = setInterval(load, 15000) } }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(iv); document.removeEventListener('visibilitychange', onVis) }
  }, [load])


  const handleSearch = async (q) => {
    if (!q?.trim()) { setSearchResults(null); return }
    setSearchLoading(true)
    try { setSearchResults(await api.searchGraph(id, q, 15)) } catch { setSearchResults([]) }
    setSearchLoading(false)
  }

  if (!hub) return (
    <div style={{ padding: '60px 24px', textAlign: 'center', color: 'var(--text-3)' }}>Loading hub...</div>
  )

  const members = hub.members || []

  return (
    <div className="hub-layout">
      {/* ICON SHELF */}
      <Sidebar section={section} setSection={setSection} />

      {/* GRAPH — full bleed mode */}
      {section === 'graph' && (
        <div className="hub-main-graph">
          {/* Compact header overlay */}
          <div className="graph-header-bar">
            <div className="graph-header-left">
              <h1 className="graph-header-title">{hub.name}</h1>
              <span className={`status status-${hub.status}`}><span className="status-dot" />{hub.status}</span>
            </div>
            <div className="graph-header-right">
              <GraphSearch
                nodes={nodes}
                onSelect={(uuid) => setSelectedGraphEntity(uuid)}
                onHighlight={setGraphHighlight}
              />
              <div className="graph-header-stats">
                <span style={{ color: 'var(--cyan)' }}>{nodes.length}</span> entities
                <span style={{ color: 'var(--magenta)', marginLeft: 8 }}>{edges.length}</span> relations
              </div>
            </div>
          </div>

          {/* Full-page graph */}
          <GraphView
            nodes={nodes}
            edges={edges}
            onSelectEntity={setSelectedGraphEntity}
            selectedEntityUuid={selectedGraphEntity}
            searchHighlight={graphHighlight}
          />

          {/* Detail panel overlay */}
          {selectedGraphEntity && (
            <GraphDetailPanel
              hubId={id}
              uuid={selectedGraphEntity}
              onClose={() => setSelectedGraphEntity(null)}
              onNavigate={(uuid) => setSelectedGraphEntity(uuid)}
            />
          )}
        </div>
      )}

      {/* MAIN CONTENT — non-graph sections */}
      {section !== 'graph' && (
      <div className="hub-main">
        {/* HUB HEADER */}
        <div className="hd-header">
          <div className="hd-header-row">
            <div className="hd-header-info">
              <h1 className="hd-title">
                {hub.name}
                <span className={`status status-${hub.status}`}><span className="status-dot" />{hub.status}</span>
              </h1>
              {hub.description && <p className="hd-desc">{hub.description}</p>}
            </div>
            <div className="hd-header-stats">
              <div className="hd-stat">
                <div className="hd-stat-val" style={{ color: 'var(--cyan)' }}>{nodes.length || hub.entity_count}</div>
                <div className="hd-stat-lbl">Entities</div>
              </div>
              <div className="hd-stat">
                <div className="hd-stat-val" style={{ color: 'var(--magenta)' }}>{edges.length || hub.edge_count}</div>
                <div className="hd-stat-lbl">Relations</div>
              </div>
              <div className="hd-stat">
                <div className="hd-stat-val" style={{ color: 'var(--electric)' }}>{members.length}</div>
                <div className="hd-stat-lbl">Agents</div>
              </div>
            </div>
          </div>
        </div>

        {/* SECTION HEADER */}
        {SECTION_TITLES[section] && (
          <div className="hd-section-bar">
            <span className="hd-section-title">{SECTION_TITLES[section]}</span>
            {section === 'entities' && <span className="hd-section-count">{nodes.length}</span>}
            {section === 'relationships' && <span className="hd-section-count">{edges.length}</span>}
            {section === 'members' && <span className="hd-section-count">{members.length}</span>}
          </div>
        )}

        {/* CHAT */}
        {section === 'chat' && <ChatPanel hubId={id} hubName={hub.name} />}

        {/* EXPLORE */}

        {/* ENTITIES */}
        {section === 'entities' && (
          nodes.length === 0 ? (
            <div className="empty-state">
              <img src={mobAura} alt="" className="empty-img" />
              <div className="empty-state-title">{hub.status === 'seeding' ? 'Building graph...' : 'No entities yet'}</div>
            </div>
          ) : (
            <>
              <div className="card-list">
                {nodes.slice((entityPage - 1) * ENTITY_PAGE, entityPage * ENTITY_PAGE).map(n => {
                  const labels = (n.labels || []).filter(l => l !== 'Entity')
                  const entityType = labels.find(l => ['Person','Organization','Concept','Method','Tool','Event','Dataset','Location'].includes(l))
                  const otherLabels = labels.filter(l => l !== entityType)
                  const tc = TYPE_CONFIG[entityType] || DEFAULT_TYPE
                  const TypeIcon = tc.Icon
                  return (
                    <div key={n.uuid} className="ecard" onClick={() => setProfileUuid(n.uuid)}>
                      <div className="ecard-header">
                        <div className="ecard-icon" style={{ background: tc.bg, color: tc.color }}>
                          <TypeIcon size={18} strokeWidth={1.8} />
                        </div>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                          {entityType && <span className="ecard-badge" style={{ color: tc.color, background: tc.bg }}>{entityType}</span>}
                          {n.asset_count > 0 && (
                            <span className="ecard-badge" style={{ color: 'var(--green)', background: 'rgba(0,230,118,0.08)', fontSize: 8 }}>
                              PROFILED
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="ecard-name">{n.name}</div>
                      {otherLabels.length > 0 && (
                        <div className="ecard-labels">
                          {otherLabels.map((l, i) => <span key={l} className={`entity-label label-${i % 5}`}>{l}</span>)}
                        </div>
                      )}
                      {n.summary && <div className="ecard-summary">{n.summary.length > 120 ? n.summary.slice(0, 118) + '...' : n.summary}</div>}
                      <div className="ecard-footer">
                        <div className="ecard-meta">
                          {n.provenance_count > 0 && <span>{n.provenance_count} source{n.provenance_count !== 1 ? 's' : ''}</span>}
                          {n.asset_count > 0 && <span>{n.asset_count} asset{n.asset_count !== 1 ? 's' : ''}</span>}
                        </div>
                        {n.confidence != null && (
                          <div className="ecard-conf">
                            <div className="ecard-conf-bar">
                              <div className="ecard-conf-fill" style={{
                                width: `${Math.round(n.confidence * 100)}%`,
                                background: n.confidence >= 0.7 ? 'var(--green)' : n.confidence >= 0.4 ? 'var(--amber)' : 'var(--red)'
                              }} />
                            </div>
                            <span style={{ color: n.confidence >= 0.7 ? 'var(--green)' : n.confidence >= 0.4 ? 'var(--amber)' : 'var(--red)' }}>
                              {Math.round(n.confidence * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
              <Pagination totalItems={nodes.length} pageSize={ENTITY_PAGE} currentPage={entityPage} onPageChange={setEntityPage} />
            </>
          )
        )}

        {/* RELATIONSHIPS */}
        {section === 'relationships' && (
          edges.length === 0 ? (
            <div className="empty-state"><div className="empty-state-title">No relationships yet</div></div>
          ) : (
            <>
              <div className="card-list">
                {edges.slice((edgePage - 1) * EDGE_PAGE, edgePage * EDGE_PAGE).map(e => (
                  <div key={e.uuid} className="rel-card">
                    <div className="rel-label">
                      <ArrowLeftRight size={12} strokeWidth={2} />
                      <span>{e.name}</span>
                    </div>
                    <div className="rel-fact">{e.fact}</div>
                    <div className="rel-footer">
                      {e.valid_at && <span>{timeAgo(e.valid_at)}</span>}
                      {e.invalid_at && <span className="fact-superseded">superseded</span>}
                      <ConfidenceBar confidence={e.confidence} voteCount={e.vote_count} provenanceCount={e.provenance_count} />
                    </div>
                  </div>
                ))}
              </div>
              <Pagination totalItems={edges.length} pageSize={EDGE_PAGE} currentPage={edgePage} onPageChange={setEdgePage} />
            </>
          )
        )}

        {/* SOURCES */}

        {/* PLAYGROUND — wave visualization */}
        {section === 'playground' && <PlaygroundView hubId={id} />}

        {/* AGENTS — v3 Playground */}
        {section === 'agents' && <AgentPlayground hubId={id} />}

        {/* SKILLS */}

      </div>
      )}

      {/* ENTITY PROFILE SLIDER */}
      {profileUuid && (
        <>
          <div className="ep-overlay" onClick={() => setProfileUuid(null)} />
          <div className="ep-slider">
            <EntityProfile hubId={id} uuid={profileUuid}
              onClose={() => setProfileUuid(null)}
              onNavigate={(uuid) => setProfileUuid(uuid)} />
          </div>
        </>
      )}
    </div>
  )
}

function Sidebar({ section, setSection }) {
  return (
    <div className="hub-sidebar">
      {NAV_SECTIONS.map((item, idx) => {
        if (item.type === 'section') {
          return <div key={idx} className="hub-nav-section">{item.label}</div>
        }
        const { Icon } = item
        return (
          <div key={item.id} className={`hub-nav-item ${section === item.id ? 'active' : ''}`}
            onClick={() => setSection(item.id)}
            data-tooltip={item.label}>
            <span className="hub-nav-icon"><Icon size={18} strokeWidth={1.8} /></span>
            <span className="hub-nav-label">{item.label}</span>
          </div>
        )
      })}
    </div>
  )
}
