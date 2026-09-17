import { useState, useEffect } from 'react'

// ── Default platform groups (shown while API loads) ───────────────────
const DEFAULT_GROUPS = {
  tiktok: {
    label: 'TikTok', icon: '🎵',
    formats: [
      { key: 'tiktok',         label: 'Vertical',  desc: '9:16 · Vertical', available: true, default: true },
    ],
  },
  youtube: {
    label: 'YouTube', icon: '▶️',
    formats: [
      { key: 'youtube_shorts', label: 'Shorts',    desc: '9:16 · Shorts',       available: true,  default: true },
      { key: 'youtube_long',   label: 'Long-form', desc: '16:9 · Main channel', available: false, default: false },
    ],
  },
  instagram: {
    label: 'Instagram', icon: '📸',
    formats: [
      { key: 'instagram_reels',    label: 'Reels',    desc: '9:16 · Reels', available: true, default: true },
      { key: 'instagram_square',   label: 'Square',   desc: '1:1 · Feed',   available: true, default: false },
      { key: 'instagram_portrait', label: 'Portrait', desc: '4:5 · Feed',   available: true, default: false },
    ],
  },
  facebook: {
    label: 'Facebook', icon: '👥',
    formats: [
      { key: 'facebook_reels',  label: 'Reels',  desc: '9:16 · Reels', available: true, default: true },
      { key: 'facebook_square', label: 'Square', desc: '1:1 · Feed',   available: true, default: false },
    ],
  },
}

/**
 * Build the default selected formats given a set of brand keys.
 * Picks each brand's default+available format.
 */
function defaultFormatsFor(brands, groups) {
  const result = []
  for (const brand of brands) {
    const grp = groups[brand]
    if (!grp) continue
    const def = grp.formats.find(f => f.default && f.available)
    if (def) result.push(def.key)
  }
  return result
}

