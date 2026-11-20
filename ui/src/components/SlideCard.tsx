import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { SlideItem } from './CarouselMockup'

interface SlideCardProps {
  slide: SlideItem
  onRemove: (photoId: string) => void
  onCaptionChange?: (photoId: string, caption: string) => void
}

export default function SlideCard({ slide, onRemove, onCaptionChange }: SlideCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: slide.photo_id })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const filename = slide.export_path ? slide.export_path.split('/').pop() : ''
  const imageUrl = filename ? `/static/${filename}` : ''

  return (
    <div ref={setNodeRef} style={style} className="slide-card">
      {/* Drag handle */}
      <div {...attributes} {...listeners} className="drag-handle" title="Drag to reorder slide">
        ⠿
      </div>

      {/* Position badge */}
      <div className="slide-badge">#{slide.position + 1}</div>

      {/* Thumbnail */}
      <div className="slide-thumb-container">
        {imageUrl ? (
          <img src={imageUrl} alt={`Slide ${slide.position + 1}`} className="slide-thumb" />
        ) : (
          <div className="slide-thumb-placeholder">?</div>
        )}
      </div>

      {/* Slide caption override or ID */}
      <div className="slide-info">
        <input
          type="text"
          placeholder="Slide caption override (optional)"
          value={slide.caption || ''}
          onChange={(e) => onCaptionChange?.(slide.photo_id, e.target.value)}
          className="slide-caption-input"
        />
        <span className="slide-id-label">{slide.photo_id.slice(0, 8)}…</span>
      </div>

      {/* Remove button */}
      <button
        type="button"
        className="slide-remove-btn"
        onClick={() => onRemove(slide.photo_id)}
        title="Remove this photo from carousel"
      >
        ✕ Remove
      </button>
    </div>
  )
}
