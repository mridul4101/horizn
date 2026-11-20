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
  hashtags?: string[]
  aspectRatio?: string
  onRemoveSlide?: (photoId: string) => void
}

export default function CarouselMockup({
  slides,
  caption,
  hashtags = [],
  aspectRatio = '4:5',
  onRemoveSlide,
}: CarouselMockupProps) {
  const [currentIndex, setCurrentIndex] = useState(0)

  if (!slides || slides.length === 0) {
    return (
      <div className="phone-frame mockup-empty">
        <div className="dynamic-island">
          <div className="island-camera"></div>
        </div>
        <div className="mockup-empty-content">
          <p>No slides in this carousel yet.</p>
          <span className="text-muted">Add or restore photos to preview</span>
        </div>
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

  const handleRemoveClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (currentSlide && onRemoveSlide) {
      onRemoveSlide(currentSlide.photo_id)
      if (currentIndex >= slides.length - 1) {
        setCurrentIndex(Math.max(0, slides.length - 2))
      }
    }
  }

  return (
    <div className="mockup-container">
      {/* iPhone 17 Pro Max Chassis */}
      <div className="phone-frame">
        {/* Modern Dynamic Island */}
        <div className="dynamic-island-container">
          <div className="dynamic-island">
            <div className="island-camera"></div>
            <div className="island-sensor"></div>
          </div>
        </div>

        {/* iPhone Status Bar */}
        <div className="phone-status-bar">
          <span className="status-time">9:41</span>
          <div className="status-icons">
            <span className="status-cell">5G</span>
            <svg className="status-battery" viewBox="0 0 24 12" fill="currentColor">
              <rect x="0.5" y="0.5" width="20" height="11" rx="3.5" stroke="currentColor" fill="none" />
              <rect x="2" y="2" width="14" height="8" rx="2" />
              <path d="M22 4C22.6 4.4 23 5.1 23 6C23 6.9 22.6 7.6 22 8" stroke="currentColor" strokeLinecap="round" />
            </svg>
          </div>
        </div>

        {/* Instagram Post Header */}
        <div className="phone-ig-header">
          <div className="ig-avatar-ring">
            <div className="ig-avatar"></div>
          </div>
          <div className="ig-user-meta">
            <span className="ig-username">horizn.studio</span>
            <span className="ig-location">Varanasi, India</span>
          </div>
          <div className="ig-header-actions">
            <span className="ig-slide-counter">
              {safeIndex + 1}/{slides.length}
            </span>
            <span className="ig-more-dots">•••</span>
          </div>
        </div>

        {/* Photo Container */}
        <div
          className="phone-image-area"
          style={{ aspectRatio: aspectRatio === '1:1' ? '1/1' : aspectRatio === '16:9' ? '16/9' : '4/5' }}
        >
          {imageUrl ? (
            <img src={imageUrl} alt={`Slide ${safeIndex + 1}`} className="phone-image" />
          ) : (
            <div className="image-placeholder">No image preview</div>
          )}

          {/* Sleek Delete Icon Overlay directly on the photo */}
          {onRemoveSlide && (
            <button
              type="button"
              className="photo-overlay-delete-btn"
              onClick={handleRemoveClick}
              title={`Remove slide #${safeIndex + 1}`}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          )}

          {/* Navigation Arrows */}
          {slides.length > 1 && (
            <>
              <button type="button" className="nav-arrow nav-left" onClick={handlePrev} title="Previous">
                ‹
              </button>
              <button type="button" className="nav-arrow nav-right" onClick={handleNext} title="Next">
                ›
              </button>
            </>
          )}
        </div>

        {/* Instagram Action Row: Heart, Comment, Share ... Dots ... Bookmark */}
        <div className="phone-ig-actions">
          <div className="ig-actions-left">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
            </svg>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </div>

          {/* Dots centered in action bar */}
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

          <div className="ig-actions-right">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </div>
        </div>

        {/* Caption & Metadata */}
        <div className="phone-caption-area">
          <div className="phone-likes-count">
            Liked by <strong>natgeo</strong> and <strong>others</strong>
          </div>
          <p className="phone-caption-text">
            <strong>horizn.studio</strong>{' '}
            {caption || currentSlide?.caption || 'Capturing the unseen horizons.'}
          </p>
          {hashtags.length > 0 && (
            <p className="phone-hashtags-text">
              {hashtags.slice(0, 10).join(' ')}
            </p>
          )}
          <span className="phone-timestamp">2 HOURS AGO</span>
        </div>

        {/* iOS Home Indicator Bar */}
        <div className="phone-home-indicator">
          <div className="home-bar"></div>
        </div>
      </div>
    </div>
  )
}