export default function NicheWizard({ niches, defaultPlatforms = ['tiktok', 'instagram', 'youtube', 'facebook'], onSelect, onBack }) {
  const [groups, setGroups]             = useState(DEFAULT_GROUPS)
  const [activeBrands, setActiveBrands] = useState(new Set(defaultPlatforms))
  const [selFormats, setSelFormats]     = useState(() =>
    defaultFormatsFor(defaultPlatforms, DEFAULT_GROUPS)
  )
  const [brollSource, setBrollSource]   = useState('pexels')

  const hasNiches = Object.keys(niches).length > 0

  // Sync brands when defaultPlatforms prop changes
  useEffect(() => {
    setActiveBrands(new Set(defaultPlatforms))
    setSelFormats(defaultFormatsFor(defaultPlatforms, groups))
  }, [defaultPlatforms.join(',')])   // eslint-disable-line

  // Load platform groups from backend
  useEffect(() => {
    fetch('/api/platforms')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.groups && Object.keys(data.groups).length > 0) {
          setGroups(data.groups)
          // Re-derive defaults with loaded groups
          setSelFormats(defaultFormatsFor([...activeBrands], data.groups))
        }
      })
      .catch(() => {})
  }, [])   // eslint-disable-line

  // ── Brand toggle ────────────────────────────────────────────────────
  const toggleBrand = (brand) => {
    setActiveBrands(prev => {
      const next = new Set(prev)
      if (next.has(brand)) {
        if (next.size === 1) return prev   // must keep at least one brand
        next.delete(brand)
        // Remove all formats for this brand from selFormats
        const brandFmts = new Set((groups[brand]?.formats || []).map(f => f.key))
        setSelFormats(sf => sf.filter(k => !brandFmts.has(k)))
      } else {
        next.add(brand)
        // Auto-select the default format for this brand
        const grp = groups[brand]
        if (grp) {
          const def = grp.formats.find(f => f.default && f.available)
          if (def) setSelFormats(sf => sf.includes(def.key) ? sf : [...sf, def.key])
        }
      }
      return next
    })
  }

  // ── Format toggle ────────────────────────────────────────────────────
  const toggleFormat = (brand, fmtKey, available) => {
    if (!available) return   // coming-soon formats are not clickable
    const brandFmts = (groups[brand]?.formats || []).filter(f => f.available).map(f => f.key)

    setSelFormats(prev => {
      const has = prev.includes(fmtKey)
      if (has) {
        // Don't deselect if it's the last format for this brand
        const remaining = prev.filter(k => k !== fmtKey && brandFmts.includes(k))
        if (remaining.length === 0) return prev
        return prev.filter(k => k !== fmtKey)
      }
      return [...prev, fmtKey]
    })
  }

  const selectAll = () => {
    const allBrands = Object.keys(groups)
    setActiveBrands(new Set(allBrands))
    setSelFormats(defaultFormatsFor(allBrands, groups))
  }

  const clearAll = () => {
    const first = Object.keys(groups)[0] || 'tiktok'
    setActiveBrands(new Set([first]))
    setSelFormats(defaultFormatsFor([first], groups))
  }

  const totalFormats = selFormats.length

  return (
    <div className="wizard-screen">
      <div className="wizard-header">
        {onBack && (
          <button className="btn-wizard-back" onClick={onBack}>← Back to jobs</button>
        )}
        <h1 className="wizard-title">🎬 Create a New Video</h1>
        <p className="wizard-subtitle">Pick a niche — one Shorts script, exported to every selected format</p>
      </div>

      <div className="wizard-body">

        {/* ── Platform + Format two-level picker ─────────────────────── */}
        <div className="platform-section">
          <div className="platform-section-label">
            <span>Platforms &amp; Formats</span>
            <span className="platform-section-meta">
              <button className="btn-platform-link" onClick={selectAll}>all</button>
              {' · '}
              <button className="btn-platform-link" onClick={clearAll}>clear</button>
            </span>
          </div>

          <div className="platform-groups">
            {Object.entries(groups).map(([brand, grp]) => {
              const brandOn = activeBrands.has(brand)
              const availFmts = (grp.formats || []).filter(f => f.available)
              const anySelForBrand = availFmts.some(f => selFormats.includes(f.key))

              return (
                <div key={brand} className={`platform-group${brandOn ? ' group-on' : ''}`}>
                  {/* Brand row */}
                  <button
                    className={`platform-brand-btn${brandOn ? ' active' : ''}`}
                    onClick={() => toggleBrand(brand)}
                  >
                    <span className="platform-icon">{grp.icon}</span>
                    <span className="platform-label">{grp.label}</span>
                    <span className={`platform-check${brandOn ? ' on' : ''}`}>
                      {brandOn ? '✓' : '+'}
                    </span>
                  </button>

                  {/* Format chips — always visible so user sees options */}
                  <div className="format-chips">
                    {(grp.formats || []).map(fmt => {
                      const fmtSelected = selFormats.includes(fmt.key)
                      const isDefault   = fmt.default
                      return (
                        <button
                          key={fmt.key}
                          className={[
                            'format-chip',
                            fmtSelected  ? 'chip-on'      : '',
                            !fmt.available ? 'chip-soon'  : '',
                            isDefault    ? 'chip-default' : '',
                          ].filter(Boolean).join(' ')}
                          onClick={() => {
                            if (!brandOn) toggleBrand(brand)   // auto-activate brand
                            toggleFormat(brand, fmt.key, fmt.available)
                          }}
                          title={fmt.available ? fmt.desc : 'Coming soon'}
                          disabled={!fmt.available}
                        >
                          {fmt.label}
                          <span className="chip-desc">{fmt.desc}</span>
                          {!fmt.available && <span className="chip-soon-badge">🔜</span>}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          <p className="platform-hint">
            One 70–90s script · rendered once · exported as{' '}
            <strong>{totalFormats} format{totalFormats !== 1 ? 's' : ''}</strong>
            {totalFormats > 0 && (
              <span className="platform-hint-formats">
                {' ('}
                {selFormats.map(k => {
                  // find label from groups
                  for (const grp of Object.values(groups)) {
                    const f = (grp.formats || []).find(f => f.key === k)
                    if (f) return f.label
                  }
                  return k
                }).join(', ')}
                {')'}
              </span>
            )}
          </p>
        </div>

        {/* ── B-roll source picker ─────────────────────────────────── */}
        <div className="broll-source-picker">
          <p className="broll-source-label">B-roll Source</p>
          <label className={`broll-option${brollSource === 'pexels' ? ' active' : ''}`}>
            <input
              type="radio"
              name="broll-source"
              value="pexels"
              checked={brollSource === 'pexels'}
              onChange={() => setBrollSource('pexels')}
            />
            <span>📦 Pexels</span>
            <span className="broll-option-desc">Free · Fast · Stock footage</span>
          </label>
          <label className={`broll-option${brollSource === 'veo2' ? ' active' : ''}`}>
            <input
              type="radio"
              name="broll-source"
              value="veo2"
              checked={brollSource === 'veo2'}
              onChange={() => setBrollSource('veo2')}
            />
            <span>🤖 Veo 2</span>
            <span className="broll-option-desc">AI-generated · ~3-7 min · ~$2.50/video</span>
          </label>
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
              onClick={() => onSelect(key, [...activeBrands], brollSource, selFormats)}
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
