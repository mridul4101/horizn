import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface PhotoItem {
  id: string
  filepath: string
  export_path?: string
  taken_at?: string
  lat?: number
  lon?: number
  sharpness?: number
  aspect_ratio?: string
  is_landscape: number
  ingested_at?: string
  carousel_id?: string
  duplicate_of?: string
  alternate_count?: number
  status: 'awaiting_curation' | 'in_carousel' | 'published' | 'duplicate' | 'excluded'
}

export default function Library() {
  const [photos, setPhotos] = useState<PhotoItem[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'awaiting' | 'in_carousel' | 'published' | 'duplicate'>('all')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [creatingCarousel, setCreatingCarousel] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const navigate = useNavigate()

  const fetchPhotos = async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/photos')
      if (res.ok) {
        const data = await res.json()
        setPhotos(data)
      }
    } catch (err) {
      console.error('Failed to load photos', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPhotos()
  }, [])

  const filteredPhotos = photos.filter((p) => {
    if (filter === 'awaiting') return p.status === 'awaiting_curation'
    if (filter === 'in_carousel') return p.status === 'in_carousel'
    if (filter === 'published') return p.status === 'published'
    if (filter === 'duplicate') return p.status === 'duplicate'
    return true
  })

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        if (next.size >= 10) {
          alert('Instagram carousels support a maximum of 10 photos.')
          return next
        }
        next.add(id)
      }
      return next
    })
  }

  const selectAllFiltered = () => {
    const toSelect = filteredPhotos.slice(0, 10).map((p) => p.id)
    setSelectedIds(new Set(toSelect))
  }

  const clearSelection = () => {
    setSelectedIds(new Set())
  }

  const handleDeleteSingle = async (photoId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Are you sure you want to delete this photo from your library?')) return
    try {
      const res = await fetch(`/api/photos/${photoId}`, { method: 'DELETE' })
      if (res.ok) {
        setPhotos((prev) => prev.filter((p) => p.id !== photoId))
        setSelectedIds((prev) => {
          const next = new Set(prev)
          next.delete(photoId)
          return next
        })
      }
    } catch (err) {
      console.error('Failed to delete photo', err)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm(`Delete ${selectedIds.size} selected photo(s) from your library?`)) return
    try {
      const res = await fetch('/api/photos/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_ids: Array.from(selectedIds) }),
      })
      if (res.ok) {
        setPhotos((prev) => prev.filter((p) => !selectedIds.has(p.id)))
        setSelectedIds(new Set())
        setMessage('Selected photos deleted from library.')
        setTimeout(() => setMessage(null), 3000)
      }
    } catch (err) {
      console.error('Failed batch delete', err)
    }
  }

  const handleCreateManualCarousel = async () => {
    if (selectedIds.size === 0) return
    try {
      setCreatingCarousel(true)
      setMessage('AI is ordering slides narratively and drafting captions…')

      const res = await fetch('/api/carousels/manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_ids: Array.from(selectedIds) }),
      })

      if (res.ok) {
        const carousel = await res.json()
        navigate(`/editor/${carousel.id}`)
      } else {
        const err = await res.json()
        alert(err.detail || 'Failed to create carousel.')
        setCreatingCarousel(false)
        setMessage(null)
      }
    } catch {
      alert('Error creating manual carousel.')
      setCreatingCarousel(false)
      setMessage(null)
    }
  }

  const countAwaiting = photos.filter((p) => p.status === 'awaiting_curation').length
  const countInCarousel = photos.filter((p) => p.status === 'in_carousel').length
  const countPublished = photos.filter((p) => p.status === 'published').length
  const countDuplicates = photos.filter((p) => p.status === 'duplicate').length

  return (
    <div className="library-page">
      {/* Top Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Photo Library</h1>
          <p className="page-subtitle">
            Browse all {photos.length} ingested photos, inspect metadata, or manually curate a carousel with Gemini.
          </p>
        </div>

        <div className="action-buttons">
          <button className="btn-secondary" onClick={fetchPhotos}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="library-toolbar">
        <div className="filter-pills">
          <button
            className={`filter-pill ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All Photos ({photos.length})
          </button>
          <button
            className={`filter-pill ${filter === 'awaiting' ? 'active' : ''}`}
            onClick={() => setFilter('awaiting')}
          >
            Awaiting Curation ({countAwaiting})
          </button>
          <button
            className={`filter-pill ${filter === 'in_carousel' ? 'active' : ''}`}
            onClick={() => setFilter('in_carousel')}
          >
            In Drafts ({countInCarousel})
          </button>
          <button
            className={`filter-pill ${filter === 'published' ? 'active' : ''}`}
            onClick={() => setFilter('published')}
          >
            Published ({countPublished})
          </button>
          <button
            className={`filter-pill ${filter === 'duplicate' ? 'active' : ''}`}
            onClick={() => setFilter('duplicate')}
          >
            Alternate / Burst ({countDuplicates})
          </button>
        </div>

        <div className="selection-quick-tools">
          <button className="btn-link" onClick={selectAllFiltered}>
            Select 10
          </button>
          {selectedIds.size > 0 && (
            <button className="btn-link" onClick={clearSelection}>
              Clear ({selectedIds.size})
            </button>
          )}
        </div>
      </div>

      {message && <div className="notification-banner">{message}</div>}

      {/* Photo Grid */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading photo library…</p>
        </div>
      ) : filteredPhotos.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📷</div>
          <h2>No photos found in this view</h2>
          <p>Sync your photos from the Queue tab to populate the library.</p>
        </div>
      ) : (
        <div className="library-grid">
          {filteredPhotos.map((photo) => {
            const isSelected = selectedIds.has(photo.id)
            const filename = photo.export_path ? photo.export_path.split('/').pop() : ''
            const imageUrl = filename ? `/static/${filename}` : ''

            return (
              <div
                key={photo.id}
                className={`library-card ${isSelected ? 'selected' : ''}`}
                onClick={() => toggleSelect(photo.id)}
              >
                <div className="library-thumb-wrap">
                  {imageUrl ? (
                    <img src={imageUrl} alt="Library thumbnail" className="library-thumb-img" />
                  ) : (
                    <div className="image-placeholder">No preview</div>
                  )}

                  {/* Selection Checkbox Pill */}
                  <div className={`select-checkbox ${isSelected ? 'checked' : ''}`}>
                    {isSelected && (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </div>

                  {/* Delete Button */}
                  <button
                    type="button"
                    className="library-item-delete-btn"
                    onClick={(e) => handleDeleteSingle(photo.id, e)}
                    title="Delete photo from library"
                  >
                    ✕
                  </button>

                  {/* Status Badge */}
                  <div className="library-badge-container">
                    {photo.status === 'published' ? (
                      <span className="badge-published-library">✓ Published</span>
                    ) : photo.status === 'in_carousel' ? (
                      <span className="badge-in-draft">
                        {photo.alternate_count && photo.alternate_count > 0 ? `★ Hero (${photo.alternate_count} alt${photo.alternate_count > 1 ? 's' : ''})` : 'In Draft'}
                      </span>
                    ) : photo.status === 'duplicate' ? (
                      <span className="badge-duplicate-library" title={`Alternate shot (Hero ID: ${photo.duplicate_of?.slice(0, 8)})`}>
                        📷 Alternate
                      </span>
                    ) : photo.alternate_count && photo.alternate_count > 0 ? (
                      <span className="badge-hero-library" title={`Hero shot representing ${photo.alternate_count} alternate shots`}>
                        ★ Hero ({photo.alternate_count} alt{photo.alternate_count > 1 ? 's' : ''})
                      </span>
                    ) : (
                      <span className="badge-awaiting">Awaiting Curation</span>
                    )}
                  </div>
                </div>

                <div className="library-meta-info">
                  <span className="meta-filename">{filename || photo.id.slice(0, 8)}</span>
                  <div className="meta-details-row">
                    <span>{photo.aspect_ratio || '4:5'}</span>
                    {photo.lat && photo.lon && <span>📍 GPS</span>}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Floating Bottom Selection Bar */}
      {selectedIds.size > 0 && (
        <div className="floating-action-bar">
          <div className="floating-selection-count">
            <span className="count-bubble">{selectedIds.size}</span>
            <span>photo{selectedIds.size > 1 ? 's' : ''} selected (max 10)</span>
          </div>

          <div className="floating-buttons-row">
            <button
              className="btn-primary"
              onClick={handleCreateManualCarousel}
              disabled={creatingCarousel}
            >
              {creatingCarousel ? 'Curating with AI…' : `✨ Create Carousel with AI (${selectedIds.size})`}
            </button>

            <button className="btn-danger" onClick={handleBatchDelete} disabled={creatingCarousel}>
              🗑️ Delete from Library
            </button>

            <button className="btn-secondary" onClick={clearSelection}>
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
