import { useState, useEffect } from 'react'

const DEFAULT_PLATFORMS = [
  { value: 'tiktok',    label: 'TikTok',    icon: '🎵', desc: '9:16 · vertical' },
  { value: 'instagram', label: 'Instagram', icon: '📸', desc: '9:16 · Reels'    },
  { value: 'youtube',   label: 'YouTube',   icon: '▶️', desc: '9:16 · Shorts'   },
  { value: 'facebook',  label: 'Facebook',  icon: '👥', desc: '9:16 · Reels'    },
]

export default function NicheWizard({ niches, defaultPlatforms = ['tiktok','instagram','youtube','facebook'], onSelect, onBack }) {
  const [selected, setSelected] = useState(new Set(defaultPlatforms))
  const [platforms, setPlatforms] = useState(DEFAULT_PLATFORMS)

  const hasNiches = Object.keys(niches).length > 0

  // Keep selected in sync if defaultPlatforms changes
  useEffect(() => { setSelected(new Set(defaultPlatforms)) }, [defaultPlatforms.join(',')])

  // Load platforms from backend
  useEffect(() => {
    fetch('/api/platforms')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.platforms) return
        const ICONS = { youtube: '▶️', tiktok: '🎵', instagram: '📸', facebook: '👥' }
        const DESCS = { youtube: '9:16 · Shorts', tiktok: '9:16 · vertical', instagram: '9:16 · Reels', facebook: '9:16 · Reels' }
        const list = Object.entries(data.platforms).map(([k, v]) => ({
          value: k, label: v.label, icon: ICONS[k] || '🎬', desc: DESCS[k] || `${v.width}×${v.height}`,
        }))
        if (list.length) setPlatforms(list)
      })
      .catch(() => {})
  }, [])

  const toggle = (value) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(value)) {
        if (next.size === 1) return prev  // must keep at least one
        next.delete(value)
      } else {
        next.add(value)
      }
      return next
    })
  }

  const selectAll  = () => setSelected(new Set(platforms.map(p => p.value)))
  const clearAll   = () => setSelected(new Set([platforms[0].value]))  // keep first

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
        {onBack && (
          <button className="btn-wizard-back" onClick={onBack}>← Back to jobs</button>
        )}
        <h1 className="wizard-title">🎬 Create a New Video</h1>
        <p className="wizard-subtitle">Pick a niche — one Shorts script, exported to every selected platform</p>

        {/* Platform multi-select */}
        <div className="platform-section">
          <div className="platform-section-label">
            <span>Export to platforms</span>
            <span className="platform-section-meta">
              <button className="btn-platform-link" onClick={selectAll}>all</button>
              {' · '}
              <button className="btn-platform-link" onClick={clearAll}>clear</button>
            </span>
          </div>
          <div className="platform-toggle">
            {platforms.map(p => {
              const isOn = selected.has(p.value)
              return (
                <button
                  key={p.value}
                  className={`platform-btn${isOn ? ' active' : ''}`}
                  onClick={() => toggle(p.value)}
                  title={isOn ? `Deselect ${p.label}` : `Select ${p.label}`}
                >
                  <span className="platform-icon">{p.icon}</span>
                  <span className="platform-label">{p.label}</span>
                  <span className="platform-desc">{p.desc}</span>
                  <span className={`platform-check${isOn ? ' on' : ''}`}>{isOn ? '✓' : '+'}</span>
                </button>
              )
            })}
          </div>
          <p className="platform-hint">
            One 70-90s Shorts script · rendered once · auto-exported to {selected.size} platform{selected.size !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      {!hasNiches ? (
        <div className="wizard-error" style={{ textAlign: 'center', padding: '40px 20px' }}>
          <p>⚠️ Could not load niches — is the server running?</p>
          <button className="btn-wizard-refresh" style={{ marginTop: '12px' }}
            onClick={() => window.location.reload()}>🔄 Retry</button>
        </div>
      ) : (
        <div className="niche-grid">
          {Object.entries(niches).map(([key, niche]) => (
            <button
              key={key}
              className="niche-card"
              style={{ '--niche-color': niche.color }}
              onClick={() => onSelect(key, [...selected])}
            >
              <span className="niche-icon">{niche.icon}</span>
              <span className="niche-label">{niche.label}</span>
              <span className="niche-desc">{niche.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
