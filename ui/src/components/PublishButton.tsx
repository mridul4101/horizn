import { useState } from 'react'

interface PublishButtonProps {
  carouselId: string
  onPublished?: (mediaId: string) => void
}

type StepState = 'waiting' | 'active' | 'done' | 'error'

interface StepStatus {
  tunnel: StepState
  upload: StepState
  container: StepState
  publish: StepState
}

export default function PublishButton({ carouselId, onPublished }: PublishButtonProps) {
  const [publishing, setPublishing] = useState(false)
  const [publishedMediaId, setPublishedMediaId] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [steps, setSteps] = useState<StepStatus>({
    tunnel: 'waiting',
    upload: 'waiting',
    container: 'waiting',
    publish: 'waiting',
  })

  const startPublish = async () => {
    setPublishing(true)
    setErrorMessage(null)
    setSteps({
      tunnel: 'active',
      upload: 'waiting',
      container: 'waiting',
      publish: 'waiting',
    })

    try {
      const res = await fetch(`/api/publish/${carouselId}`, { method: 'POST' })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to start publish')
      }

      // Connect to SSE stream
      const eventSource = new EventSource(`/api/publish/${carouselId}/status`)

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.event === 'tunnel_ready') {
            setSteps((s) => ({ ...s, tunnel: 'done', upload: 'active' }))
          } else if (data.event === 'upload_slide' || data.event === 'upload') {
            setSteps((s) => ({ ...s, tunnel: 'done', upload: 'active' }))
          } else if (data.event === 'create_carousel' || data.event === 'processing') {
            setSteps((s) => ({ ...s, upload: 'done', container: 'active' }))
          } else if (data.event === 'publishing') {
            setSteps((s) => ({ ...s, container: 'done', publish: 'active' }))
          } else if (data.event === 'published' || (data.event === 'done' && data.status === 'published')) {
            const mediaId = data.ig_media_id || 'published'
            setSteps({
              tunnel: 'done',
              upload: 'done',
              container: 'done',
              publish: 'done',
            })
            setPublishedMediaId(mediaId)
            setPublishing(false)
            eventSource.close()
            onPublished?.(mediaId)
          } else if (data.event === 'error' || data.status === 'failed') {
            setErrorMessage(data.detail || 'Publishing failed')
            setPublishing(false)
            eventSource.close()
          }
        } catch {
          // ignore parsing error
        }
      }

      eventSource.onerror = () => {
        eventSource.close()
        setPublishing(false)
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Error publishing')
      setPublishing(false)
    }
  }

  return (
    <div className="publish-widget">
      {!publishing && !publishedMediaId && (
        <button className="btn-publish" onClick={startPublish}>
          Publish to Instagram
        </button>
      )}

      {publishing && (
        <div className="publish-stepper">
          <div className="stepper-title">Publishing in progress…</div>
          <div className="stepper-row">
            <span className={`step-badge ${steps.tunnel}`}>
              {steps.tunnel === 'done' ? '✓' : steps.tunnel === 'active' ? '●' : '○'} Tunnel
            </span>
            <span className={`step-badge ${steps.upload}`}>
              {steps.upload === 'done' ? '✓' : steps.upload === 'active' ? '●' : '○'} Upload
            </span>
            <span className={`step-badge ${steps.container}`}>
              {steps.container === 'done' ? '✓' : steps.container === 'active' ? '●' : '○'} Container
            </span>
            <span className={`step-badge ${steps.publish}`}>
              {steps.publish === 'done' ? '✓' : steps.publish === 'active' ? '●' : '○'} Publish
            </span>
          </div>
        </div>
      )}

      {publishedMediaId && (
        <div className="publish-success">
          <span className="success-icon">✓</span> Published to Instagram! (Media ID: {publishedMediaId})
        </div>
      )}

      {errorMessage && <div className="publish-error">⚠️ {errorMessage}</div>}
    </div>
  )
}
