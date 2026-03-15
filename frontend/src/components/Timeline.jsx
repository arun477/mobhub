import { useState, useEffect } from 'react'
import { api } from '../api'

function dotClass(sourceType) {
  if (sourceType?.includes('seed') || sourceType?.includes('paper')) return 'timeline-dot seed'
  if (sourceType?.includes('episode') || sourceType?.includes('source')) return 'timeline-dot episode'
  return 'timeline-dot edit'
}

export default function Timeline({ hubId }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getTimeline(hubId).then(d => { setData(d || []); setLoading(false) }).catch(() => setLoading(false))
  }, [hubId])

  if (loading) return <div className="empty">Loading timeline...</div>
  if (data.length === 0) return <div className="empty">No provenance data yet.</div>

  return (
    <div>
      {data.map(day => (
        <div key={day.date} className="timeline-day">
          <div className="timeline-date-row">
            <div className="timeline-date">{day.date}</div>
            <div className="timeline-date-stats">
              <span style={{ color: 'var(--cyan)' }}>+{day.entity_count} entities</span>
              <span style={{ color: 'var(--magenta)' }}>+{day.edge_count} relations</span>
            </div>
            <div className="timeline-line" />
          </div>

          <div className="timeline-events">
            {day.events.slice(0, 20).map((e, i) => (
              <div key={i} className="timeline-event">
                <div className={dotClass(e.source_type)} />
                <div className="timeline-event-header">
                  <span className={`badge ${e.source_type?.includes('seed') ? 'badge-cyan' : e.source_type?.includes('episode') ? 'badge-green' : 'badge-amber'}`}>
                    {(e.source_type || '').replace(/_/g, ' ')}
                  </span>
                  {e.agent_name && <span className="badge badge-cyan">{e.agent_name}</span>}
                  <span style={{ color: 'var(--text-3)', fontFamily: 'var(--mono)', fontSize: 10 }}>
                    {e.node_uuid ? 'entity' : 'relation'}
                  </span>
                </div>
                {e.episode_name && <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{e.episode_name}</div>}
              </div>
            ))}
            {day.events.length > 20 && <div style={{ fontSize: 11, color: 'var(--text-3)', paddingLeft: 20 }}>+{day.events.length - 20} more</div>}
          </div>
        </div>
      ))}
    </div>
  )
}
