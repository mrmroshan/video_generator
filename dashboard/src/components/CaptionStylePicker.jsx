import { useState, useEffect } from 'react'

const STYLE_META = {
  clean:          { icon: '📺', label: 'Clean',     desc: 'White bold · black outline · bottom' },
  cinematic:      { icon: '🎬', label: 'Cinematic', desc: 'Yellow on dark bar · documentary' },
  tiktok:         { icon: '📱', label: 'TikTok',    desc: 'Giant Impact · thick outline · center' },
  minimal:        { icon: '🤍', label: 'Minimal',   desc: 'Small gray · no outline · subtle' },
  karaoke:        { icon: '✨', label: 'Karaoke',   desc: 'Word-by-word highlight · yellow · bottom' },
  karaoke_tiktok: { icon: '🔥', label: 'KTV TikTok', desc: 'Word highlight · Impact · center screen' },
  karaoke_fire:   { icon: '🌶', label: 'KTV Fire',   desc: 'Word highlight · orange · dramatic' },
}

export default function CaptionStylePicker({ job, onUpdate }) {
  const [active, setActive]     = useState(job.caption_style || 'clean')
  const [saving, setSaving]     = useState(false)
  const [previewStyle, setPreview] = useState(null)
  const locked = job.status === 'approved' || job.status === 'done' || job.status === 'rendering'

  // Sync if job changes externally
  useEffect(() => { setActive(job.caption_style || 'clean') }, [job.caption_style])

  const select = async (style) => {
    if (locked || style === active) return
    setSaving(true)
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/caption-style`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caption_style: style }),
      })
      if (!res.ok) throw new Error(await res.text())
      setActive(style)
      onUpdate(await res.json())
    } catch (e) {
      alert('Style save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="caption-picker">
      <div className="caption-picker-label">
        <span>🔤 Caption Style</span>
        {locked && <span className="caption-picker-locked">locked</span>}
        {saving && <span className="caption-picker-saving">saving…</span>}
      </div>

      <div className="caption-picker-grid">
        {Object.entries(STYLE_META).map(([key, meta]) => (
          <button
            key={key}
            className={[
              'caption-style-btn',
              active === key ? 'caption-style-btn--active' : '',
              locked        ? 'caption-style-btn--locked' : '',
            ].join(' ')}
            onClick={() => select(key)}
            onMouseEnter={() => setPreview(key)}
            onMouseLeave={() => setPreview(null)}
            disabled={locked || saving}
            title={meta.desc}
          >
            <span className="style-icon">{meta.icon}</span>
            <span className="style-label">{meta.label}</span>
            {active === key && <span className="style-check">✓</span>}
          </button>
        ))}
      </div>

      {previewStyle && (
        <div className="caption-preview">
          <CaptionPreview style={previewStyle} />
        </div>
      )}
    </div>
  )
}

function CaptionPreview({ style }) {
  const SAMPLE = "You didn't choose to be here. You opened the app for ten seconds."

  const styles = {
    clean: {
      fontFamily: 'Arial, sans-serif', fontWeight: 'bold',
      fontSize: 18, color: '#fff',
      textShadow: '2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000',
      position: 'absolute', bottom: 16, left: 16, right: 16, textAlign: 'center',
    },
    cinematic: {
      fontFamily: 'Arial, sans-serif', fontWeight: 'bold',
      fontSize: 16, color: '#F5E642',
      background: 'rgba(0,0,0,0.72)', padding: '4px 10px',
      position: 'absolute', bottom: 16, left: 0, right: 0, textAlign: 'center',
    },
    tiktok: {
      fontFamily: 'Impact, Arial Narrow, sans-serif', fontWeight: 'normal',
      fontSize: 24, color: '#fff',
      textShadow: '3px 3px 0 #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000',
      position: 'absolute', top: '50%', left: 8, right: 8,
      transform: 'translateY(-50%)', textAlign: 'center',
    },
    minimal: {
      fontFamily: 'Arial, sans-serif', fontWeight: 'normal',
      fontSize: 13, color: '#ccc',
      textShadow: '1px 1px 0 #000',
      position: 'absolute', bottom: 10, right: 12, textAlign: 'right', maxWidth: '70%',
    },
    karaoke: {
      fontFamily: 'Arial, sans-serif', fontWeight: 'bold',
      fontSize: 20, color: '#fff',
      textShadow: '2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000',
      position: 'absolute', bottom: 16, left: 16, right: 16, textAlign: 'center',
    },
    karaoke_tiktok: {
      fontFamily: 'Impact, Arial Narrow, sans-serif', fontWeight: 'normal',
      fontSize: 24, color: '#fff',
      textShadow: '3px 3px 0 #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000',
      position: 'absolute', top: '50%', left: 8, right: 8,
      transform: 'translateY(-50%)', textAlign: 'center',
    },
    karaoke_fire: {
      fontFamily: 'Arial, sans-serif', fontWeight: 'bold',
      fontSize: 20, color: '#e0e0e0',
      textShadow: '2px 2px 0 #000, -2px -2px 0 #000',
      position: 'absolute', bottom: 16, left: 16, right: 16, textAlign: 'center',
    },
  }

  return (
    <div className="caption-preview-frame">
      <div style={{ position: 'relative', width: '100%', height: '100%', background: '#111' }}>
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ color: '#333', fontSize: 11, fontStyle: 'italic' }}>video preview</span>
        </div>
        {style.startsWith('karaoke') ? (
          <div style={styles[style] || styles.karaoke}>
            <span style={{color: '#fff'}}>You opened the app </span>
            <span style={{color: '#FFFF00', fontWeight: 'bold'}}>for ten</span>
            <span style={{color: '#fff'}}> seconds.</span>
          </div>
        ) : (
          <div style={styles[style]}>
            {SAMPLE.slice(0, 52)}{SAMPLE.length > 52 ? '…' : ''}
          </div>
        )}
      </div>
    </div>
  )
}
