import { useState } from 'react'

export interface SlideItem {
  position: number
  photo_id: string
  export_path?: string
  caption?: string
}

interface CarouselMockupProps {
  slides: SlideItem[]
  caption?: string
  aspectRatio?: string
  onRemoveSlide?: (photoId: string) => void
}

export default function CarouselMockup({
  slides,
  caption,
  aspectRatio = '4:5',
  onRemoveSlide,
}: CarouselMockupProps) {
  const [currentIndex, setCurrentIndex] = useState(0)

  if (!slides || slides.length === 0) {
    return (
      <div className="phone-frame mockup-empty">
        <p>No slides in this carousel yet.</p>
      </div>
    )
  }

  const safeIndex = Math.min(currentIndex, slides.length - 1)
  const currentSlide = slides[safeIndex]
  const filename = currentSlide?.export_path ? currentSlide.export_path.split('/').pop() : ''
  const imageUrl = filename ? `/static/${filename}` : ''

  const handlePrev = (e: React.MouseEvent) => {
    e.stopPropagation()
    setCurrentIndex((prev) => (prev > 0 ? prev - 1 : slides.length - 1))
  }

  const handleNext = (e: React.MouseEvent) => {
    e.stopPropagation()
    setCurrentIndex((prev) => (prev < slides.length - 1 ? prev + 1 : 0))
  }

  const handleRemove = () => {
    if (currentSlide && onRemoveSlide) {
      onRemoveSlide(currentSlide.photo_id)
      if (currentIndex >= slides.length - 1) {
        setCurrentIndex(Math.max(0, slides.length - 2))
      }
    }
  }

  return (
    <div className="mockup-container">
      <div className="phone-frame">
        {/* Notch */}
        <div className="phone-notch">
          <div className="notch-camera"></div>
        </div>

        {/* Header inside phone */}
        <div className="phone-ig-header">
          <div className="ig-avatar"></div>
          <span className="ig-username">your_landscape_account</span>
          <span className="ig-slide-counter">
            {safeIndex + 1} / {slides.length}
          </span>
        </div>

        {/* Photo view area */}
        <div className="phone-image-area" style={{ aspectRatio: aspectRatio === '1:1' ? '1/1' : '4/5' }}>
          {imageUrl ? (
            <img src={imageUrl} alt={`Slide ${safeIndex + 1}`} className="phone-image" />
          ) : (
            <div className="image-placeholder">No image preview</div>
          )}

          {slides.length > 1 && (
            <>
              <button className="nav-arrow nav-left" onClick={handlePrev} title="Previous">
                ‹
              </button>
              <button className="nav-arrow nav-right" onClick={handleNext} title="Next">
                ›
              </button>
            </>
          )}
        </div>

        {/* Carousel indicator dots */}
        {slides.length > 1 && (
          <div className="phone-dots">
            {slides.map((_, idx) => (
              <span
                key={idx}
                className={`dot ${idx === safeIndex ? 'active' : ''}`}
                onClick={() => setCurrentIndex(idx)}
              />
            ))}
          </div>
        )}

        {/* Caption preview inside mockup */}
        <div className="phone-caption-area">
          <p className="phone-caption-text">
            <strong>your_landscape_account</strong>{' '}
            {caption || currentSlide?.caption || 'No caption entered yet.'}
          </p>
        </div>
      </div>

      {/* Quick remove button right below phone mockup */}
      {onRemoveSlide && currentSlide && (
        <div className="phone-quick-actions">
          <button className="btn-remove-current-slide" onClick={handleRemove}>
            🗑️ Remove Slide #{safeIndex + 1} from Carousel
          </button>
        </div>
      )}
    </div>
  )
}
