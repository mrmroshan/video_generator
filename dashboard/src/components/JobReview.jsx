import { useState, useRef, useEffect } from 'react'
import SceneCard from './SceneCard.jsx'
import Timeline from './Timeline.jsx'
import { formatDistanceToNow } from '../utils/time.js'

export default function JobReview({ job, onBack, onUpdate }) {
  const [approving, setApproving]       = useState(false)
  const [activeScene, setActiveScene]   = useState(job.scenes?.[0]?.scene_id || null)
  const sceneRefs                       = useRef({})
  const locked = job.status === 'approved'

  // Scroll to scene card when timeline scene is clicked
  const handleSelectScene = (sceneId) => {
    setActiveScene(sceneId)
    const el = sceneRefs.current[sceneId]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // Reorder: send new scene_id order to API
  const handleReorder = async (orderedIds, directUpdatedJob) => {
    if (directUpdatedJob) { onUpdate(directUpdatedJob); return }
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_ids: orderedIds }),
      })
      if (!res.ok) throw new Error(await res.text())
      onUpdate(await res.json())
    } catch (e) {
      alert('Reorder failed: ' + e.message)
    }
  }

  const approve = async () => {
    if (!confirm('Lock this job as approved? No further edits will be possible.')) return
    setApproving(true)
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/approve`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      onUpdate(await res.json())
    } catch (e) {
      alert('Approval failed: ' + e.message)
    } finally {
      setApproving(false)
    }
  }

  const totalDuration = job.scenes?.reduce((s, sc) => s + (sc.target_duration_seconds || 0), 0) || 0

  return (
    <div className="review-root">

      {/* ── Top bar ─────────────────────────────────────────────── */}
      <div className="review-topbar">
        <button className="btn-back" onClick={onBack}>← Jobs</button>

        <div className="review-title">
          <h2>{job.title}</h2>
          <div className="review-meta">
            <span>📱 {job.platform}</span>
            <span>🎬 {job.scenes?.length} scenes</span>
            <span>⏱ {totalDuration.toFixed(1)}s</span>
            <span>🕐 {formatDistanceToNow(job.created_at)}</span>
            <span className={`status-badge status-${job.status}`}>{job.status}</span>
            {job.hashtags?.length > 0 && (
              <span className="hashtags">{job.hashtags.join(' ')}</span>
            )}
          </div>
        </div>

        {locked ? (
          <div className="approved-badge">✓ Approved</div>
        ) : (
          <button className="btn-approve" onClick={approve} disabled={approving}>
            {approving ? 'Approving…' : '✓ Approve & Lock'}
          </button>
        )}
      </div>

      {/* ── Timeline ─────────────────────────────────────────────── */}
      <Timeline
        job={job}
        activeSceneId={activeScene}
        onSelectScene={handleSelectScene}
        onReorder={handleReorder}
        locked={locked}
      />

      {/* ── Scene cards ──────────────────────────────────────────── */}
      <div className="scenes-list">
        {job.scenes?.map((scene, idx) => (
          <div
            key={scene.scene_id}
            ref={el => sceneRefs.current[scene.scene_id] = el}
            className={activeScene === scene.scene_id ? 'scene-wrap scene-wrap--active' : 'scene-wrap'}
            onClick={() => setActiveScene(scene.scene_id)}
          >
            <SceneCard
              scene={scene}
              sceneIndex={idx + 1}
              jobId={job.job_id}
              jobStatus={job.status}
              onUpdate={onUpdate}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
