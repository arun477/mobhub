import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api'
import { timeAgo } from '../utils'
import { Send, Plus, Trash2, MessageSquare, User } from 'lucide-react'
import dimpleImg from '../assets/dimple.png'

const SUGGESTIONS = [
  'What are the key entities in this hub?',
  'Summarize the main topics covered',
  'What connections exist between the top entities?',
  'What are the most recent findings?',
]

function renderMarkdown(text) {
  if (!text) return text
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

export default function ChatPanel({ hubId, hubName }) {
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    api.listChatSessions(hubId).then(d => { setSessions(d || []); setSessionsLoading(false) }).catch(() => setSessionsLoading(false))
  }, [hubId])

  useEffect(() => {
    if (!activeSession) { setMessages([]); return }
    api.getChatSession(hubId, activeSession).then(d => setMessages(d?.messages || [])).catch(() => {})
  }, [hubId, activeSession])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const autoResize = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }, [])

  const handleNewSession = async () => {
    const s = await api.createChatSession(hubId)
    setSessions(prev => [{ ...s, message_count: 0 }, ...prev])
    setActiveSession(s.id)
    setMessages([])
    textareaRef.current?.focus()
  }

  const handleSend = async (text) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    let sid = activeSession
    if (!sid) {
      const s = await api.createChatSession(hubId)
      setSessions(prev => [{ ...s, message_count: 0 }, ...prev])
      sid = s.id
      setActiveSession(sid)
    }

    const tempId = Date.now()
    setMessages(prev => [...prev, { id: tempId, role: 'user', content: msg, created_at: new Date().toISOString() }])
    setLoading(true)

    try {
      const resp = await api.sendChatMessage(hubId, sid, msg)
      setMessages(prev => [...prev.filter(m => m.id !== tempId), resp.user_message, resp.assistant_message])
      if (resp.session_title) {
        setSessions(prev => prev.map(s => s.id === sid ? { ...s, title: resp.session_title } : s))
      }
    } catch (e) {
      setMessages(prev => [...prev, { id: tempId + 1, role: 'assistant', content: `Error: ${e.message}`, created_at: new Date().toISOString() }])
    }
    setLoading(false)
  }

  const handleDelete = async (e, sid) => {
    e.stopPropagation()
    await api.deleteChatSession(hubId, sid).catch(() => {})
    setSessions(prev => prev.filter(s => s.id !== sid))
    if (activeSession === sid) { setActiveSession(null); setMessages([]) }
  }

  return (
    <div className="chat-layout">
      {/* Session sidebar */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <span className="chat-sidebar-label">Conversations</span>
          <button className="chat-new-btn" onClick={handleNewSession}>
            <Plus size={14} /> New
          </button>
        </div>
        <div className="chat-session-list">
          {sessionsLoading ? (
            <div className="chat-sidebar-empty">Loading...</div>
          ) : sessions.length === 0 ? (
            <div className="chat-sidebar-empty">
              <MessageSquare size={20} strokeWidth={1.5} />
              <span>No conversations yet</span>
            </div>
          ) : sessions.map(s => (
            <div key={s.id} className={`chat-session-item ${activeSession === s.id ? 'active' : ''}`} onClick={() => setActiveSession(s.id)}>
              <div className="chat-session-title">{s.title}</div>
              <div className="chat-session-meta">
                <span>{s.message_count} msgs</span>
                <span>{timeAgo(s.updated_at || s.created_at)}</span>
              </div>
              <button className="chat-session-delete" onClick={e => handleDelete(e, s.id)}>
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="chat-main">
        <div className="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="chat-empty">
              <div className="chat-empty-icon">
                <img src={dimpleImg} alt="MobHub" className="chat-empty-dimple" />
              </div>
              <div className="chat-empty-title">
                {hubName ? `Ask Dimple about ${hubName}` : 'Ask anything about this knowledge graph'}
              </div>
              <div className="chat-empty-desc">Grounded in the hub's entities and relationships</div>
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} className="chat-suggestion" onClick={() => handleSend(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={m.id || i} className={`chat-row ${m.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}>
              <div className={`chat-avatar ${m.role === 'user' ? 'chat-avatar-user' : 'chat-avatar-bot'}`}>
                {m.role === 'user' ? <User size={14} /> : <img src={dimpleImg} alt="MobHub" className="chat-avatar-img" />}
              </div>
              <div className={`chat-bubble ${m.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>
                <div className="chat-bubble-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
                {m.citations?.entities?.length > 0 && (
                  <div className="chat-bubble-citations">
                    {m.citations.entities.map((e, j) => <span key={j} className="chat-citation">{e.name}</span>)}
                  </div>
                )}
                <div className="chat-bubble-meta">{m.role === 'user' ? 'You' : 'Dimple'} &middot; {timeAgo(m.created_at)}</div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-row chat-row-assistant">
              <div className="chat-avatar chat-avatar-bot"><img src={dimpleImg} alt="MobHub" className="chat-avatar-img" /></div>
              <div className="chat-thinking">
                <span className="chat-thinking-dot" />
                <span className="chat-thinking-dot" />
                <span className="chat-thinking-dot" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-bar">
          <div className="chat-input-wrap">
            <textarea ref={textareaRef} className="chat-input"
              placeholder="Ask about entities, relationships, or insights..."
              value={input}
              onChange={e => { setInput(e.target.value); autoResize() }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              disabled={loading}
              rows={1} />
            <button className="chat-send-btn" onClick={() => handleSend()} disabled={loading || !input.trim()}>
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
