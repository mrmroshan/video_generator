import { useState, useEffect } from 'react'

// Fallback used while /api/platforms loads
const DEFAULT_PLATFORMS = [
  { value: 'youtube',   label: 'YouTube',   icon: '▶️', desc: '16:9 · landscape' },
  { value: 'tiktok',    label: 'TikTok',    icon: '🎵', desc: '9:16 · vertical'  },
  { value: 'instagram', label: 'Instagram', icon: '📸', desc: '1:1 · square'     },
  { value: 'facebook',  label: 'Facebook',  icon: '👥', desc: '16:9 · landscape' },
]

export default function NicheWizard({ niches, defaultPlatform = 'youtube', onSelect, onBack }) {
  const [platform, setPlatform]   = useState(defaultPlatform)
  const [platforms, setPlatforms] = useState(DEFAULT_PLATFORMS)

  const hasNiches = Object.keys(niches).length > 0

  // Load platforms from backend so UI always matches server capabilities
  useEffect(() => {
    fetch('/api/platforms')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.platforms) return
        const ICONS = { youtube: '▶️', tiktok: '🎵', instagram: '📸', facebook: '👥' }
        const list = Object.entries(data.platforms).map(([k, v]) => ({
          value: k,
          label: v.label,
          icon:  ICONS[k] || '🎬',
          desc:  `${v.width}×${v.height}`,
        }))
        if (list.length) setPlatforms(list)
      })
      .catch(() => {})  // keep defaults on error
  }, [])

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
        {onBack && (
          <button className="btn-wizard-back" onClick={onBack}>← Back to jobs</button>
        )}
        <h1 className="wizard-title">🎬 Create a New Video</h1>
        <p className="wizard-subtitle">Pick a niche — we'll generate trending topics for you</p>

        {/* Platform toggle — all 4 platforms */}
        <div className="platform-toggle">
          {platforms.map(p => (
            <button
              key={p.value}
              className={`platform-btn${platform === p.value ? ' active' : ''}`}
              onClick={() => setPlatform(p.value)}
            >
              <span className="platform-icon">{p.icon}</span>
              <span className="platform-label">{p.label}</span>
              <span className="platform-desc">{p.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {!hasNiches ? (
        <div className="wizard-error" style={{ textAlign: 'center', padding: '40px 20px' }}>
          <p>⚠️ Could not load niches — is the server running?</p>
          <button className="btn-wizard-refresh" style={{ marginTop: '12px' }}
            onClick={() => window.location.reload()}>
            🔄 Retry
          </button>
        </div>
      ) : (
        <div className="niche-grid">
          {Object.entries(niches).map(([key, niche]) => (
            <button
              key={key}
              className="niche-card"
              style={{ '--niche-color': niche.color }}
              onClick={() => onSelect(key, platform)}
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
