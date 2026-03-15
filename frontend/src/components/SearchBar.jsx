import { useRef, useCallback } from 'react'

export default function SearchBar({ value, onChange, onSearch, placeholder = 'Search...', resultCount, loading }) {
  const timerRef = useRef(null)

  const handleChange = useCallback((e) => {
    const v = e.target.value
    onChange(v)

    if (onSearch) {
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => onSearch(v), 300)
    }
  }, [onChange, onSearch])

  const handleClear = () => {
    onChange('')
    if (onSearch) onSearch('')
  }

  return (
    <div className="search-bar">
      <input
        className="search-bar-input"
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={handleChange}
        onKeyDown={e => e.key === 'Enter' && onSearch && onSearch(value)}
      />

      {resultCount !== undefined && !loading && value && (
        <span className="search-bar-count">{resultCount}</span>
      )}

      {loading ? (
        <div className="search-bar-spinner" />
      ) : value ? (
        <button className="search-bar-clear" onClick={handleClear}>
          &times;
        </button>
      ) : null}
    </div>
  )
}
