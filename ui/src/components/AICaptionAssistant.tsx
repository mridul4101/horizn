import React, { useState } from 'react'

interface AICaptionAssistantProps {
  carouselId: string
  currentCaption: string
  currentHashtags: string[]
  onApply: (newCaption: string, newHashtags: string[]) => void
}

const REFINE_PRESETS = [
  { label: '🌿 More Poetic', instruction: 'Make it more evocative, atmospheric, and poetic' },
  { label: '⚡ Short & Punchy', instruction: 'Make it 1–2 punchy, minimal sentences' },
  { label: '📖 Storyteller', instruction: 'Write with a vivid, documentary storytelling narrative' },
  { label: '☕ Candid Phone Diary', instruction: 'Humble, observant phone photography journal tone' },
  { label: '✨ Polish & Elevate', instruction: 'Keep the core meaning, but polish the phrasing elegantly' },
]

const SCRATCH_PRESETS = [
  { label: '✨ Fresh & Minimal', instruction: 'Clean, minimal caption capturing the visual essence' },
  { label: '🌅 Mood & Light', instruction: 'Focus on the lighting, colors, and visual atmosphere' },
  { label: '🚶 Street & Candid', instruction: 'Observant, candid street photography from a phone lens' },
  { label: '📜 Reflective Journey', instruction: 'A reflective, nostalgic memory of this travel moment' },
]

export default function AICaptionAssistant({
  carouselId,
  currentCaption,
  currentHashtags,
  onApply,
}: AICaptionAssistantProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [mode, setMode] = useState<'refine' | 'scratch'>('refine')
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [suggestion, setSuggestion] = useState<{ caption: string; hashtags: string[] } | null>(null)
  const [undoState, setUndoState] = useState<{ caption: string; hashtags: string[] } | null>(null)

  const handleGenerate = async (customInstruction?: string) => {
    const finalInstruction = customInstruction !== undefined ? customInstruction : instruction
    setLoading(true)
    setError(null)
    setSuggestion(null)

    try {
      const res = await fetch(`/api/carousels/${carouselId}/ai-caption`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          instruction: finalInstruction.trim() || undefined,
          current_caption: currentCaption,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Failed to generate AI caption')
      }

      const data = await res.json()
      setSuggestion({
        caption: data.caption,
        hashtags: data.hashtags || [],
      })
    } catch (err: any) {
      setError(err.message || 'Error generating AI caption')
    } finally {
      setLoading(false)
    }
  }

  const handleApply = () => {
    if (!suggestion) return
    // Save current state for undo
    setUndoState({
      caption: currentCaption,
      hashtags: [...currentHashtags],
    })
    onApply(suggestion.caption, suggestion.hashtags)
    setSuggestion(null)
  }

  const handleUndo = () => {
    if (!undoState) return
    onApply(undoState.caption, undoState.hashtags)
    setUndoState(null)
  }

  return (
    <div className="ai-caption-widget">
      <div className="ai-caption-header">
        <button
          type="button"
          className={`btn-ai-toggle ${isOpen ? 'active' : ''}`}
          onClick={() => setIsOpen(!isOpen)}
        >
          <span className="ai-icon">✨</span>
          <span className="ai-title">AI Caption Assistant</span>
          <span className="ai-badge">{isOpen ? 'Hide' : 'Rewrite & Refine'}</span>
        </button>

        {undoState && (
          <button type="button" className="btn-ai-undo" onClick={handleUndo} title="Revert to caption before AI change">
            ↺ Undo AI Changes
          </button>
        )}
      </div>

      {isOpen && (
        <div className="ai-caption-body">
          {/* Mode Switcher */}
          <div className="ai-mode-tabs">
            <button
              type="button"
              className={`ai-tab ${mode === 'refine' ? 'active' : ''}`}
              onClick={() => {
                setMode('refine')
                setSuggestion(null)
              }}
            >
              ✏️ Refine Current Caption
            </button>
            <button
              type="button"
              className={`ai-tab ${mode === 'scratch' ? 'active' : ''}`}
              onClick={() => {
                setMode('scratch')
                setSuggestion(null)
              }}
            >
              🔄 Build from Scratch
            </button>
          </div>

          {/* Quick Preset Chips */}
          <div className="ai-presets-wrap">
            <span className="presets-label">Quick styles:</span>
            <div className="presets-chips">
              {(mode === 'refine' ? REFINE_PRESETS : SCRATCH_PRESETS).map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className="preset-chip"
                  onClick={() => {
                    setInstruction(preset.instruction)
                    handleGenerate(preset.instruction)
                  }}
                  disabled={loading}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Custom Instruction Input */}
          <div className="ai-input-row">
            <input
              type="text"
              className="ai-prompt-input"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !loading) {
                  e.preventDefault()
                  handleGenerate()
                }
              }}
              placeholder={
                mode === 'refine'
                  ? "Give instructions (e.g. 'Make it shorter and nostalgic', 'Focus on the street chai stall')..."
                  : "Creative direction (e.g. 'Humble phone photography vibe', 'Varanasi evening peace')..."
              }
              disabled={loading}
            />
            <button
              type="button"
              className="btn-ai-generate"
              onClick={() => handleGenerate()}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="ai-spinner"></span>
                  Crafting…
                </>
              ) : (
                <>✨ Generate</>
              )}
            </button>
          </div>

          {error && <div className="ai-error-msg">⚠️ {error}</div>}

          {/* Suggestion Result Preview Card */}
          {suggestion && (
            <div className="ai-suggestion-card">
              <div className="ai-suggestion-header">
                <span className="suggestion-badge">AI Suggestion</span>
                <div className="suggestion-actions">
                  <button type="button" className="btn-ai-apply" onClick={handleApply}>
                    ✓ Apply to Draft
                  </button>
                  <button
                    type="button"
                    className="btn-ai-retry"
                    onClick={() => handleGenerate()}
                    disabled={loading}
                    title="Generate another option"
                  >
                    ↺ Re-roll
                  </button>
                  <button
                    type="button"
                    className="btn-ai-dismiss"
                    onClick={() => setSuggestion(null)}
                    title="Dismiss suggestion"
                  >
                    ✕
                  </button>
                </div>
              </div>

              <div className="ai-suggestion-text">{suggestion.caption}</div>

              {suggestion.hashtags.length > 0 && (
                <div className="ai-suggestion-tags">
                  {suggestion.hashtags.slice(0, 10).map((tag, idx) => (
                    <span key={idx} className="suggestion-tag">
                      {tag}
                    </span>
                  ))}
                  {suggestion.hashtags.length > 10 && (
                    <span className="suggestion-tag-more">
                      +{suggestion.hashtags.length - 10} more
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
