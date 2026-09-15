import { useState, useEffect } from 'react'
import BrollPicker from './BrollPicker.jsx'
import CaptionEditor from './CaptionEditor.jsx'

export default function SceneCard({ scene, sceneIndex, jobId, jobStatus, onUpdate }) {
  const [caption, setCaption]         = useState(scene.voiceover_text)
  const [brollPrompt, setBrollPrompt] = useState(scene.broll_prompt)
  const [duration, setDuration]       = useState(scene.target_duration_seconds)
  const [editing, setEditing]         = useState(false)
  const [saving, setSaving]           = useState(false)
  const [showPicker, setShowPicker]   = useState(false)
  const locked = jobStatus === 'approved' || jobStatus === 'done'

  useEffect(() => {
    setCaption(scene.voiceover_text)
    setBrollPrompt(scene.broll_prompt)
    setDuration(scene.target_duration_seconds)
  }, [scene.scene_id, scene.voiceover_text, scene.broll_prompt, scene.target_duration_seconds])

  const saveChanges = async () => {
    setSaving(true)
    try {
      const res = await fetch(`/api/jobs/${jobId}/scenes/${scene.scene_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          voiceover_text: caption,
          broll_prompt: brollPrompt,
          target_duration_seconds: parseFloat(duration),
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      onUpdate(await res.json())
      setEditing(false)
    } catch (e) {
      alert('Save failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const cancelChanges = () => {
    setCaption(scene.voiceover_text)
    setBrollPrompt(scene.broll_prompt)
    setDuration(scene.target_duration_seconds)
    setEditing(false)
  }

  const audioSrc = scene.audio_path ? `/api/jobs/${jobId}/scenes/${scene.scene_id}/audio` : null
  const brollSrc = scene.broll_path ? `/api/jobs/${jobId}/scenes/${scene.scene_id}/broll` : null
  const meta = scene.broll_meta || {}

  return (
    <>
      {showPicker && (
        <BrollPicker
          scene={scene}
          jobId={jobId}
          onPicked={(updatedJob) => { setShowPicker(false); onUpdate(updatedJob) }}
          onClose={() => setShowPicker(false)}
        />
      )}

      <div className="scene-card">

        {/* ── Header ───────────────────────────────────────── */}
        <div className="scene-header">
          <div className="scene-header-left">
            <span className="scene-num">{sceneIndex}</span>
            <span className="scene-id">{scene.scene_id}</span>
          </div>
          <div className="scene-header-right">
            {meta.photographer && (
              <span className="scene-credit">
                📷 {meta.photographer} · {meta.duration}s · {meta.width}×{meta.height}
              </span>
            )}
            {!locked && editing ? (
              <div className="scene-dur-edit">
                <label>Duration</label>
                <input
                  type="number" min="1" max="60" step="0.5"
                  value={duration}
                  onChange={e => setDuration(e.target.value)}
                  className="dur-input"
                />
                <span>s</span>
              </div>
            ) : (
              <span className="scene-dur-badge">⏱ {scene.target_duration_seconds}s</span>
            )}
          </div>
        </div>

        {/* ── Body ─────────────────────────────────────────── */}
        <div className="scene-body">

          {/* LEFT — video */}
          <div className="scene-video-col">
            {brollSrc ? (
              <video className="broll-player" controls muted loop src={brollSrc} />
            ) : (
              <div className="broll-missing">No clip yet</div>
            )}

            {!locked && (
              <button className="btn-replace-broll" onClick={() => setShowPicker(true)}>
                🔍 Replace B-roll
              </button>
            )}
          </div>

          {/* RIGHT — caption + audio */}
          <div className="scene-edit-col">
            <div className="field-group">
              <div className="field-label">🎙 Voiceover</div>
              <textarea
                className="caption-textarea"
                value={caption}
                onChange={e => { setCaption(e.target.value); setEditing(true) }}
                disabled={locked || saving}
                rows={3}
              />
            </div>

            <div className="field-group">
              <div className="field-label">🔍 B-roll prompt</div>
              <textarea
                className="caption-textarea prompt-textarea"
                value={brollPrompt}
                onChange={e => { setBrollPrompt(e.target.value); setEditing(true) }}
                disabled={locked || saving}
                rows={2}
              />
            </div>

            {audioSrc && (
              <div className="field-group">
                <div className="field-label">🔊 Audio preview</div>
                <audio className="audio-player" controls src={audioSrc} />
              </div>
            )}

            {/* Caption editor — always visible; shows approximate timing warning when no timestamps */}
            <CaptionEditor
              scene={scene}
              jobId={jobId}
              onUpdate={onUpdate}
            />

            {editing && !locked && (
              <div className="caption-actions">
                <button className="btn-save" onClick={saveChanges} disabled={saving}>
                  {saving ? 'Saving…' : '💾 Save changes'}
                </button>
                <button className="btn-cancel" onClick={cancelChanges}>Cancel</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
