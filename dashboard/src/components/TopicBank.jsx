import { useState, useEffect, useRef } from 'react'

const STATUS_LABELS = {
  queued: 'Queued', in_progress: 'In Progress', published: 'Published', archived: 'Archived'
}
const STATUS_ORDER = ['queued', 'in_progress', 'published', 'archived']

export default function TopicBank({ project, onBack, onStartVideo }) {
  const [data, setData]         = useState(null)
  const [filter, setFilter]     = useState('all')
  const [generating, setGen]    = useState(false)
  const [genCount, setGenCount] = useState(20)
  const [starting, setStarting] = useState({})   // topic_id → true while loading
  const pollRef = useRef(null)

  const load = () => {
    fetch(`/api/projects/${project.project_id}/topics`)
      .then(r => r.json())
      .then(d => setData(d))
      .catch(() => {})
  }

  useEffect(() => {
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [project.project_id])

  const handleGenerate = async () => {
    setGen(true)
    try {
      const res = await fetch(`/api/projects/${project.project_id}/topics/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: genCount }),
      })
      if (!res.ok) throw new Error(await res.text())
      // Poll every 3s until topics stabilise
      let prev = data?.topics?.length || 0
      let stable = 0
      pollRef.current = setInterval(() => {
        fetch(`/api/projects/${project.project_id}/topics`)
          .then(r => r.json())
          .then(d => {
            setData(d)
            const cur = d.topics?.length || 0
            if (cur === prev) { stable++ } else { stable = 0; prev = cur }
            if (stable >= 3) { clearInterval(pollRef.current); setGen(false) }
          })
      }, 3000)
    } catch (e) { alert('Generate failed: ' + e.message); setGen(false) }
  }

  const handleStartVideo = async (topic) => {
    setStarting(s => ({ ...s, [topic.topic_id]: true }))
    try {
      const res = await fetch(
        `/api/projects/${project.project_id}/topics/${topic.topic_id}/start-video`,
        { method: 'POST' }
      )
      if (!res.ok) throw new Error(await res.text())
      const { job_id } = await res.json()
      load()
      onStartVideo && onStartVideo(job_id, topic)
    } catch (e) { alert('Failed to start: ' + e.message) }
    finally { setStarting(s => ({ ...s, [topic.topic_id]: false })) }
  }

  const handleStatus = async (topic, status) => {
    await fetch(`/api/projects/${project.project_id}/topics/${topic.topic_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    load()
  }

  const handleDelete = async (topic) => {
    if (!confirm(`Delete "${topic.title}"?`)) return
    await fetch(`/api/projects/${project.project_id}/topics/${topic.topic_id}`, { method: 'DELETE' })
    load()
  }

  const stats   = data?.stats || {}
  const topics  = data?.topics || []
  const visible = filter === 'all' ? topics : topics.filter(t => t.status === filter)

  return (
    <div className="topicbank-root">

      {/* Header */}
      <div className="topicbank-header">
        <button className="btn-back" onClick={onBack}>← Projects</button>
        <div className="topicbank-title-block">
          <h2 className="topicbank-title">{project.name}</h2>
          <span className="topicbank-niche">{project.niche}</span>
        </div>
        <div className="topicbank-generate">
          <select
            className="gen-count-select"
            value={genCount}
            onChange={e => setGenCount(Number(e.target.value))}
            disabled={generating}
          >
            {[10, 20, 30, 40].map(n => <option key={n} value={n}>{n} topics</option>)}
          </select>
          <button className="btn-generate-topics" onClick={handleGenerate} disabled={generating}>
            {generating ? '⏳ Generating…' : '✨ Generate Topics'}
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="topicbank-stats">
        {['all', ...STATUS_ORDER].map(s => {
          const count = s === 'all' ? (stats.total || 0) : (stats[s] || 0)
          return (
            <button
              key={s}
              className={`stat-filter-btn${filter === s ? ' active' : ''} stat-filter-${s}`}
              onClick={() => setFilter(s)}
            >
              {s === 'all' ? 'All' : STATUS_LABELS[s]} · {count}
            </button>
          )
        })}
      </div>

      {/* Topic list */}
      {topics.length === 0 ? (
        <div className="topicbank-empty">
          <p>No topics yet.</p>
          <p>Hit <strong>✨ Generate Topics</strong> to fill your bank with AI-generated ideas.</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="topicbank-empty"><p>No {filter} topics.</p></div>
      ) : (
        <div className="topic-list">
          {visible.map((topic, idx) => (
            <div key={topic.topic_id} className={`topic-row topic-row--${topic.status}`}>
              <div className="topic-row-left">
                <span className="topic-row-num">#{topics.indexOf(topic) + 1}</span>
                <div className="topic-row-body">
                  <p className="topic-row-title">{topic.title}</p>
                  {topic.hook && <p className="topic-row-hook">"{topic.hook}"</p>}
                  {topic.why_trending && <p className="topic-row-why">📈 {topic.why_trending}</p>}
                </div>
              </div>
              <div className="topic-row-right">
                <span className={`topic-status-pill status-pill--${topic.status}`}>
                  {STATUS_LABELS[topic.status]}
                </span>

                {topic.status === 'queued' && (
                  <button
                    className="btn-start-video"
                    onClick={() => handleStartVideo(topic)}
                    disabled={starting[topic.topic_id]}
                  >
                    {starting[topic.topic_id] ? '⏳' : '🎬 Make Video'}
                  </button>
                )}
                {topic.status === 'in_progress' && topic.job_id && (
                  <span className="topic-job-link">job: {topic.job_id.slice(0, 8)}…</span>
                )}
                {topic.status === 'in_progress' && (
                  <button className="btn-topic-action" onClick={() => handleStatus(topic, 'published')}>
                    ✅ Mark Published
                  </button>
                )}
                {topic.status === 'published' && (
                  <span className="topic-published-badge">✅ Published</span>
                )}

                {topic.status !== 'archived' && topic.status !== 'published' && (
                  <button className="btn-topic-archive" onClick={() => handleStatus(topic, 'archived')}
                    title="Archive this topic">
                    📦
                  </button>
                )}
                {topic.status === 'archived' && (
                  <button className="btn-topic-restore" onClick={() => handleStatus(topic, 'queued')}>
                    ↩ Restore
                  </button>
                )}
                <button className="btn-topic-delete" onClick={() => handleDelete(topic)} title="Delete">🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
