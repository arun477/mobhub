import { useState, useRef, useMemo, useEffect } from 'react'
import { Search, X } from 'lucide-react'

const TYPE_COLORS = {
  Person: '#00e5ff', Organization: '#ff2d78', Concept: '#5b5bff', Method: '#00e676',
  Tool: '#ffab00', Event: '#ff3d3d', Dataset: '#84cc16', Location: '#ec4899',
}

function getEntityType(labels) {
  return (labels || []).find(l => TYPE_COLORS[l] && l !== 'Entity') || 'Entity'
}

export default function GraphSearch({ nodes, onSelect, onHighlight }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState(0)
  const inputRef = useRef()
  const listRef = useRef()

  // Fuzzy match — case insensitive, supports partial
  const results = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase()
    return nodes
      .filter(n => n.name.toLowerCase().includes(q))
      .sort((a, b) => {
        // Exact start match first
        const aStarts = a.name.toLowerCase().startsWith(q) ? 0 : 1
        const bStarts = b.name.toLowerCase().startsWith(q) ? 0 : 1
        if (aStarts !== bStarts) return aStarts - bStarts
        // Then by edge count (more connected = more important)
        const aEc = a.edge_count || a._ec || 0
        const bEc = b.edge_count || b._ec || 0
        return bEc - aEc
      })
      .slice(0, 12)
  }, [query, nodes])

  // Highlight matching nodes on graph
  useEffect(() => {
    if (results.length > 0) {
      onHighlight?.(results.map(r => r.uuid))
    } else {
      onHighlight?.(null)
    }
  }, [results, onHighlight])

  // Reset selection when results change
  useEffect(() => { setSelectedIdx(0) }, [results.length])

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const item = listRef.current.children[selectedIdx]
      item?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIdx])

  const handleSelect = (node) => {
    onSelect?.(node.uuid)
    setQuery('')
    setOpen(false)
    onHighlight?.(null)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && results[selectedIdx]) {
      e.preventDefault()
      handleSelect(results[selectedIdx])
    } else if (e.key === 'Escape') {
      setQuery('')
      setOpen(false)
      onHighlight?.(null)
      inputRef.current?.blur()
    }
  }

  const handleClear = () => {
    setQuery('')
    setOpen(false)
    onHighlight?.(null)
    inputRef.current?.focus()
  }

  return (
    <div className="gsearch">
      <div className="gsearch-input-wrap">
        <Search size={14} className="gsearch-icon" />
        <input
          ref={inputRef}
          className="gsearch-input"
          type="text"
          placeholder="Search entities..."
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => query && setOpen(true)}
          onKeyDown={handleKeyDown}
        />
        {query && (
          <>
            <span className="gsearch-count">{results.length}</span>
            <button className="gsearch-clear" onClick={handleClear}><X size={12} /></button>
          </>
        )}
      </div>

      {/* Dropdown results */}
      {open && results.length > 0 && (
        <div className="gsearch-dropdown" ref={listRef}>
          {results.map((n, i) => {
            const type = getEntityType(n.labels)
            const color = TYPE_COLORS[type] || '#8888aa'
            const ec = n.edge_count || n._ec || 0
            // Highlight matching text
            const idx = n.name.toLowerCase().indexOf(query.toLowerCase())
            const before = n.name.slice(0, idx)
            const match = n.name.slice(idx, idx + query.length)
            const after = n.name.slice(idx + query.length)

            return (
              <div
                key={n.uuid}
                className={`gsearch-item ${i === selectedIdx ? 'gsearch-item-active' : ''}`}
                onClick={() => handleSelect(n)}
                onMouseEnter={() => setSelectedIdx(i)}
              >
                <span className="gsearch-item-dot" style={{ background: color }} />
                <div className="gsearch-item-info">
                  <div className="gsearch-item-name">
                    {before}<mark>{match}</mark>{after}
                  </div>
                  <div className="gsearch-item-meta">
                    <span style={{ color }}>{type === 'Entity' ? 'General' : type}</span>
                    {ec > 0 && <span>{ec} links</span>}
                    {n.confidence != null && <span>{Math.round(n.confidence * 100)}%</span>}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* No results message */}
      {open && query.length >= 2 && results.length === 0 && (
        <div className="gsearch-dropdown">
          <div className="gsearch-empty">No matching entities</div>
        </div>
      )}
    </div>
  )
}
