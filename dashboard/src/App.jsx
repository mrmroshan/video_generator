import { useState, useEffect } from 'react'
import JobList from './components/JobList.jsx'
import JobReview from './components/JobReview.jsx'
import NicheWizard from './components/NicheWizard.jsx'
import TopicPicker from './components/TopicPicker.jsx'
import GeneratingScreen from './components/GeneratingScreen.jsx'
import Projects from './components/Projects.jsx'
import TopicBank from './components/TopicBank.jsx'
import './App.css'

// Wizard steps
const STEP = { LIST: 'list', NICHE: 'niche', TOPIC: 'topic', GENERATING: 'generating', REVIEW: 'review', PROJECTS: 'projects', TOPICBANK: 'topicbank' }

export default function App() {
  const [jobs, setJobs]               = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [step, setStep]               = useState(STEP.LIST)
  const [activeProject, setActiveProject] = useState(null)

  // Wizard state
  const [niches, setNiches]             = useState({})
  const [nicheError, setNicheError]     = useState(null)
  const [wizardNiche, setWizardNiche]   = useState(null)
  // Persist platform + format selection across wizard sessions
  const [wizardPlatforms, setWizardPlatforms] = useState(['tiktok','instagram','youtube','facebook'])
  const [wizardFormats, setWizardFormats]     = useState([])
  const [wizardBrollSource, setWizardBrollSource] = useState('pexels')
  const [wizardCaptionStyle, setWizardCaptionStyle] = useState('none')
  const [generatingJob, setGenJob]      = useState(null)
  const [wizardError, setWizardError]   = useState(null)
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

  const handleNicheSelect = (nicheKey, platforms, brollSource = 'pexels', formats = [], captionStyle = 'none') => {
    setWizardNiche(nicheKey)
    setWizardPlatforms(platforms)
    setWizardFormats(formats)
    setWizardBrollSource(brollSource)
    setWizardCaptionStyle(captionStyle)
    setStep(STEP.TOPIC)
  }

  const handleTopicSelect = async (params) => {
    setWizardError(null)
    setCreateLoading(true)
    try {
      const res = await fetch('/api/jobs/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, broll_source: wizardBrollSource, formats: wizardFormats, caption_style: wizardCaptionStyle }),
      })
      if (!res.ok) throw new Error(await res.text())
      const { job_id } = await res.json()
      setGenJob({
        jobId:       job_id,
        topic:       params.topic_title,
        niche:       params.niche,
        platforms:   params.platforms,
        brollSource: wizardBrollSource,
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
  const isTopLevel     = [STEP.LIST, STEP.PROJECTS].includes(step)

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="logo" style={{cursor:'pointer'}} onClick={() => setStep(STEP.LIST)}>🎬 Video Maker</span>
          <span className="subtitle">AI Video Pipeline</span>
        </div>

        {/* Top-level nav tabs */}
        {isTopLevel && (
          <nav className="header-tabs">
            <button
              className={`header-tab${step === STEP.LIST ? ' active' : ''}`}
              onClick={() => setStep(STEP.LIST)}
            >Videos</button>
            <button
              className={`header-tab${step === STEP.PROJECTS ? ' active' : ''}`}
              onClick={() => setStep(STEP.PROJECTS)}
            >Projects</button>
          </nav>
        )}

        {isTopLevel && step === STEP.LIST && (
          <button className="btn-new-video" onClick={handleNewVideo}>+ New Video</button>
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
            defaultPlatforms={wizardPlatforms}
            onSelect={handleNicheSelect}
            onBack={handleBack}
          />
        )}

        {step === STEP.TOPIC && (
          <TopicPicker
            niche={wizardNiche}
            nicheInfo={niches[wizardNiche]}
            platforms={wizardPlatforms}
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
            platforms={generatingJob.platforms}
            brollSource={generatingJob.brollSource}
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

        {step === STEP.PROJECTS && (
          <Projects
            onOpenProject={(project) => {
              setActiveProject(project)
              setStep(STEP.TOPICBANK)
            }}
          />
        )}

        {step === STEP.TOPICBANK && activeProject && (
          <TopicBank
            project={activeProject}
            onBack={() => setStep(STEP.PROJECTS)}
            onStartVideo={(jobId) => {
              // Navigate to the new job's review screen directly
              handleSelectJob(jobId)
            }}
          />
        )}
      </main>
    </div>
  )
}
