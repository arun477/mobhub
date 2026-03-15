import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'
import {
  Play, Pause, Square, RotateCcw, Send, ChevronDown, ChevronRight,
  Bot, Search, Brain, ShieldCheck, UserSearch, Trash2, Sparkles,
  Circle, Loader, AlertCircle, CheckCircle, GitBranch, Skull, Power
} from 'lucide-react'

const AGENT_ICONS = {
  scout: Search,
  analyst: Brain,
  verifier: ShieldCheck,
  profiler: UserSearch,
  curator: Trash2,
  synthesizer: Sparkles,
  person_profiler: UserSearch,
  org_profiler: UserSearch,
}

const AGENT_COLORS = {
  scout: 'var(--cyan)',
  analyst: 'var(--electric)',
  verifier: 'var(--green)',
  profiler: 'var(--amber)',
  curator: 'var(--magenta)',
  synthesizer: '#b388ff',
  person_profiler: 'var(--amber)',
  org_profiler: 'var(--amber)',
}

const STATUS_ICONS = {
  idle: Circle,
  working: Loader,
  paused: Pause,
  completed: CheckCircle,
  error: AlertCircle,
}

function AgentCard({ agent, onPause, onResume, onSelect, isSelected }) {
  const Icon = AGENT_ICONS[agent.agent_type] || Bot
  const color = AGENT_COLORS[agent.agent_type] || 'var(--text-3)'
  const StatusIcon = STATUS_ICONS[agent.status] || Circle
  const isWorking = agent.status === 'working'
  const hasActivity = agent.events_handled > 0
  const lastAction = agent.recent_actions?.[agent.recent_actions.length - 1]

  return (
    <div
      className={`pg-agent-card ${isSelected ? 'selected' : ''} ${isWorking ? 'working' : ''}`}
      onClick={() => onSelect(agent.id)}
    >
      <div className="pg-agent-icon" style={{ color, background: `${color}15` }}>
        <Icon size={18} strokeWidth={2} />
      </div>
      <div className="pg-agent-info">
        <div className="pg-agent-name">{agent.name}</div>
        {lastAction ? (
          <div className="pg-agent-last-action" title={lastAction.description}>
            {lastAction.action_type}: {lastAction.description.slice(0, 40)}{lastAction.description.length > 40 ? '...' : ''}
          </div>
        ) : (
          <div className="pg-agent-type">{agent.agent_type}</div>
        )}
      </div>
      <div className="pg-agent-right">
        <div className={`pg-agent-status status-${agent.status}`}>
          <StatusIcon size={12} className={isWorking ? 'pg-spin' : ''} />
          {agent.status}
        </div>
        <div className="pg-agent-stats">
          {hasActivity && <span className="pg-event-count">{agent.events_handled}</span>}
          {agent.errors > 0 && <span className="pg-errors">{agent.errors} err</span>}
        </div>
      </div>
      <div className="pg-agent-controls" onClick={e => e.stopPropagation()}>
        {agent.status === 'paused' ? (
          <button className="pg-ctrl-btn" onClick={() => onResume(agent.id)} title="Resume">
            <Play size={12} />
          </button>
        ) : (
          <button className="pg-ctrl-btn" onClick={() => onPause(agent.id)} title="Pause">
            <Pause size={12} />
          </button>
        )}
      </div>
    </div>
  )
}

function ActionEntry({ action }) {
  const color = AGENT_COLORS[action.agent_type] || 'var(--text-3)'
  const isFailed = action.status === 'failed'

  return (
    <div className={`pg-action ${isFailed ? 'failed' : ''}`}>
      <div className="pg-action-time">
        {new Date(action.timestamp).toLocaleTimeString('en-US', {
          hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
        })}
      </div>
      <div className="pg-action-dot" style={{ background: color }} />
      <div className="pg-action-body">
        <span className="pg-action-agent" style={{ color }}>{action.agent_name || action.agent_id?.slice(0, 8)}</span>
        <span className="pg-action-type">{action.action_type}</span>
        <span className="pg-action-desc">{action.description}</span>
      </div>
      {isFailed && <AlertCircle size={12} className="pg-action-err-icon" />}
    </div>
  )
}

