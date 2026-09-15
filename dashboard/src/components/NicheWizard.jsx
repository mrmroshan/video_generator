import { useState } from 'react'

const PLATFORM_OPTIONS = [
  { value: 'youtube',  label: 'YouTube',  icon: '▶️', desc: '16:9 · landscape' },
  { value: 'tiktok',   label: 'TikTok',   icon: '🎵', desc: '9:16 · vertical'  },
]

export default function NicheWizard({ niches, defaultPlatform = 'youtube', onSelect, onBack }) {
  const [platform, setPlatform] = useState(defaultPlatform)

  const hasNiches = Object.keys(niches).length > 0

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
        {onBack && (
          <button className="btn-wizard-back" onClick={onBack}>← Back to jobs</button>
        )}
        <h1 className="wizard-title">🎬 Create a New Video</h1>
        <p className="wizard-subtitle">Pick a niche — we'll generate trending topics for you</p>

        {/* Platform toggle */}
        <div className="platform-toggle">
          {PLATFORM_OPTIONS.map(p => (
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
