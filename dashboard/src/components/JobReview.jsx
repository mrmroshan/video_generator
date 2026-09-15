import { useState, useRef, useEffect } from 'react'
import SceneCard from './SceneCard.jsx'
import Timeline from './Timeline.jsx'
import CaptionStylePicker from './CaptionStylePicker.jsx'
import { formatDistanceToNow } from '../utils/time.js'

export default function JobReview({ job, onBack, onUpdate }) {
  const [approving, setApproving]       = useState(false)
  const [rendering, setRendering]       = useState(false)
  const [savingDraft, setSavingDraft]   = useState(false)
  const [draftSaved, setDraftSaved]     = useState(false)   // flash confirmation
  const [activeScene, setActiveScene]   = useState(job.scenes?.[0]?.scene_id || null)
  const sceneRefs    = useRef({})
  const pollRef      = useRef(null)
  const draftTimeout = useRef(null)

  const isDraft  = job.status === 'draft'
  const locked   = job.status === 'approved' || job.status === 'done'
  const rendered = job.status === 'done' && job.output_path
  const editable = !locked   // in_review OR draft

  // Clean up intervals on unmount
  useEffect(() => () => {
    if (pollRef.current)      clearInterval(pollRef.current)
    if (draftTimeout.current) clearTimeout(draftTimeout.current)
  }, [])

  const handleSelectScene = (sceneId) => {
    setActiveScene(sceneId)
    sceneRefs.current[sceneId]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

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
    } catch (e) { alert('Reorder failed: ' + e.message) }
  }

  const saveDraft = async () => {
    setSavingDraft(true)
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/save-draft`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      onUpdate(await res.json())
      setDraftSaved(true)
      if (draftTimeout.current) clearTimeout(draftTimeout.current)
      draftTimeout.current = setTimeout(() => setDraftSaved(false), 3000)
    } catch (e) { alert('Save draft failed: ' + e.message) }
    finally { setSavingDraft(false) }
  }

  const approve = async () => {
    if (!confirm('Approve and lock for render? Edits will no longer be possible.')) return
    setApproving(true)
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/approve`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      onUpdate(await res.json())
    } catch (e) { alert('Approval failed: ' + e.message) }
    finally { setApproving(false) }
  }

  const render = async () => {
    if (!confirm('Render to MP4 with captions? Takes ~30–60s.')) return
    setRendering(true)
    try {
      const res = await fetch(`/api/jobs/${job.job_id}/render`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())

      // Poll /render-status every 3 seconds until done or failed; max 5 min timeout
      let elapsed = 0
      pollRef.current = setInterval(async () => {
        elapsed += 3
        try {
          const sr = await fetch(`/api/jobs/${job.job_id}/render-status`)
          if (!sr.ok) return
          const data = await sr.json()
          if (data.done || data.failed || elapsed >= 300) {
            clearInterval(pollRef.current); pollRef.current = null
            setRendering(false)
            if (elapsed >= 300 && !data.done) {
              alert('Render timed out — check server logs.')
              return
            }
            const jr = await fetch(`/api/jobs/${job.job_id}`)
            if (jr.ok) onUpdate(await jr.json())
          }
        } catch (_) { }
      }, 3000)
    } catch (e) {
      alert('Render failed: ' + e.message)
      setRendering(false)
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

        <div className="review-actions">
          {rendered ? (
            <a className="btn-download" href={`/api/jobs/${job.job_id}/output`} download>
              ⬇ Download MP4
            </a>
          ) : locked ? (
            <button className="btn-render" onClick={render} disabled={rendering}>
              {rendering ? '⏳ Rendering… (checking every 3s)' : '🎬 Render MP4'}
            </button>
          ) : (
            <>
              {/* Save Draft — available while editing (in_review or draft) */}
              <button
                className={`btn-save-draft${draftSaved ? ' saved' : ''}`}
                onClick={saveDraft}
                disabled={savingDraft}
                title="Save your edits as a draft. Come back and keep editing anytime."
              >
                {savingDraft ? 'Saving…' : draftSaved ? '✓ Draft saved!' : isDraft ? '💾 Re-save Draft' : '💾 Save Draft'}
              </button>

              {/* Approve — locks for render */}
              <button className="btn-approve" onClick={approve} disabled={approving}>
                {approving ? 'Approving…' : '✓ Approve & Lock'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Caption style picker ─────────────────────────────────── */}
      <CaptionStylePicker job={job} onUpdate={onUpdate} />

      {/* ── Timeline ─────────────────────────────────────────────── */}
      <Timeline
        job={job}
        activeSceneId={activeScene}
        onSelectScene={handleSelectScene}
        onReorder={handleReorder}
        onJobUpdate={onUpdate}
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
