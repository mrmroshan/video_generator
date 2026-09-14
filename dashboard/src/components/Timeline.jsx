import { useState, useRef, useEffect } from 'react'

const PIXELS_PER_SECOND = 80  // 1s = 80px on timeline

export default function Timeline({ job, activeSceneId, onSelectScene, onReorder, onJobUpdate, locked }) {
  const scenes = job?.scenes || []
  const totalDuration = scenes.reduce((s, sc) => s + (sc.target_duration_seconds || 0), 0)
  const totalWidth = Math.max(totalDuration * PIXELS_PER_SECOND, 600)

  const [dragIdx, setDragIdx]     = useState(null)
  const [dragOver, setDragOver]   = useState(null)
  const [editingDur, setEditingDur] = useState(null)  // scene_id being edited
  const [durValue, setDurValue]   = useState('')
  const containerRef = useRef(null)

  // Scroll active scene into view on the timeline
  useEffect(() => {
    if (!activeSceneId || !containerRef.current) return
    const el = containerRef.current.querySelector(`[data-scene="${activeSceneId}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  }, [activeSceneId])

  // ── Drag-to-reorder ────────────────────────────────────────────────
  const handleDragStart = (e, idx) => {
    if (locked) return
    setDragIdx(idx)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', idx)
  }
  const handleDragOver = (e, idx) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(idx)
  }
  const handleDrop = (e, idx) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === idx) { setDragIdx(null); setDragOver(null); return }
    const newOrder = [...scenes]
    const [moved] = newOrder.splice(dragIdx, 1)
    newOrder.splice(idx, 0, moved)
    setDragIdx(null)
    setDragOver(null)
    onReorder(newOrder.map(s => s.scene_id))
  }
  const handleDragEnd = () => { setDragIdx(null); setDragOver(null) }

  // ── Duration inline edit ───────────────────────────────────────────
  const startEditDur = (scene) => {
    if (locked) return
    setEditingDur(scene.scene_id)
    setDurValue(String(scene.target_duration_seconds))
  }
  const commitDur = async (scene) => {
    const val = parseFloat(durValue)
    if (!isNaN(val) && val >= 1 && val <= 60) {
      try {
        const r = await fetch(`/api/jobs/${job.job_id}/scenes/${scene.scene_id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_duration_seconds: val }),
        })
        if (!r.ok) throw new Error(await r.text())
        const updated = await r.json()
        if (onJobUpdate) onJobUpdate(updated)
      } catch (e) {
        alert('Duration save failed: ' + e.message)
      }
    }
    setEditingDur(null)
  }

  // ── Ruler ticks ───────────────────────────────────────────────────
  const ticks = []
  for (let t = 0; t <= totalDuration; t += 1) {
    ticks.push(t)
  }

  // ── Cumulative offset for each scene ──────────────────────────────
  const offsets = []
  let acc = 0
  for (const sc of scenes) {
    offsets.push(acc)
    acc += sc.target_duration_seconds || 0
  }

  return (
    <div className="timeline-wrapper">
      <div className="timeline-label">
        <span>⏱ Timeline</span>
        <span className="timeline-total">{totalDuration.toFixed(1)}s total</span>
        {!locked && <span className="timeline-hint">drag to reorder · double-click duration to edit</span>}
      </div>

      <div className="timeline-scroll" ref={containerRef}>
        <div className="timeline-track" style={{ width: totalWidth + 80 }}>

          {/* Ruler */}
          <div className="timeline-ruler">
            {ticks.map(t => (
              <div
                key={t}
                className={`ruler-tick ${t % 5 === 0 ? 'major' : 'minor'}`}
                style={{ left: t * PIXELS_PER_SECOND }}
              >
                {t % 5 === 0 && <span className="ruler-label">{t}s</span>}
              </div>
            ))}
          </div>

          {/* Scene blocks */}
          <div className="timeline-scenes">
            {scenes.map((scene, idx) => {
              const width = (scene.target_duration_seconds || 4) * PIXELS_PER_SECOND
              const left  = offsets[idx] * PIXELS_PER_SECOND
              const isActive = scene.scene_id === activeSceneId
              const isDragging = dragIdx === idx
              const isOver = dragOver === idx

              return (
                <div
                  key={scene.scene_id}
                  data-scene={scene.scene_id}
                  className={[
                    'timeline-scene',
                    isActive   ? 'timeline-scene--active'   : '',
                    isDragging ? 'timeline-scene--dragging' : '',
                    isOver     ? 'timeline-scene--dragover' : '',
                  ].join(' ')}
                  style={{ left, width }}
                  draggable={!locked}
                  onDragStart={e => handleDragStart(e, idx)}
                  onDragOver={e => handleDragOver(e, idx)}
                  onDrop={e => handleDrop(e, idx)}
                  onDragEnd={handleDragEnd}
                  onClick={() => onSelectScene(scene.scene_id)}
                >
                  {/* Video thumbnail */}
                  {scene.broll_path && (
                    <video
                      className="timeline-thumb"
                      src={`/api/jobs/${job.job_id}/scenes/${scene.scene_id}/broll`}
                      muted
                      preload="metadata"
                      onLoadedMetadata={e => { e.target.currentTime = 1 }}
                    />
                  )}

                  {/* Overlay content */}
                  <div className="timeline-scene-overlay">
                    <div className="timeline-scene-num">{idx + 1}</div>

                    <div className="timeline-scene-text">
                      {scene.voiceover_text?.slice(0, 60)}{scene.voiceover_text?.length > 60 ? '…' : ''}
                    </div>

                    <div className="timeline-scene-footer">
                      {editingDur === scene.scene_id ? (
                        <input
                          className="timeline-dur-input"
                          value={durValue}
                          onChange={e => setDurValue(e.target.value)}
                          onBlur={() => commitDur(scene)}
                          onKeyDown={e => { if (e.key === 'Enter') commitDur(scene); if (e.key === 'Escape') setEditingDur(null) }}
                          autoFocus
                          onClick={e => e.stopPropagation()}
                          style={{ width: 44 }}
                        />
                      ) : (
                        <span
                          className="timeline-dur"
                          onDoubleClick={e => { e.stopPropagation(); startEditDur(scene) }}
                          title="Double-click to edit duration"
                        >
                          {scene.target_duration_seconds}s
                        </span>
                      )}
                      {!locked && <span className="drag-handle" title="Drag to reorder">⠿</span>}
                    </div>
                  </div>
                </div>
              )
            })}

            {/* Playhead line at 0 */}
            <div className="timeline-playhead" />
          </div>
        </div>
      </div>
    </div>
  )
}
