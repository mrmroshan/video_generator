import { useState, useRef, useEffect } from 'react'

export default function BrollPicker({ scene, jobId, onPicked, onClose }) {
  const [query, setQuery]       = useState(scene.broll_prompt || '')
  const [results, setResults]   = useState([])
  const [loading, setLoading]   = useState(false)
  const [picking, setPicking]   = useState(null)   // video_id being downloaded
  const [error, setError]       = useState(null)
  const [hoveredId, setHovered] = useState(null)
  const inputRef = useRef(null)

  // Auto-search on open with existing prompt
  useEffect(() => {
    inputRef.current?.focus()
    if (query.trim()) search(query)
  }, [])

  const search = async (q) => {
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `/api/jobs/${jobId}/scenes/${scene.scene_id}/search-broll?q=${encodeURIComponent(q)}&limit=6`
      )
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResults(data.results)
      if (!data.results.length) setError('No results — try a different search term')
    } catch (e) {
      setError('Search failed: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const pick = async (result) => {
    setPicking(result.video_id)
    try {
      const res = await fetch(`/api/jobs/${jobId}/scenes/${scene.scene_id}/pick-broll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          download_url: result.download_url,
          video_id:     result.video_id,
          photographer: result.photographer,
          pexels_url:   result.pexels_url,
          width:        result.width,
          height:       result.height,
          duration:     result.duration,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const updatedJob = await res.json()
      onPicked(updatedJob)
    } catch (e) {
      setError('Download failed: ' + e.message)
      setPicking(null)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') search(query)
    if (e.key === 'Escape') onClose()
  }

  return (
    <div className="picker-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="picker-modal">

        {/* Header */}
        <div className="picker-header">
          <div className="picker-title">
            <span>🔍 Replace B-roll</span>
            <span className="picker-scene-id">{scene.scene_id}</span>
          </div>
          <button className="picker-close" onClick={onClose}>✕</button>
        </div>

        {/* Search bar */}
        <div className="picker-search">
          <input
            ref={inputRef}
            className="picker-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search Pexels videos…"
          />
          <button
            className="picker-search-btn"
            onClick={() => search(query)}
            disabled={loading}
          >
            {loading ? '⏳' : '🔍 Search'}
          </button>
        </div>

        {/* Hint */}
        <div className="picker-hint">
          Current prompt: <em>"{scene.broll_prompt}"</em>
        </div>

        {/* Error */}
        {error && <div className="picker-error">{error}</div>}

        {/* Results grid */}
        {results.length > 0 && (
          <div className="picker-grid">
            {results.map(r => {
              const isHovered  = hoveredId === r.video_id
              const isPicking  = picking  === r.video_id
              const otherBusy  = picking !== null && picking !== r.video_id
              return (
                <div
                  key={r.video_id}
                  className={[
                    'picker-result',
                    isPicking ? 'picker-result--picking' : '',
                    otherBusy ? 'picker-result--dimmed'  : '',
                  ].join(' ')}
                  onMouseEnter={() => setHovered(r.video_id)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => !picking && pick(r)}
                >
                  {/* Video preview on hover, thumbnail by default */}
                  {isHovered ? (
                    <video
                      className="picker-preview-video"
                      src={r.preview_url}
                      autoPlay muted loop playsInline
                    />
                  ) : (
                    <img
                      className="picker-preview-img"
                      src={r.image}
                      alt={r.photographer}
                      loading="lazy"
                    />
                  )}

                  {/* Overlay info */}
                  <div className="picker-result-overlay">
                    <div className="picker-result-meta">
                      <span className="picker-dur">{r.duration}s</span>
                      <span className="picker-res">{r.width}×{r.height}</span>
                    </div>
                    <div className="picker-photographer">📷 {r.photographer}</div>
                  </div>

                  {/* Pick button / loading */}
                  <div className="picker-result-action">
                    {isPicking ? (
                      <span className="picker-downloading">⏳ Downloading…</span>
                    ) : (
                      <button className="picker-pick-btn">
                        {isHovered ? '✓ Use this clip' : 'Select'}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Empty state */}
        {!loading && results.length === 0 && !error && (
          <div className="picker-empty">
            Type a search term and press Enter or click Search
          </div>
        )}
      </div>
    </div>
  )
}
