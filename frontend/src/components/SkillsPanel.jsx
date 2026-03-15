import { useState, useEffect } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'
import { Search, Globe, BookOpen, Link, FileText, Settings, Microscope, Play, X, Clock, CheckCircle2, XCircle, Plus } from 'lucide-react'

const SKILL_META = {
  web_search:    { Icon: Search, color: '#00e5ff', bg: 'rgba(0,229,255,0.08)', label: 'Search' },
  browser:       { Icon: Globe, color: '#5b5bff', bg: 'rgba(91,91,255,0.08)', label: 'Browser' },
  paper_search:  { Icon: BookOpen, color: '#00e676', bg: 'rgba(0,230,118,0.08)', label: 'Academic' },
  url_ingest:    { Icon: Link, color: '#ffab00', bg: 'rgba(255,171,0,0.08)', label: 'Ingest' },
  text_analysis: { Icon: FileText, color: '#ff2d78', bg: 'rgba(255,45,120,0.08)', label: 'Analysis' },
  deep_research: { Icon: Microscope, color: '#00e5ff', bg: 'rgba(0,229,255,0.08)', label: 'Research' },
}
const DEFAULT_META = { Icon: Settings, color: '#666', bg: 'rgba(255,255,255,0.04)', label: 'Skill' }

export default function SkillsPanel({ hubId }) {
  const [data, setData] = useState({ installed: [], available: [] })
  const [executions, setExecutions] = useState([])
  const [loading, setLoading] = useState(true)
  const [testSkill, setTestSkill] = useState(null)
  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)

  const load = () => {
    api.listSkills(hubId).then(d => { setData(d || { installed: [], available: [] }); setLoading(false) }).catch(() => setLoading(false))
    api.listSkillExecutions(hubId).then(d => setExecutions(d || [])).catch(() => {})
  }
  useEffect(() => { load() }, [hubId])

  const handleToggle = async (skillId, enabled) => { await api.updateSkill(hubId, skillId, { enabled: !enabled }); load() }
  const handleAdd = async (type) => { await api.addSkill(hubId, type); load() }
  const handleTest = async () => {
    if (!testSkill || !testInput.trim()) return
    setTesting(true); setTestResult(null)
    try {
      let input; try { input = JSON.parse(testInput) } catch { input = { query: testInput } }
      setTestResult(await api.executeSkill(hubId, testSkill.id, input))
    } catch (e) { setTestResult({ error: e.message }) }
    setTesting(false); load()
  }

  if (loading) return <div className="empty">Loading skills...</div>

  const getMeta = (type) => SKILL_META[type] || DEFAULT_META

  return (
    <div className="sk-panel">
      {/* Installed skills */}
      <div className="sk-grid">
        {data.installed.map(s => {
          const m = getMeta(s.skill_type)
          const IconComp = m.Icon
          return (
            <div key={s.id} className={`sk-card ${!s.enabled ? 'sk-disabled' : ''}`}>
              <div className="sk-card-header">
                <div className="sk-card-icon" style={{ background: m.bg, color: m.color }}>
                  <IconComp size={20} strokeWidth={1.8} />
                </div>
                <div className="sk-card-toggle-wrap">
                  <button className={`sk-toggle ${s.enabled ? 'on' : 'off'}`} onClick={() => handleToggle(s.id, s.enabled)}>
                    <span className="sk-toggle-dot" />
                  </button>
                </div>
              </div>
              <div className="sk-card-name">{s.name}</div>
              <div className="sk-card-desc">{s.description}</div>
              <div className="sk-card-footer">
                <span className="sk-card-type">{m.label}</span>
                <button className="sk-test-btn" onClick={() => { setTestSkill(s); setTestInput(''); setTestResult(null) }}>
                  <Play size={11} /> Test
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Test panel */}
      {testSkill && (
        <div className="sk-test-panel">
          <div className="sk-test-header">
            <span className="sk-test-title">
              <Play size={13} /> Test: {testSkill.name}
            </span>
            <button className="sk-test-close" onClick={() => setTestSkill(null)}><X size={14} /></button>
          </div>
          <div className="sk-test-input-row">
            <input className="input" placeholder='{"query": "..."} or plain text' value={testInput}
              onChange={e => setTestInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleTest()} autoFocus />
            <button className="btn btn-primary btn-sm" onClick={handleTest} disabled={testing}>
              {testing ? <span className="spinner" /> : 'Run'}
            </button>
          </div>
          {testResult && <pre className="sk-test-result">{JSON.stringify(testResult, null, 2)}</pre>}
        </div>
      )}

      {/* Available skills */}
      {data.available.length > 0 && (
        <div className="sk-section">
          <div className="sk-section-title">Available Skills</div>
          <div className="sk-grid">
            {data.available.map(s => {
              const m = getMeta(s.skill_type)
              const IconComp = m.Icon
              return (
                <div key={s.skill_type} className="sk-card sk-card-available">
                  <div className="sk-card-header">
                    <div className="sk-card-icon" style={{ background: m.bg, color: m.color }}>
                      <IconComp size={20} strokeWidth={1.8} />
                    </div>
                  </div>
                  <div className="sk-card-name">{s.name}</div>
                  <div className="sk-card-desc">{s.description}</div>
                  <div className="sk-card-footer">
                    <span className="sk-card-type">{m.label}</span>
                    <button className="sk-add-btn" onClick={() => handleAdd(s.skill_type)}>
                      <Plus size={12} /> Add
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Recent executions */}
      {executions.length > 0 && (
        <div className="sk-section">
          <div className="sk-section-title">Recent Executions</div>
          <div className="sk-exec-list">
            {executions.slice(0, 10).map(e => {
              const m = getMeta(e.skill_type)
              return (
                <div key={e.id} className="sk-exec">
                  <div className="sk-exec-left">
                    <span className="sk-exec-status">
                      {e.status === 'completed' ? <CheckCircle2 size={13} color="var(--green)" /> : <XCircle size={13} color="var(--red)" />}
                    </span>
                    <span className="sk-exec-name">{e.skill_name}</span>
                    {e.agent_name && <span className="badge badge-cyan">{e.agent_name}</span>}
                  </div>
                  <div className="sk-exec-right">
                    {e.duration_ms != null && <span className="sk-exec-duration">{e.duration_ms}ms</span>}
                    <span className="sk-exec-time"><Clock size={10} /> {timeAgo(e.created_at)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
