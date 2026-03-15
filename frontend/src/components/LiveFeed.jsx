function formatTime(ts) {
  return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function LiveFeed({ entries, title, maxItems = 30 }) {
  return (
    <div className="feed-panel">
      <div className="feed-header">
        <span className="feed-dot" />
        {title || 'Live'}
      </div>
      <div className="feed-body">
        {(!entries || entries.length === 0) ? (
          <div className="feed-empty">Awaiting psychic activity...</div>
        ) : entries.slice(0, maxItems).map(e => (
          <div key={e.id} className={`feed-entry action-${e.action}`}>
            <div className="feed-time">{formatTime(e.created_at)}</div>
            <div>
              <span className="feed-agent">{e.agent_name || 'system'}</span>{' '}
              <span className="feed-action">{e.detail || e.action}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
