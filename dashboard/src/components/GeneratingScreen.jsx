import { useState, useEffect, useRef } from 'react'

const PHASES = [
  { key: 'queued',               icon: '⏳', label: 'Queued',                    desc: 'Starting up…' },
  { key: 'generating_script',    icon: '✍️', label: 'Writing script',             desc: 'Claude is crafting your video script' },
  { key: 'generating_audio',     icon: '🎙️', label: 'Recording voiceover',        desc: 'ElevenLabs TTS generating audio' },
  { key: 'extracting_timestamps',icon: '⚡', label: 'Syncing captions',           desc: 'Whisper extracting word timestamps' },
  { key: 'downloading_broll',    icon: '🎬', label: 'Downloading B-roll',         desc: 'Fetching clips from Pexels' },
  { key: 'ready_for_review',     icon: '✅', label: 'Ready for review',           desc: 'All done — opening dashboard' },
]

export default function GeneratingScreen({ jobId, topic, niche, nicheInfo, platforms = [], onReady, onFailed, onCancel }) {
  const [progress, setProgress]   = useState(null)
  const [elapsed, setElapsed]     = useState(0)
  const pollRef                   = useRef(null)
  const timerRef                  = useRef(null)
  const readyTimeoutRef           = useRef(null)   // store setTimeout ID for cleanup
  const onReadyRef                = useRef(onReady)
  const onFailedRef               = useRef(onFailed)

  // Keep callback refs current so stale closure doesn't capture old props
  useEffect(() => { onReadyRef.current  = onReady  }, [onReady])
  useEffect(() => { onFailedRef.current = onFailed }, [onFailed])

  // Clamp to valid index; unknown phase strings fall to 0 (not -1)
  const currentPhaseIdx = Math.max(0,
    progress ? PHASES.findIndex(p => p.key === progress.progress_phase) : 0
  )

  useEffect(() => {
    // Elapsed time counter
    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)

    // Poll progress every 2 seconds
    let done = false
    const poll = async () => {
      if (done) return
      try {
        const res = await fetch(`/api/jobs/${jobId}/progress`)
        if (!res.ok) return
        const data = await res.json()
        setProgress(data)

        if (data.ready) {
          done = true
          clearInterval(pollRef.current)
          clearInterval(timerRef.current)
          // Store timeout ID so it can be cancelled on unmount
          readyTimeoutRef.current = setTimeout(() => onReadyRef.current(jobId), 800)
        } else if (data.failed) {
          done = true
          clearInterval(pollRef.current)
          clearInterval(timerRef.current)
          onFailedRef.current(data.progress_detail || 'Pipeline failed')
        }
      } catch (_) { }
    }

    poll()  // immediate first poll
    pollRef.current = setInterval(poll, 2000)

    return () => {
      // Cancel all timers on unmount — prevents bounce-back-to-REVIEW
      clearInterval(pollRef.current)
      clearInterval(timerRef.current)
      clearTimeout(readyTimeoutRef.current)
    }
  }, [jobId])

  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  return (
    <div className="wizard-screen generating-screen">
      {/* Header */}
      <div className="wizard-header">
        <div className="wizard-niche-badge" style={{ background: nicheInfo?.color + '22', borderColor: nicheInfo?.color }}>
          <span>{nicheInfo?.icon}</span>
          <span>{nicheInfo?.label}</span>
          <span className="wizard-platform-tag">{platforms.join(' · ') || 'shorts'}</span>
        </div>
        <h2 className="wizard-title">Generating Your Video</h2>
        <p className="wizard-topic-preview">"{topic}"</p>
        <p className="wizard-elapsed">⏱ {fmt(elapsed)}</p>
      </div>

      {/* Phase steps */}
      <div className="phase-list">
        {PHASES.filter(p => p.key !== 'ready_for_review').map((phase, idx) => {
          const isDone    = idx < currentPhaseIdx
          const isCurrent = idx === currentPhaseIdx
          const isFuture  = idx > currentPhaseIdx
          const isFailed  = progress?.failed && isCurrent

          return (
            <div
              key={phase.key}
              className={`phase-item ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''} ${isFuture ? 'future' : ''} ${isFailed ? 'failed' : ''}`}
            >
              <div className="phase-icon">
                {isDone   ? '✅' :
                 isFailed ? '❌' :
                 isCurrent ? <span className="phase-spinner" /> :
                 phase.icon}
              </div>
              <div className="phase-content">
                <div className="phase-label">{phase.label}</div>
                {isCurrent && (
                  <div className="phase-detail">
                    {progress?.progress_detail || phase.desc}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Ready state */}
      {progress?.ready && (
        <div className="generating-ready">
          <span className="ready-checkmark">✅</span>
          <p>Video ready! Opening review dashboard…</p>
        </div>
      )}

      {/* Cancel button — visible until ready */}
      {!progress?.ready && onCancel && (
        <div style={{ textAlign: 'center', marginTop: '8px' }}>
          <button className="btn-wizard-back" onClick={onCancel}>
            ✕ Cancel &amp; start over
          </button>
        </div>
      )}

      {/* Tip */}
      {!progress?.ready && !progress?.failed && (
        <div className="generating-tip">
          💡 This takes about 60–90 seconds. The pipeline is fully automatic.
        </div>
      )}
    </div>
  )
}