function AgentDetail({ agent, onClose }) {
  const [expanded, setExpanded] = useState({ memory: false, actions: true })

  if (!agent) return null
  const color = AGENT_COLORS[agent.agent_type] || 'var(--text-3)'

  return (
    <div className="pg-detail">
      <div className="pg-detail-header">
        <div className="pg-detail-title" style={{ color }}>{agent.name}</div>
        <button className="pg-detail-close" onClick={onClose}>&times;</button>
      </div>

      <div className="pg-detail-section">
        <div className="pg-detail-label">Personality</div>
        <div className="pg-detail-text">{agent.personality?.approach || 'default'}</div>
        {agent.personality?.expertise?.length > 0 && (
          <div className="pg-detail-tags">
            {agent.personality.expertise.map(e => (
              <span key={e} className="pg-tag">{e}</span>
            ))}
          </div>
        )}
      </div>

      <div className="pg-detail-section">
        <div className="pg-detail-label">Stats</div>
        <div className="pg-detail-grid">
          <div className="pg-stat"><span className="pg-stat-val">{agent.events_handled}</span><span className="pg-stat-lbl">Events</span></div>
          <div className="pg-stat"><span className="pg-stat-val">{agent.errors}</span><span className="pg-stat-lbl">Errors</span></div>
          <div className="pg-stat"><span className="pg-stat-val">{agent.status}</span><span className="pg-stat-lbl">Status</span></div>
          <div className="pg-stat"><span className="pg-stat-val">{agent.last_active ? timeAgo(agent.last_active) : 'never'}</span><span className="pg-stat-lbl">Last Active</span></div>
        </div>
      </div>

      {agent.parent_agent_id && (
        <div className="pg-detail-section">
          <div className="pg-detail-label">Sub-Agent</div>
          <div className="pg-detail-text" style={{ fontSize: 12 }}>
            <GitBranch size={12} style={{ marginRight: 4 }} />
            Spawned by {agent.parent_agent_id.slice(0, 8)}...
          </div>
        </div>
      )}

      {agent.memory_keys?.length > 0 && (
        <div className="pg-detail-section">
          <div className="pg-detail-label pg-clickable" onClick={() => setExpanded(e => ({ ...e, memory: !e.memory }))}>
            {expanded.memory ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Memory ({agent.memory_keys.length} keys)
          </div>
          {expanded.memory && (
            <div className="pg-detail-tags">
              {agent.memory_keys.map(k => <span key={k} className="pg-tag">{k}</span>)}
            </div>
          )}
        </div>
      )}

      {agent.recent_actions?.length > 0 && (
        <div className="pg-detail-section">
          <div className="pg-detail-label pg-clickable" onClick={() => setExpanded(e => ({ ...e, actions: !e.actions }))}>
            {expanded.actions ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Recent Actions ({agent.recent_actions.length})
          </div>
          {expanded.actions && (
            <div className="pg-detail-actions">
              {agent.recent_actions.map(a => (
                <div key={a.id} className={`pg-mini-action ${a.status === 'failed' ? 'failed' : ''}`}>
                  <span className="pg-mini-type">{a.action_type}</span>
                  <span className="pg-mini-desc">{a.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AgentPlayground({ hubId }) {
  const [agents, setAgents] = useState([])
  const [actions, setActions] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [instruction, setInstruction] = useState('')
  const [sending, setSending] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const logRef = useRef(null)
  const wsRef = useRef(null)

  // Load agents and actions
  const loadAgents = useCallback(async () => {
    try {
      const data = await api.getHubAgents(hubId)
      setAgents(data.agents || [])
    } catch { /* engine might not be running */ }
  }, [hubId])

  const loadActions = useCallback(async () => {
    try {
      const data = await api.getHubActions(hubId, 100)
      setActions(data.actions || [])
    } catch {}
  }, [hubId])

  // WebSocket connection
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${proto}://${window.location.host}/api/engine/hubs/${hubId}/ws`

    let ws
    let retryTimeout

    function connect() {
      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setWsConnected(true)
      }

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'init') {
            setAgents(msg.agents || [])
          } else if (msg.type === 'agent_action') {
            setActions(prev => [...prev.slice(-199), msg.action])
            // Refresh agents to get updated status
            loadAgents()
          }
        } catch {}
      }

      ws.onclose = () => {
        setWsConnected(false)
        retryTimeout = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        setWsConnected(false)
      }
    }

    connect()

    return () => {
      clearTimeout(retryTimeout)
      if (ws) ws.close()
    }
  }, [hubId, loadAgents])

  // Initial load + polling fallback
  useEffect(() => {
    loadAgents()
    loadActions()
    const iv = setInterval(() => {
      if (!wsConnected) {
        loadAgents()
        loadActions()
      }
    }, 5000)
    return () => clearInterval(iv)
  }, [loadAgents, loadActions, wsConnected])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [actions])

  const handlePause = async (agentId) => {
    try { await api.pauseAgent(agentId); loadAgents() } catch {}
  }
  const handleResume = async (agentId) => {
    try { await api.resumeAgent(agentId); loadAgents() } catch {}
  }
  const handleResumeAll = async () => {
    try { await api.resumeHub(hubId); loadAgents() } catch {}
  }
  const handleStopAll = async () => {
    try { await api.stopHub(hubId); loadAgents() } catch {}
  }
  const handleKillAll = async () => {
    if (!confirm('Kill all agents? They will be fully removed and you will need to respawn them.')) return
    try { await api.killHub(hubId); loadAgents() } catch {}
  }
  const handleRespawn = async () => {
    try { await api.spawnHubAgents(hubId, '', ''); loadAgents() } catch {}
  }
  const handleInstruct = async () => {
    if (!instruction.trim()) return
    setSending(true)
    try {
      await api.instructHub(hubId, instruction, selectedId)
      setInstruction('')
    } catch {}
    setSending(false)
  }

  const selectedAgent = agents.find(a => a.id === selectedId)
  const mainAgents = agents.filter(a => !a.parent_agent_id)
  const subAgents = agents.filter(a => a.parent_agent_id)

  // Enrich actions with agent name from our agent list
  const agentMap = Object.fromEntries(agents.map(a => [a.id, a]))
  const enrichedActions = actions.map(a => ({
    ...a,
    agent_name: a.agent_name || agentMap[a.agent_id]?.name || a.agent_id?.slice(0, 8),
    agent_type: agentMap[a.agent_id]?.agent_type || '',
  }))

  return (
    <div className="pg-layout">
      {/* LEFT: Agent grid */}
      <div className="pg-agents-panel">
        <div className="pg-panel-header">
          <div className="pg-panel-title">Agent Team</div>
          <div className="pg-header-controls">
            <div className={`pg-ws-indicator ${wsConnected ? 'connected' : ''}`}>
              <Circle size={6} fill="currentColor" />
              {wsConnected ? 'Live' : 'Polling'}
            </div>
          </div>
        </div>
        <div className="pg-controls-bar">
          <button className="pg-action-btn pg-btn-start" onClick={handleResumeAll} title="Start all agents">
            <Play size={13} /> Start
          </button>
          <button className="pg-action-btn pg-btn-stop" onClick={handleStopAll} title="Stop all agents">
            <Square size={13} /> Stop
          </button>
          <button className="pg-action-btn pg-btn-kill" onClick={handleKillAll} title="Kill & remove all agents">
            <Skull size={13} /> Kill
          </button>
          {agents.length === 0 && (
            <button className="pg-action-btn pg-btn-respawn" onClick={handleRespawn} title="Respawn agent team">
              <RotateCcw size={13} /> Respawn
            </button>
          )}
        </div>

        <div className="pg-agent-list">
          {mainAgents.map(a => (
            <AgentCard
              key={a.id} agent={a}
              onPause={handlePause} onResume={handleResume}
              onSelect={setSelectedId} isSelected={selectedId === a.id}
            />
          ))}
        </div>

        {subAgents.length > 0 && (
          <>
            <div className="pg-sub-header">
              <GitBranch size={12} /> Sub-Agents ({subAgents.length})
            </div>
            <div className="pg-sub-list">
              {subAgents.map(a => {
                const Icon = AGENT_ICONS[a.agent_type] || Bot
                const color = AGENT_COLORS[a.agent_type] || 'var(--text-3)'
                const StatusIcon = STATUS_ICONS[a.status] || Circle
                const isWorking = a.status === 'working'
                const isDone = a.status === 'completed'
                // Extract target name from agent name like "PersonProfiler(Karan Malhotra)"
                const targetMatch = a.name.match(/\((.+)\)/)
                const targetName = targetMatch ? targetMatch[1] : a.name

                return (
                  <div key={a.id}
                    className={`pg-sub-card ${selectedId === a.id ? 'selected' : ''} ${isDone ? 'done' : ''}`}
                    onClick={() => setSelectedId(a.id)}
                  >
                    <div className="pg-sub-connector" />
                    <div className="pg-sub-icon" style={{ color, background: `${color}15` }}>
                      <Icon size={14} />
                    </div>
                    <div className="pg-sub-info">
                      <div className="pg-sub-target">{targetName}</div>
                      <div className="pg-sub-type">
                        {a.agent_type === 'person_profiler' ? 'Person' : a.agent_type === 'org_profiler' ? 'Organization' : a.agent_type}
                      </div>
                    </div>
                    <div className={`pg-agent-status status-${a.status}`}>
                      <StatusIcon size={10} className={isWorking ? 'pg-spin' : ''} />
                      {a.status}
                    </div>
                    {a.events_handled > 0 && <span className="pg-event-count">{a.events_handled}</span>}
                  </div>
                )
              })}
            </div>
          </>
        )}

        {agents.length === 0 && (
          <div className="pg-empty">
            <Bot size={32} strokeWidth={1} />
            <div>No agents spawned yet</div>
            <div className="pg-empty-sub">Agents are created automatically when the hub is built</div>
          </div>
        )}

        {/* Instruction input */}
        <div className="pg-instruct">
          <input
            className="pg-instruct-input"
            placeholder="Direct agents... (e.g. 'focus on investors')"
            value={instruction}
            onChange={e => setInstruction(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleInstruct()}
            disabled={sending}
          />
          <button className="pg-instruct-btn" onClick={handleInstruct} disabled={sending || !instruction.trim()}>
            <Send size={14} />
          </button>
        </div>
      </div>

      {/* MIDDLE: Live log */}
      <div className="pg-log-panel">
        <div className="pg-panel-header">
          <div className="pg-panel-title">Live Log</div>
          <div className="pg-log-count">{actions.length} actions</div>
        </div>
        <div className="pg-log-body" ref={logRef}>
          {enrichedActions.length === 0 ? (
            <div className="pg-log-empty">Waiting for agent activity...</div>
          ) : (
            enrichedActions.map((a, i) => <ActionEntry key={a.id || i} action={a} />)
          )}
        </div>
      </div>

      {/* RIGHT: Agent detail (conditional) */}
      {selectedAgent && (
        <AgentDetail
          agent={selectedAgent}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  )
}
