import { useState, useEffect } from 'react'

const NICHE_ICONS = {
  finance: '💰', entrepreneurship: '🚀', health: '🧬', tech: '⚡',
  mindset: '🧠', productivity: '⚙️', ai: '🤖', marketing: '📣',
  relationships: '❤️', fitness: '💪',
}
const NICHE_LABELS = {
  finance: 'Finance & Money', entrepreneurship: 'Entrepreneurship',
  health: 'Health & Wellness', tech: 'Technology', mindset: 'Mindset & Growth',
  productivity: 'Productivity', ai: 'AI & Future', marketing: 'Marketing',
  relationships: 'Relationships', fitness: 'Fitness',
}

export default function Projects({ onOpenProject }) {
  const [projects, setProjects]   = useState([])
  const [loading, setLoading]     = useState(true)
  const [creating, setCreating]   = useState(false)
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm]           = useState({ name: '', niche: 'ai', description: '' })

  const load = () => {
    setLoading(true)
    fetch('/api/projects')
      .then(r => r.json())
      .then(d => { setProjects(d); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!form.name.trim()) return alert('Project name required')
    setCreating(true)
    try {
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name, niche: form.niche, description: form.description }),
      })
      if (!res.ok) throw new Error(await res.text())
      const project = await res.json()
      setShowForm(false)
      setForm({ name: '', niche: 'ai', description: '' })
      load()
      onOpenProject(project)
    } catch (e) { alert('Failed: ' + e.message) }
    finally { setCreating(false) }
  }

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete project "${name}" and all its topics? This cannot be undone.`)) return
    await fetch(`/api/projects/${id}`, { method: 'DELETE' })
    load()
  }

  return (
    <div className="projects-root">
      <div className="projects-header">
        <div>
          <h2 className="projects-title">📋 Content Projects</h2>
          <p className="projects-sub">Build a topic bank per niche. Track every video from idea to published.</p>
        </div>
        <button className="btn-new-project" onClick={() => setShowForm(true)}>+ New Project</button>
      </div>

      {showForm && (
        <div className="project-form-card">
          <h3>New Project</h3>
          <input
            className="project-input"
            placeholder="Project name (e.g. AI Tools 2026)"
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          />
          <select
            className="project-input"
            value={form.niche}
            onChange={e => setForm(f => ({ ...f, niche: e.target.value }))}
          >
            {Object.entries(NICHE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{NICHE_ICONS[k]} {v}</option>
            ))}
          </select>
          <textarea
            className="project-input"
            placeholder="Description (optional)"
            rows={2}
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          />
          <div className="project-form-actions">
            <button className="btn-cancel" onClick={() => setShowForm(false)}>Cancel</button>
            <button className="btn-approve" onClick={handleCreate} disabled={creating}>
              {creating ? 'Creating…' : 'Create Project'}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="projects-empty">Loading…</p>
      ) : projects.length === 0 ? (
        <div className="projects-empty">
          <p>No projects yet.</p>
          <p style={{ fontSize: '13px', color: '#555', marginTop: '8px' }}>
            Create a project to build a topic bank and track your content pipeline.
          </p>
        </div>
      ) : (
        <div className="projects-grid">
          {projects.map(p => {
            const stats = p.stats || {}
            const pct = stats.total ? Math.round((stats.published / stats.total) * 100) : 0
            return (
              <div key={p.project_id} className="project-card" onClick={() => onOpenProject(p)}>
                <div className="project-card-header">
                  <span className="project-niche-icon">{NICHE_ICONS[p.niche] || '🎬'}</span>
                  <div className="project-card-meta">
                    <span className="project-card-name">{p.name}</span>
                    <span className="project-card-niche">{NICHE_LABELS[p.niche] || p.niche}</span>
                  </div>
                  <button
                    className="btn-project-delete"
                    onClick={e => { e.stopPropagation(); handleDelete(p.project_id, p.name) }}
                    title="Delete project"
                  >🗑</button>
                </div>
                {p.description && <p className="project-card-desc">{p.description}</p>}
                <div className="project-stats">
                  <span className="stat-pill stat-queued">{stats.queued || 0} queued</span>
                  <span className="stat-pill stat-in_progress">{stats.in_progress || 0} in progress</span>
                  <span className="stat-pill stat-published">{stats.published || 0} published</span>
                  {stats.archived > 0 && <span className="stat-pill stat-archived">{stats.archived} archived</span>}
                </div>
                <div className="project-progress-bar">
                  <div className="project-progress-fill" style={{ width: `${pct}%` }} />
                </div>
                <p className="project-progress-label">{pct}% published · {stats.total || 0} topics total</p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
