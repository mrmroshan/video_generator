import { useState, useEffect } from 'react'

export default function TopicPicker({ niche, nicheInfo, platforms = ['tiktok'], onSelect, onBack, createLoading = false, wizardError = null }) {
  const [topics, setTopics]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [selected, setSelected]   = useState(null)
  const [captionStyle, setStyle]  = useState('karaoke')

  const STYLES = [
    { value: 'karaoke',       label: '🎤 Karaoke',     desc: 'Word-by-word highlight' },
    { value: 'karaoke_tiktok',label: '🔥 TikTok',      desc: 'Bold centre highlight' },
    { value: 'karaoke_fire',  label: '✨ Fire',         desc: 'Glowing word pop' },
    { value: 'clean',         label: '✏️ Clean',        desc: 'Minimal subtitle' },
    { value: 'cinematic',     label: '🎬 Cinematic',    desc: 'Elegant fade-in' },
  ]

  const loadTopics = async () => {
    setLoading(true)
    setError(null)
    setTopics([])
    setSelected(null)
    try {
      const res = await fetch('/api/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ niche, platform: platforms[0] }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setTopics(data.topics || [])
    } catch (e) {
      setError('Could not load topics: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTopics() }, [niche, platforms[0]])

  const handleGenerate = () => {
    if (!selected) return
    onSelect({
      niche,
      platforms,
      topic_title:   selected.title,
      topic_hook:    selected.hook,
      caption_style: captionStyle,
    })
  }

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
        <button className="btn-wizard-back" onClick={onBack}>← Back</button>
        <div className="wizard-niche-badge" style={{ background: nicheInfo?.color + '22', borderColor: nicheInfo?.color }}>
          <span>{nicheInfo?.icon}</span>
          <span>{nicheInfo?.label}</span>
          <span className="wizard-platform-tag">{platforms.join(' · ')}</span>
        </div>
        <h2 className="wizard-title">Pick a Topic</h2>
        <p className="wizard-subtitle">
          {loading ? 'Generating trending topics…' : `${topics.length} topic ideas for you`}
        </p>
      </div>

      {error && <div className="wizard-error">❌ {error}</div>}

      {loading ? (
        <div className="wizard-loading">
          <div className="wizard-spinner" />
          <p>Generating trending topics with AI…</p>
        </div>
      ) : (
        <>
          <div className="topic-grid">
            {topics.map(t => (
              <button
                key={t.id}
                className={`topic-card${selected?.id === t.id ? ' selected' : ''}`}
                onClick={() => setSelected(t)}
              >
                <div className="topic-title">{t.title}</div>
                <div className="topic-hook">"{t.hook}"</div>
                <div className="topic-trending">📈 {t.why_trending}</div>
              </button>
            ))}
          </div>

          <div className="wizard-actions-row">
            <button className="btn-wizard-refresh" onClick={loadTopics}>
              🔄 Generate more ideas
            </button>
          </div>

          {/* Caption style */}
          <div className="wizard-style-row">
            <span className="wizard-style-label">Caption style:</span>
            <div className="wizard-style-options">
              {STYLES.map(s => (
                <button
                  key={s.value}
                  className={`wizard-style-btn${captionStyle === s.value ? ' active' : ''}`}
                  onClick={() => setStyle(s.value)}
                  title={s.desc}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-cta">
            <button
              className="btn-wizard-generate"
              disabled={!selected || createLoading}
              onClick={handleGenerate}
            >
              {createLoading ? '⏳ Starting pipeline…' :
               selected
                ? `🚀 Generate Video — "${selected.title.slice(0, 40)}${selected.title.length > 40 ? '…' : ''}"`
                : '← Select a topic above'}
            </button>
            {/* Inline error — shown near CTA so user sees it even when scrolled down */}
            {wizardError && (
              <div className="ce-error" style={{ marginTop: '8px', textAlign: 'center' }}>
                ❌ {wizardError}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
