import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'

import CarouselMockup, { SlideItem } from '../components/CarouselMockup'
import SlideCard from '../components/SlideCard'
import PublishButton from '../components/PublishButton'

export default function Editor() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [slides, setSlides] = useState<SlideItem[]>([])
  const [caption, setCaption] = useState('')
  const [hashtags, setHashtags] = useState<string[]>([])
  const [aspectRatio, setAspectRatio] = useState('4:5')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)

  const [removePhotoId, setRemovePhotoId] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const fetchCarousel = async () => {
    if (!id) return
    try {
      setLoading(true)
      const res = await fetch(`/api/carousels/${id}`)
      if (res.ok) {
        const data = await res.json()
        setSlides(data.slides || [])
        setCaption(data.caption || '')
        setHashtags(data.hashtags || [])
        setAspectRatio(data.aspect_ratio || '4:5')
      }
    } catch (err) {
      console.error('Failed to load carousel', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCarousel()
  }, [id])

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (over && active.id !== over.id) {
      setSlides((items) => {
        const oldIndex = items.findIndex((i) => i.photo_id === active.id)
        const newIndex = items.findIndex((i) => i.photo_id === over.id)
        const reordered = arrayMove(items, oldIndex, newIndex)
        return reordered.map((slide, idx) => ({ ...slide, position: idx }))
      })
    }
  }

  const handleRemoveSlide = (photoId: string) => {
    setRemovePhotoId(photoId)
  }

  const confirmRemoveSlide = async (photoId: string, deleteFromLibrary: boolean) => {
    if (!id) return
    try {
      const res = await fetch(
        `/api/carousels/${id}/slides/${photoId}?delete_from_library=${deleteFromLibrary}`,
        { method: 'DELETE' }
      )
      if (res.ok) {
        const data = await res.json()
        if (data.status === 'deleted' || !data.slides || data.slides.length === 0) {
          navigate('/')
        } else {
          setSlides(data.slides || [])
        }
      }
    } catch (err) {
      console.error('Failed to remove slide', err)
    } finally {
      setRemovePhotoId(null)
    }
  }

  const handleDeleteDraft = async () => {
    if (!id) return
    if (!confirm('Are you sure you want to delete this draft carousel?')) return
    try {
      const res = await fetch(`/api/carousels/${id}`, { method: 'DELETE' })
      if (res.ok) {
        navigate('/')
      }
    } catch (err) {
      console.error('Failed to delete draft', err)
    }
  }

  const handleSave = async () => {
    if (!id) return
    try {
      setSaving(true)
      const res = await fetch(`/api/carousels/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          caption,
          hashtags,
          slide_order: slides.map((s) => s.photo_id),
        }),
      })
      if (res.ok) {
        setFeedback('Saved successfully!')
        setTimeout(() => setFeedback(null), 3000)
      }
    } catch {
      setFeedback('Error saving changes.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Loading editor…</p>
      </div>
    )
  }

  return (
    <div className="editor-page">
      <div className="editor-top-bar">
        <button className="btn-back" onClick={() => navigate('/')}>
          ← Back to Queue
        </button>
        <div className="editor-actions">
          {feedback && <span className="feedback-text">{feedback}</span>}
          <button className="btn-danger" onClick={handleDeleteDraft}>
            Delete Draft
          </button>
          <button className="btn-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>

      <div className="editor-grid">
        {/* Left column: Realistic Instagram Preview */}
        <div className="editor-preview-col">
          <CarouselMockup
            slides={slides}
            caption={caption}
            hashtags={hashtags}
            aspectRatio={aspectRatio}
            onRemoveSlide={handleRemoveSlide}
          />
        </div>

        {/* Right column: Controls & Slide reordering */}
        <div className="editor-controls-col">
          <div className="panel-box">
            <h2 className="section-title">Carousel Slides ({slides.length})</h2>
            <p className="section-hint">Drag slides using the handle (⠿) to change their display order.</p>

            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={slides.map((s) => s.photo_id)} strategy={verticalListSortingStrategy}>
                <div className="slides-sortable-list">
                  {slides.map((slide) => (
                    <SlideCard
                      key={slide.photo_id}
                      slide={slide}
                      onRemove={handleRemoveSlide}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </div>

          <div className="panel-box">
            <h2 className="section-title">Caption & Copy</h2>
            <textarea
              className="caption-textarea"
              rows={4}
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Write an evocative caption for this scenery carousel…"
            />

            <h3 className="subsection-title">Hashtags</h3>
            <input
              type="text"
              className="hashtags-input"
              value={hashtags.join(' ')}
              onChange={(e) =>
                setHashtags(
                  e.target.value
                    .split(/\s+/)
                    .filter((t) => t.trim().length > 0)
                )
              }
              placeholder="#landscape #mountains #travel…"
            />
          </div>

          <div className="panel-box publish-panel">
            <h2 className="section-title">Publishing</h2>
            <p className="section-hint">
              Publishes directly to your linked Instagram Creator/Business account via the Meta Graph API and an ephemeral tunnel.
            </p>
            {id && <PublishButton carouselId={id} onPublished={() => navigate('/history')} />}
          </div>
        </div>
      </div>

      {/* Remove Photo Options Modal */}
      {removePhotoId && (
        <div className="modal-backdrop" onClick={() => setRemovePhotoId(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Remove Photo</h3>
            <p className="modal-desc">
              Choose how you would like to remove this photo:
            </p>

            <div className="modal-options-list">
              <button
                type="button"
                className="modal-option-btn primary-option"
                onClick={() => confirmRemoveSlide(removePhotoId, false)}
              >
                <div className="option-headline">Remove from Carousel Only</div>
                <div className="option-subtext">
                  Keeps the photo in your library. It returns to "Awaiting Curation" and can be used in other carousels.
                </div>
              </button>

              <button
                type="button"
                className="modal-option-btn danger-option"
                onClick={() => confirmRemoveSlide(removePhotoId, true)}
              >
                <div className="option-headline">🗑️ Delete from Library Altogether</div>
                <div className="option-subtext">
                  Permanently removes this photo from your library and all draft carousels.
                </div>
              </button>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setRemovePhotoId(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
