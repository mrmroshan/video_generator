import { useState } from 'react'

const PLATFORM_OPTIONS = [
  { value: 'youtube',  label: 'YouTube',  icon: '▶️', desc: '16:9 · landscape' },
  { value: 'tiktok',   label: 'TikTok',   icon: '🎵', desc: '9:16 · vertical'  },
]

export default function NicheWizard({ niches, onSelect }) {
  const [platform, setPlatform] = useState('youtube')

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
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
    </div>
  )
}
