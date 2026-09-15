import { formatDistanceToNow } from '../utils/time.js'

const STATUS_LABELS = {
  pending: 'Pending',
  generating_assets: 'Generating',
  in_review: 'In Review',
  draft: 'Draft',
  approved: 'Approved',
  rendering: 'Rendering',
  distributing: 'Distributing',
  done: 'Done',
  failed: 'Failed',
}

export default function JobList({ jobs, loading, onSelect }) {
  if (loading) return <div className="loading-state">Loading jobs…</div>

  if (!jobs.length) return (
    <div className="empty-state">
      <p>No jobs yet.</p>
      <p>Run the pipeline to create one:</p>
      <code>python pipeline.py --topic "your topic" --platform tiktok</code>
    </div>
  )

  return (
    <div>
      <div className="job-list-header">
        <h2>Jobs</h2>
        <div className="job-count">{jobs.length} total</div>
      </div>

      <div className="job-grid">
        {jobs.map(job => (
          <div key={job.job_id} className="job-card" onClick={() => onSelect(job.job_id)}>
            <div className="job-card-title">{job.title || job.job_id}</div>
            <div className="job-card-meta">
              <span>
                <span className={`status-badge status-${job.status}`}>
                  {STATUS_LABELS[job.status] || job.status}
                </span>
              </span>
              <span>📱 {job.platform}</span>
              <span>🎬 {job.scenes?.length || 0} scenes</span>
              <span>🕐 {formatDistanceToNow(job.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
