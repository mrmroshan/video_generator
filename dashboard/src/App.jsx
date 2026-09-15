import { useState, useEffect } from 'react'
import JobList from './components/JobList.jsx'
import JobReview from './components/JobReview.jsx'
import NicheWizard from './components/NicheWizard.jsx'
import TopicPicker from './components/TopicPicker.jsx'
import GeneratingScreen from './components/GeneratingScreen.jsx'
import './App.css'

// Wizard steps
const STEP = { LIST: 'list', NICHE: 'niche', TOPIC: 'topic', GENERATING: 'generating', REVIEW: 'review' }

export default function App() {
  const [jobs, setJobs]               = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [step, setStep]               = useState(STEP.LIST)

  // Wizard state
  const [niches, setNiches]           = useState({})
  const [nicheError, setNicheError]   = useState(null)
  const [wizardNiche, setWizardNiche] = useState(null)
  // Persist platform across wizard sessions so TikTok creators don't re-toggle every time
  const [wizardPlatform, setPlatform] = useState('youtube')
  const [generatingJob, setGenJob]    = useState(null)  // {jobId, topic, niche, platform}
  const [wizardError, setWizardError] = useState(null)
  const [createLoading, setCreateLoading] = useState(false)

  // ── Data fetching ────────────────────────────────────────────────────
  const fetchJobs = async () => {
    try {
      const res = await fetch('/api/jobs')
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      setJobs(await res.json())
      setError(null)
    } catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  const fetchNiches = async () => {
    try {
      const res = await fetch('/api/niches')
      if (!res.ok) throw new Error(`API ${res.status}`)
      setNiches((await res.json()).niches || {})
      setNicheError(null)
    } catch (e) {
      setNicheError('Could not load niches: ' + e.message)
    }
  }

  useEffect(() => {
    fetchJobs()
    fetchNiches()
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [])

  // ── Navigation ───────────────────────────────────────────────────────
  const handleSelectJob = async (jobId) => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`)
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      setSelectedJob(await res.json())
      setStep(STEP.REVIEW)
      setError(null)
    } catch (e) { setError(e.message) }
  }

  const handleBack = () => {
    setSelectedJob(null)
    setStep(STEP.LIST)
    fetchJobs()
  }

  // ── Wizard handlers ──────────────────────────────────────────────────
  const handleNewVideo = () => {
    setWizardError(null)
    setStep(STEP.NICHE)
  }

  const handleNicheSelect = (nicheKey, platform) => {
    setWizardNiche(nicheKey)
    setPlatform(platform)
    setStep(STEP.TOPIC)
  }

  const handleTopicSelect = async (params) => {
    setWizardError(null)
    setCreateLoading(true)
    try {
      const res = await fetch('/api/jobs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      if (!res.ok) throw new Error(await res.text())
      const { job_id } = await res.json()
      setGenJob({
        jobId:    job_id,
        topic:    params.topic_title,
        niche:    params.niche,
        platform: params.platform,
      })
      setStep(STEP.GENERATING)
    } catch (e) {
      setWizardError('Failed to start pipeline: ' + e.message)
    } finally {
      setCreateLoading(false)
    }
  }

  const handleGeneratingReady = async (jobId) => {
    await handleSelectJob(jobId)
    fetchJobs()
  }

  const handleGeneratingFailed = (detail) => {
    setGenJob(null)
    setWizardError(`Pipeline failed: ${detail}`)
    setStep(STEP.NICHE)
  }

  const handleGeneratingCancel = () => {
    // Navigate away — background job continues but user can start over
    setGenJob(null)
    setWizardError(null)
    setStep(STEP.NICHE)
  }

  // ── Render ───────────────────────────────────────────────────────────
  const isWizardActive = [STEP.NICHE, STEP.TOPIC, STEP.GENERATING].includes(step)

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="logo" style={{cursor:'pointer'}} onClick={handleBack}>🎬 Video Maker</span>
          <span className="subtitle">AI Video Pipeline</span>
        </div>
        {step === STEP.LIST && (
          <button className="btn-new-video" onClick={handleNewVideo}>
            + New Video
          </button>
        )}
        {isWizardActive && (
          <button className="btn-new-video" style={{ background: 'none', border: '1px solid #333', color: '#888' }}
            onClick={handleBack}>
            ✕ Cancel
          </button>
        )}
      </header>

      <main className="app-main">
        {error && <div className="error-banner">⚠️ {error} — is the API server running?</div>}
        {wizardError && (
          <div className="error-banner">
            ⚠️ {wizardError}
            <button className="btn-dismiss" onClick={() => setWizardError(null)}>✕</button>
          </div>
        )}

        {step === STEP.LIST && (
          <JobList jobs={jobs} loading={loading} onSelect={handleSelectJob} />
        )}

        {step === STEP.NICHE && (
          <NicheWizard
            niches={niches}
            defaultPlatform={wizardPlatform}
            onSelect={handleNicheSelect}
            onBack={handleBack}
          />
        )}

        {step === STEP.TOPIC && (
          <TopicPicker
            niche={wizardNiche}
            nicheInfo={niches[wizardNiche]}
            platform={wizardPlatform}
            createLoading={createLoading}
            wizardError={wizardError}
            onSelect={handleTopicSelect}
            onBack={() => setStep(STEP.NICHE)}
          />
        )}

        {step === STEP.GENERATING && generatingJob && (
          <GeneratingScreen
            jobId={generatingJob.jobId}
            topic={generatingJob.topic}
            niche={generatingJob.niche}
            nicheInfo={niches[generatingJob.niche]}
            platform={generatingJob.platform}
            onReady={handleGeneratingReady}
            onFailed={handleGeneratingFailed}
            onCancel={handleGeneratingCancel}
          />
        )}

        {step === STEP.REVIEW && selectedJob && (
          <JobReview
            job={selectedJob}
            onBack={handleBack}
            onUpdate={setSelectedJob}
          />
        )}
      </main>
    </div>
  )
}
