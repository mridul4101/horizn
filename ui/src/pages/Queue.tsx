import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SlideItem } from '../components/CarouselMockup'

interface CarouselItem {
  id: string
  status: string
  aspect_ratio?: string
  caption?: string
  hashtags?: string[]
  slides: SlideItem[]
}

interface IngestStats {
  total_photos: number
  uncurated_photos: number
  draft_carousels: number
}

export default function Queue() {
  const [carousels, setCarousels] = useState<CarouselItem[]>([])
  const [stats, setStats] = useState<IngestStats>({
    total_photos: 0,
    uncurated_photos: 0,
    draft_carousels: 0,
  })
  const [loading, setLoading] = useState(true)
  const [curating, setCurating] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [syncStatusText, setSyncStatusText] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const navigate = useNavigate()

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/ingest/stats')
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch {
      // stats optional
    }
  }

  const fetchCarousels = async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/carousels?status=draft')
      if (res.ok) {
        const data = await res.json()
        setCarousels(data)
      }
    } catch (err) {
      console.error('Failed to load carousels', err)
    } finally {
      setLoading(false)
    }
  }

  const refreshAll = () => {
    fetchCarousels()
    fetchStats()
  }

  useEffect(() => {
    refreshAll()
  }, [])

  const handleRunCuration = async () => {
    try {
      setCurating(true)
      setMessage('Curating carousels with visual intelligence...')
      const res = await fetch('/api/curate/run', { method: 'POST' })
      if (res.ok) {
        // Poll for completion
        const checkInterval = setInterval(async () => {
          await fetchCarousels()
          await fetchStats()
        }, 1500)

        setTimeout(() => {
          clearInterval(checkInterval)
          refreshAll()
          setCurating(false)
          setMessage('Curation complete!')
          setTimeout(() => setMessage(null), 4000)
        }, 4000)
      } else {
        setMessage('Failed to start curation.')
        setCurating(false)
      }
    } catch {
      setMessage('Error starting curation.')
      setCurating(false)
    }
  }

  const handleRunIngestion = async () => {
    try {
      setIngesting(true)
      setSyncStatusText('Starting library scan…')
      const end = new Date()
      const start = new Date()
      start.setMonth(start.getMonth() - 12)

      const res = await fetch('/api/ingest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          batch_start: start.toISOString(),
          batch_end: end.toISOString(),
        }),
      })

      if (res.ok) {
        const { job_id } = await res.json()

        // Connect to SSE stream for live updates
        const eventSource = new EventSource(`/api/ingest/status/${job_id}`)

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.status === 'running') {
              setSyncStatusText(
                `Scanning photos… (${data.total_scanned} scanned, ${data.passed_filter} passed filter, ${data.exported} exported)`
              )
            } else if (data.status === 'done') {
              setSyncStatusText(null)
              setMessage(
                `✅ Sync complete! ${data.exported} new photos exported and ready for curation.`
              )
              setIngesting(false)
              eventSource.close()
              refreshAll()
              setTimeout(() => setMessage(null), 5000)
            } else if (data.status === 'error') {
              setSyncStatusText(null)
              setMessage(`⚠️ Sync error: ${data.error || 'Unknown error'}`)
              setIngesting(false)
              eventSource.close()
            }
          } catch {
            // parse error
          }
        }

        eventSource.onerror = () => {
          eventSource.close()
          setIngesting(false)
          setSyncStatusText(null)
          refreshAll()
        }
      } else {
        setMessage('Failed to start ingestion.')
        setIngesting(false)
        setSyncStatusText(null)
      }
    } catch {
      setMessage('Error connecting to ingestion service.')
      setIngesting(false)
      setSyncStatusText(null)
    }
  }

  const handleDeleteCarousel = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this carousel draft?')) return
    try {
      const res = await fetch(`/api/carousels/${id}`, { method: 'DELETE' })
      if (res.ok) {
        setCarousels((prev) => prev.filter((c) => c.id !== id))
        fetchStats()
      }
    } catch (err) {
      console.error('Failed to delete carousel', err)
    }
  }

  const handleClearAllDrafts = async () => {
    if (
      !confirm(
        'Are you sure you want to delete ALL draft carousels in the queue? (Your synced photo library remains safe)'
      )
    )
      return
    try {
      const res = await fetch('/api/carousels/drafts/all', { method: 'DELETE' })
      if (res.ok) {
        setCarousels([])
        setMessage('All draft carousels cleared.')
        fetchStats()
        setTimeout(() => setMessage(null), 3000)
      }
    } catch (err) {
      console.error('Failed to clear drafts', err)
    }
  }

  return (
    <div className="queue-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Carousel Queue</h1>
          <p className="page-subtitle">Review, reorder slides, and publish landscape carousels.</p>
        </div>

        <div className="action-buttons">
          {carousels.length > 0 && (
            <button
              className="btn-danger"
              onClick={handleClearAllDrafts}
              title="Delete all drafts in queue"
            >
              Clear All Drafts
            </button>
          )}
          <button className="btn-secondary" onClick={handleRunIngestion} disabled={ingesting}>
            {ingesting ? 'Scanning…' : 'Sync Photos'}
          </button>
          <button className="btn-primary" onClick={handleRunCuration} disabled={curating}>
            {curating ? 'Curating…' : 'Run Curation'}
          </button>
        </div>
      </div>

      {/* Live Stats Bar */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-num">{stats.total_photos}</span>
          <span className="stat-label">Photos in Library</span>
        </div>
        <div className={`stat-item ${stats.uncurated_photos > 0 ? 'highlight-active' : ''}`}>
          <span className="stat-num">{stats.uncurated_photos}</span>
          <span className="stat-label">Awaiting Curation</span>
        </div>
        <div className="stat-item">
          <span className="stat-num">{carousels.length}</span>
          <span className="stat-label">Draft Carousels</span>
        </div>
      </div>

      {/* Progress & Notification Banners */}
      {syncStatusText && <div className="notification-banner syncing">{syncStatusText}</div>}
      {message && <div className="notification-banner">{message}</div>}

      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading draft carousels…</p>
        </div>
      ) : carousels.length === 0 ? (
        stats.uncurated_photos > 0 ? (
          <div className="empty-state ready-state">
            <div className="empty-icon">✨</div>
            <h2>{stats.uncurated_photos} Photos Synced & Ready for Curation!</h2>
            <p>
              Your photos have passed the privacy filter and are waiting to be assembled.
              Click below to group them into intelligent carousels with storytelling order and captions.
            </p>
            <button
              className="btn-primary btn-large"
              onClick={handleRunCuration}
              disabled={curating}
            >
              {curating ? 'Curating Carousels…' : '⚡ Run Curation Now'}
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon">🏞️</div>
            <h2>No Drafts in Queue</h2>
            <p>
              Click <strong>Sync Photos</strong> to scan your photos for landscapes, then click{' '}
              <strong>Run Curation</strong> to group them into intelligent carousels.
            </p>
          </div>
        )
      ) : (
        <div className="carousel-grid">
          {carousels.map((c) => {
            const firstFour = c.slides.slice(0, 4)
            return (
              <div key={c.id} className="carousel-card" onClick={() => navigate(`/editor/${c.id}`)}>
                {/* 2x2 thumbnail preview grid */}
                <div className="card-thumbnails-grid">
                  {firstFour.map((slide, sIdx) => {
                    const filename = slide.export_path ? slide.export_path.split('/').pop() : ''
                    const url = filename ? `/static/${filename}` : ''
                    return url ? (
                      <img
                        key={sIdx}
                        src={url}
                        alt={`Preview ${sIdx + 1}`}
                        className="card-thumb-img"
                      />
                    ) : (
                      <div key={sIdx} className="card-thumb-placeholder" />
                    )
                  })}
                  {firstFour.length < 4 &&
                    Array.from({ length: 4 - firstFour.length }).map((_, padIdx) => (
                      <div key={`pad-${padIdx}`} className="card-thumb-placeholder" />
                    ))}
                </div>

                <div className="card-body">
                  <div className="card-meta">
                    <span className="badge-slides">{c.slides.length} slides</span>
                    <span className="badge-ratio">{c.aspect_ratio || '4:5'}</span>
                    <span className="badge-status">{c.status}</span>
                  </div>

                  <p className="card-caption-preview">
                    {c.caption || 'No caption generated yet.'}
                  </p>

                  <div className="card-actions-row">
                    <button
                      className="btn-card-edit"
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/editor/${c.id}`)
                      }}
                    >
                      Edit & Preview →
                    </button>
                    <button
                      className="btn-card-delete"
                      onClick={(e) => handleDeleteCarousel(c.id, e)}
                      title="Delete this draft"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
