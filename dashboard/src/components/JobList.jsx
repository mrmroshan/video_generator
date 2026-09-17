import { formatDistanceToNow } from '../utils/time.js'

const STATUS_LABELS = {
  pending:           'Pending',
  generating_assets: 'Generating',
  in_review:         'In Review',
  draft:             'Draft',
  approved:          'Approved',
  rendering:         'Rendering',
  distributing:      'Distributing',
  done:              'Done ✓',
  failed:            'Failed',
}

const STATUS_ICON = {
  pending:           '⏳',
  generating_assets: '⚙️',
  in_review:         '👁',
  draft:             '📝',
  approved:          '✅',
  rendering:         '🎬',
  distributing:      '📤',
  done:              '✅',
  failed:            '❌',
}

const NICHE_ICON = {
  finance:'💰', entrepreneurship:'🚀', health:'💪', tech:'💻',
  mindset:'🧠', productivity:'⚡', ai:'🤖', marketing:'📣',
  relationships:'❤️', fitness:'🏋️',
}

// Human-readable label for a format key
const FMT_LABEL = {
  tiktok:             'TikTok',
  youtube_shorts:     'YT Shorts',
  youtube:            'YouTube',
  instagram_reels:    'IG Reels',
  instagram_square:   'IG Square',
  instagram_portrait: 'IG Portrait',
  instagram:          'Instagram',
  facebook_reels:     'FB Reels',
  facebook_square:    'FB Square',
  facebook:           'Facebook',
}

export default function JobList({ jobs, loading, onSelect }) {
  if (loading) return <div className="loading-state">Loading jobs…</div>

  if (!jobs.length) return (
    <div className="empty-state">
      <div className="empty-state-icon">🎬</div>
      <p>No videos yet.</p>
      <p className="empty-state-sub">Hit <strong>+ New Video</strong> to generate your first one.</p>
    </div>
  )

  return (
    <div>
      <div className="job-list-header">
        <h2>Videos</h2>
        <div className="job-count">{jobs.length} job{jobs.length !== 1 ? 's' : ''}</div>
      </div>

      <div className="job-grid">
        {jobs.map(job => {
          const title   = job.topic || job.title || job.job_id
          const niche   = job.niche   || ''
          const status  = job.status  || 'pending'
          const scenes  = job.scenes?.length || 0
          const formats = job.formats?.length
            ? job.formats
            : job.platforms || [job.platform].filter(Boolean)
          const isShort = title.length < 40

          return (
            <div
              key={job.job_id}
              className={`job-card status-card-${status}`}
              onClick={() => onSelect(job.job_id)}
            >
              {/* Top row: status badge + time */}
              <div className="job-card-top">
                <span className={`status-badge status-${status}`}>
                  {STATUS_ICON[status]} {STATUS_LABELS[status] || status}
                </span>
                <span className="job-card-time">{formatDistanceToNow(job.created_at)}</span>
              </div>

              {/* Title */}
              <div className={`job-card-title${isShort ? ' title-lg' : ''}`}>{title}</div>

              {/* Niche + scenes row */}
              <div className="job-card-sub">
                {niche && (
                  <span className="job-niche-tag">
                    {NICHE_ICON[niche] || '🎯'} {niche}
                  </span>
                )}
                <span className="job-scenes-tag">
                  🎞 {scenes} scene{scenes !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Format pills */}
              {formats.length > 0 && (
                <div className="job-format-pills">
                  {formats.slice(0, 4).map(f => (
                    <span key={f} className="job-fmt-pill">
                      {FMT_LABEL[f] || f}
                    </span>
                  ))}
                  {formats.length > 4 && (
                    <span className="job-fmt-pill job-fmt-more">+{formats.length - 4}</span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
