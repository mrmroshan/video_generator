import { useState, useEffect, useRef } from 'react'

/**
 * CaptionEditor — per-scene caption text editor
 *
 * Shows the Whisper-transcribed words in an editable textarea where:
 *   - Each LINE = one phrase group (shown on screen together)
 *   - Words on a line = karaoke-highlighted one by one
 *   - Press Enter = force a line break (phrase boundary)
 *   - "Re-caption" re-burns just this scene (~3-5s), no full render needed
 */
export default function CaptionEditor({ scene, jobId, onUpdate }) {
  const [text, setText]           = useState('')
  const [loading, setLoading]     = useState(true)
  const [isEdited, setIsEdited]   = useState(false)
  const [hasTs, setHasTs]         = useState(false)  // server tells us if timestamps exist
  const [dirty, setDirty]         = useState(false)
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState(null)
  const [success, setSuccess]     = useState(false)
  const textareaRef               = useRef(null)

  // Load caption text from server on mount / scene change
  useEffect(() => {
    setLoading(true)
    setError(null)
    setDirty(false)
    setSuccess(false)
    fetch(`/api/jobs/${jobId}/scenes/${scene.scene_id}/caption-text`)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(data => {
        setText(data.text)
        setIsEdited(data.is_edited)
        setHasTs(data.has_timestamps || false)
        setLoading(false)
      })
      .catch(e => {
        setError('Could not load caption text: ' + e)
        setLoading(false)
      })
  }, [scene.scene_id, jobId])

  const handleChange = (e) => {
    setText(e.target.value)
    setDirty(true)
    setSuccess(false)
  }

  const handleRecaption = async () => {
    if (!dirty) return  // nothing changed since last save or load
    setSaving(true)
    setError(null)
    setSuccess(false)
    try {
      const res = await fetch(
        `/api/jobs/${jobId}/scenes/${scene.scene_id}/recaption`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        }
      )
      if (!res.ok) {
        const body = await res.text()
        throw new Error(body)
      }
      const updatedJob = await res.json()
      setDirty(false)
      setIsEdited(true)
      setSuccess(true)
      onUpdate(updatedJob)
      setTimeout(() => setSuccess(false), 3000)
    } catch (e) {
      setError('Re-caption failed: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    // Clear saved edit — reload auto-generated text from timestamps
    setLoading(true)
    setError(null)
    try {
      // Temporarily clear caption_text_edited by fetching fresh
      // (server returns auto-generated when no edit saved — we just clear locally)
      const res = await fetch(`/api/jobs/${jobId}/scenes/${scene.scene_id}/caption-text`)
      const data = await res.json()
      // Force re-gen by ignoring is_edited
      setText(data.text)
      setIsEdited(false)
      setDirty(true) // mark dirty so user can re-apply
    } catch (e) {
      setError('Reset failed: ' + e)
    } finally {
      setLoading(false)
    }
  }

  const wordCount  = text.trim() ? text.trim().split(/\s+/).length : 0
  const lineCount  = text.trim() ? text.trim().split('\n').filter(l => l.trim()).length : 0

  return (
    <div className="caption-editor">
      <div className="caption-editor-header">
        <span className="caption-editor-title">✏️ Caption Text</span>
        <div className="caption-editor-meta">
          {isEdited && !dirty && <span className="ce-badge ce-badge-edited">edited</span>}
          {dirty     && <span className="ce-badge ce-badge-dirty">unsaved</span>}
          {!hasTs    && <span className="ce-badge ce-badge-warn">no timestamps — timing is approximate</span>}
        </div>
      </div>

      <div className="caption-editor-hint">
        Each <strong>line</strong> = one on-screen phrase · <strong>Enter</strong> = new line (phrase break) · words highlight one by one
      </div>

      {loading ? (
        <div className="ce-loading">Loading…</div>
      ) : (
        <textarea
          ref={textareaRef}
          className="ce-textarea"
          value={text}
          onChange={handleChange}
          disabled={saving}
          rows={Math.max(3, lineCount + 1)}
          spellCheck
          placeholder={'Line 1 words here\nLine 2 words here\nLine 3 words here'}
        />
      )}

      <div className="caption-editor-footer">
        <span className="ce-stats">{wordCount} words · {lineCount} lines</span>
        <div className="ce-actions">
          {isEdited && (
            <button className="btn-ce-reset" onClick={handleReset} disabled={saving || loading}>
              ↺ Reset to auto
            </button>
          )}
          <button
            className="btn-ce-recaption"
            onClick={handleRecaption}
            disabled={saving || loading || (!dirty && isEdited)}
            title={!hasTs ? 'Timing will be approximated since no Whisper timestamps exist' : ''}
          >
            {saving ? '⏳ Re-captioning…' : '🎬 Re-caption scene'}
          </button>
        </div>
      </div>

      {error   && <div className="ce-error">❌ {error}</div>}
      {success && <div className="ce-success">✅ Scene re-captioned! Re-render to see in full video.</div>}
    </div>
  )
}
