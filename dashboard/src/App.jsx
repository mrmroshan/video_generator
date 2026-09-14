import { useState, useEffect } from 'react'
import JobList from './components/JobList.jsx'
import JobReview from './components/JobReview.jsx'
import './App.css'

export default function App() {
  const [jobs, setJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchJobs = async () => {
    try {
      const res = await fetch('/api/jobs')
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const data = await res.json()
      setJobs(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleSelectJob = async (jobId) => {
    const res = await fetch(`/api/jobs/${jobId}`)
    const job = await res.json()
    setSelectedJob(job)
  }

  const handleBack = () => {
    setSelectedJob(null)
    fetchJobs()
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="logo">🎬 Video Maker</span>
          <span className="subtitle">Review Dashboard</span>
        </div>
      </header>

      <main className="app-main">
        {error && <div className="error-banner">⚠️ {error} — is the API server running?</div>}

        {selectedJob ? (
          <JobReview
            job={selectedJob}
            onBack={handleBack}
            onUpdate={setSelectedJob}
          />
        ) : (
          <JobList
            jobs={jobs}
            loading={loading}
            onSelect={handleSelectJob}
          />
        )}
      </main>
    </div>
  )
}
