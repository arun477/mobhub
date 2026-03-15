export default function Skeleton({ type = 'card', count = 3 }) {
  const items = Array.from({ length: count })

  if (type === 'graph') return <div className="skeleton skeleton-graph" />

  if (type === 'card') return items.map((_, i) => <div key={i} className="skeleton skeleton-card" />)

  if (type === 'list') return items.map((_, i) => <div key={i} className="skeleton skeleton-list" />)

  if (type === 'feed') return items.map((_, i) => <div key={i} className="skeleton skeleton-feed" />)

  return null
}
