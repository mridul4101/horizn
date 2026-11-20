import { useEffect, useState } from 'react'
import { SlideItem } from '../components/CarouselMockup'

interface PublishedCarousel {
  id: string
  status: string
  aspect_ratio?: string
  caption?: string
  ig_media_id?: string
  published_at?: string
  slides: SlideItem[]
}

export default function History() {
  const [published, setPublished] = useState<PublishedCarousel[]>([])
  const [loading, setLoading] = useState(true)

  const fetchPublished = async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/carousels?status=published')
      if (res.ok) {
        const data = await res.json()
        setPublished(data)
      }
    } catch (err) {
      console.error('Failed to load published history', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPublished()
  }, [])

  return (
    <div className="history-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Published Posts</h1>
          <p className="page-subtitle">Carousels that have been successfully published to Instagram.</p>
        </div>
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading history…</p>
        </div>
      ) : published.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📸</div>
          <h2>No Published Posts Yet</h2>
          <p>When you approve and publish carousels from the queue, they will appear here with their Instagram Media IDs.</p>
        </div>
      ) : (
        <div className="published-list">
          {published.map((p) => {
            const firstSlide = p.slides && p.slides[0]
            const filename = firstSlide?.export_path ? firstSlide.export_path.split('/').pop() : ''
            const url = filename ? `/static/${filename}` : ''

            return (
              <div key={p.id} className="published-card">
                <div className="published-thumb-area">
                  {url ? (
                    <img src={url} alt="Cover slide" className="published-thumb-img" />
                  ) : (
                    <div className="card-thumb-placeholder" />
                  )}
                </div>

                <div className="published-details">
                  <div className="published-header-row">
                    <span className="badge-published">✓ Published</span>
                    <span className="published-date">
                      {p.published_at ? new Date(p.published_at).toLocaleString() : 'Recently'}
                    </span>
                  </div>

                  <p className="published-caption">{p.caption || 'No caption'}</p>

                  <div className="published-meta-footer">
                    <span>{p.slides?.length || 1} slides</span>
                    {p.ig_media_id && (
                      <span className="ig-id-pill">
                        Meta ID: <code>{p.ig_media_id}</code>
                      </span>
                    )}
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
