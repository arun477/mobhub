import { useState } from 'react'
import { api } from '../api'

export default function QAPanel({ hubId }) {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState([])

  const handleAsk = async () => {
    if (!question.trim() || loading) return
    setLoading(true)
    try {
      const r = await api.askQuestion(hubId, question.trim())
      setResult(r)
      setHistory(prev => [{ q: question.trim(), a: r.answer, citations: r.citations }, ...prev].slice(0, 10))
    } catch (e) {
      setResult({ answer: 'Failed to get answer. Make sure OpenAI API key is configured.', citations: {} })
    }
    setLoading(false)
  }

  return (
    <div>
      {/* Input */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          style={{
            flex: 1, padding: '12px 16px', fontSize: 14,
            border: '1px solid var(--glass-border)', borderRadius: 12,
            background: 'var(--surface)', color: 'var(--text)', outline: 'none',
          }}
          placeholder="Ask a question about this knowledge graph..."
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAsk()}
        />
        <button className="btn btn-primary" onClick={handleAsk} disabled={loading}>
          {loading ? 'Thinking...' : 'Ask'}
        </button>
      </div>

      {/* Current answer */}
      {result && (
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--glass-border)',
          borderRadius: 16, padding: 24, marginBottom: 20,
        }}>
          <div style={{ fontSize: 13, color: 'var(--cyan)', fontFamily: 'var(--mono)', fontWeight: 700, marginBottom: 12 }}>
            {result.question}
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
            {result.answer}
          </div>

          {/* Citations */}
          {result.citations && (result.citations.entities?.length > 0 || result.citations.facts?.length > 0) && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
              <div style={{ fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
                Sources ({result.context_entities} entities, {result.context_facts} facts)
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(result.citations.entities || []).map((e, i) => (
                  <span key={i} style={{
                    fontSize: 11, fontFamily: 'var(--mono)', fontWeight: 600,
                    padding: '3px 8px', borderRadius: 6,
                    color: 'var(--cyan)', background: 'rgba(0,229,255,0.06)',
                  }}>{e.name}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* History */}
      {history.length > 1 && (
        <div>
          <div style={{ fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
            Previous Questions
          </div>
          {history.slice(1).map((h, i) => (
            <div key={i} style={{
              padding: '12px 16px', marginBottom: 6,
              background: 'var(--surface)', border: '1px solid var(--glass-border)', borderRadius: 12,
              cursor: 'pointer',
            }} onClick={() => { setQuestion(h.q); setResult({ question: h.q, answer: h.a, citations: h.citations }) }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 2 }}>{h.q}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {h.a.slice(0, 100)}...
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
