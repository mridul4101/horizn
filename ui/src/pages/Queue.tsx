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
  alternate_photos?: number
  draft_carousels: number
}

export default function Queue() {
  const [carousels, setCarousels] = useState<CarouselItem[]>([])
  const [stats, setStats] = useState<IngestStats>({
    total_photos: 0,
    uncurated_photos: 0,
    alternate_photos: 0,
    draft_carousels: 0,
  })
  const [loading, setLoading] = useState(true)
  const [curating, setCurating] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [syncStatusText, setSyncStatusText] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [showClearModal, setShowClearModal] = useState(false)
  const [showSyncModal, setShowSyncModal] = useState(false)
  const [syncRangeType, setSyncRangeType] = useState<'12months' | 'all' | 'custom'>('12months')
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')
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

  const startIngestionWithRange = async () => {
    setShowSyncModal(false)
    try {
      setIngesting(true)
      setSyncStatusText('Starting library scan…')

      let payload: { batch_start?: string; batch_end?: string } = {}

      if (syncRangeType === '12months') {
        const end = new Date()
        const start = new Date()
        start.setMonth(start.getMonth() - 12)
        payload = { batch_start: start.toISOString(), batch_end: end.toISOString() }
      } else if (syncRangeType === 'all') {
        payload = { batch_start: new Date(0).toISOString(), batch_end: new Date().toISOString() }
      } else if (syncRangeType === 'custom') {
        if (!customStartDate || !customEndDate) {
          alert('Please select both start and end dates.')
          setIngesting(false)
          setSyncStatusText(null)
          return
        }
        payload = {
          batch_start: new Date(customStartDate).toISOString(),
          batch_end: new Date(`${customEndDate}T23:59:59`).toISOString(),
        }
      }

      const res = await fetch('/api/ingest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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

  const confirmClearDrafts = async (deleteFromLibrary: boolean) => {
    try {
      const res = await fetch(
        `/api/carousels/drafts/all?delete_from_library=${deleteFromLibrary}`,
        { method: 'DELETE' }
      )
      if (res.ok) {
        setCarousels([])
        setMessage(
          deleteFromLibrary
            ? 'All drafts and underlying photos deleted from library.'
            : 'All drafts cleared. Photos remain safe in library awaiting curation.'
        )
        fetchStats()
        setTimeout(() => setMessage(null), 3500)
      } else {
        const err = await res.json().catch(() => ({}))
        setMessage(`⚠️ Failed to clear drafts: ${err.detail || 'Server error'}`)
        setTimeout(() => setMessage(null), 4000)
      }
    } catch (err: any) {
      console.error('Failed to clear drafts', err)
      setMessage(`⚠️ Network error: ${err.message || 'Could not connect'}`)
      setTimeout(() => setMessage(null), 4000)
    } finally {
      setShowClearModal(false)
    }
  }

  const handleClearAllDrafts = () => {
    setShowClearModal(true)
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
          <button className="btn-secondary" onClick={() => setShowSyncModal(true)} disabled={ingesting}>
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
        {(stats.alternate_photos ?? 0) > 0 && (
          <div
            className="stat-item"
            title="Burst and alternate shots grouped with hero photos. Preserved in library, excluded from automated carousels."
          >
            <span className="stat-num">{stats.alternate_photos}</span>
            <span className="stat-label">Alternates / Bursts</span>
          </div>
        )}
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

      {/* Clear All Drafts Modal */}
      {showClearModal && (
        <div className="modal-backdrop" onClick={() => setShowClearModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Clear All Drafts</h3>
            <p className="modal-desc">
              How would you like to clear the draft queue?
            </p>

            <div className="modal-options-list">
              <button
                type="button"
                className="modal-option-btn primary-option"
                onClick={() => confirmClearDrafts(false)}
              >
                <div className="option-headline">Clear Drafts Only (Keep Photos)</div>
                <div className="option-subtext">
                  Deletes all draft carousels but keeps all {stats.total_photos} photos safe in your library awaiting future curation.
                </div>
              </button>

              <button
                type="button"
                className="modal-option-btn danger-option"
                onClick={() => confirmClearDrafts(true)}
              >
                <div className="option-headline">🗑️ Clear Drafts & Delete Photos from Library</div>
                <div className="option-subtext">
                  Permanently deletes all draft carousels and removes all draft photos from the library.
                </div>
              </button>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowClearModal(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sync Photos Range Modal */}
      {showSyncModal && (
        <div className="modal-backdrop" onClick={() => setShowSyncModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Sync Photos</h3>
            <p className="modal-desc">
              Choose which photos to scan through the privacy filter:
            </p>

            <div className="modal-options-list">
              <button
                type="button"
                className={`modal-option-btn ${syncRangeType === '12months' ? 'active-option' : ''}`}
                onClick={() => setSyncRangeType('12months')}
              >
                <div className="option-headline">📅 Last 12 Months (Default)</div>
                <div className="option-subtext">Scans recent photos from the past 12 months up to today.</div>
              </button>

              <button
                type="button"
                className={`modal-option-btn ${syncRangeType === 'all' ? 'active-option' : ''}`}
                onClick={() => setSyncRangeType('all')}
              >
                <div className="option-headline">🌍 All Time</div>
                <div className="option-subtext">Scans every photo from the beginning of your library.</div>
              </button>

              <button
                type="button"
                className={`modal-option-btn ${syncRangeType === 'custom' ? 'active-option' : ''}`}
                onClick={() => setSyncRangeType('custom')}
              >
                <div className="option-headline">📆 Custom Date Range</div>
                <div className="option-subtext">Target a specific vacation or timeframe in the past.</div>
              </button>

              {syncRangeType === 'custom' && (
                <div className="custom-date-inputs">
                  <div className="date-field">
                    <label>Start Date</label>
                    <input
                      type="date"
                      value={customStartDate}
                      onChange={(e) => setCustomStartDate(e.target.value)}
                    />
                  </div>
                  <div className="date-field">
                    <label>End Date</label>
                    <input
                      type="date"
                      value={customEndDate}
                      onChange={(e) => setCustomEndDate(e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowSyncModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={startIngestionWithRange}
              >
                Start Sync
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
