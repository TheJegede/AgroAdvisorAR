import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useEvalQueue } from '../hooks/useAdmin'
import Spinner from '../components/ui/Spinner'
import Alert from '../components/ui/Alert'

function ScoreButtons({ value, onChange }) {
  return (
    <div className="flex gap-1.5" role="radiogroup" aria-label="accuracy score 1 to 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          aria-checked={value === n}
          role="radio"
          className={
            'w-9 h-9 rounded-md border text-sm font-semibold transition-colors ' +
            (value === n
              ? 'bg-field text-white border-field'
              : 'bg-white text-gray-600 border-gray-200 hover:border-field')
          }
        >
          {n}
        </button>
      ))}
    </div>
  )
}

function ChunksList({ chunks }) {
  const { t } = useLang()
  const [open, setOpen] = useState(false)
  if (!chunks || chunks.length === 0) {
    return <p className="text-xs text-gray-400">No retrieved chunks recorded.</p>
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs text-field hover:underline"
      >
        {open ? '▾' : '▸'} {t.queueShowChunks} ({chunks.length})
      </button>
      {open && (
        <ul className="mt-2 space-y-2">
          {chunks.map((c, i) => (
            <li key={i} className="bg-gray-50 border border-gray-100 rounded-md p-2 text-xs">
              <p className="font-semibold text-charcoal">{c.document_title}</p>
              {c.section_heading && (
                <p className="text-gray-500">{c.section_heading}</p>
              )}
              <p className="mt-1 text-gray-700 whitespace-pre-wrap">{c.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function AdvisoryView({ item }) {
  const { t } = useLang()
  if (item.content_type === 'oos') {
    return (
      <div className="text-sm text-gray-700 bg-harvest/10 border border-harvest/40 rounded-md p-3">
        <p className="font-medium mb-1">Out of scope reply:</p>
        <p>{typeof item.content === 'string' ? item.content : JSON.stringify(item.content)}</p>
      </div>
    )
  }
  if (item.content_type !== 'advisory' || typeof item.content !== 'object') {
    return <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(item.content, null, 2)}</pre>
  }
  const a = item.content
  return (
    <div className="text-sm text-charcoal space-y-2">
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase">Problem summary</p>
        <p>{a.problem_summary}</p>
      </div>
      {a.likely_causes?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">Likely causes</p>
          <ul className="list-disc pl-5">
            {a.likely_causes.map((c, i) => (
              <li key={i}><span className="font-medium">{c.cause}:</span> {c.explanation}</li>
            ))}
          </ul>
        </div>
      )}
      {a.recommended_actions?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">Recommended actions</p>
          <ol className="list-decimal pl-5">
            {a.recommended_actions.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
      {a.products_rates?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">Products / rates</p>
          <ul className="list-disc pl-5">
            {a.products_rates.map((p, i) => (
              <li key={i}>{p.product} — {p.rate} ({p.application_method})</li>
            ))}
          </ul>
        </div>
      )}
      {a.warnings?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">Warnings</p>
          <ul className="list-disc pl-5 text-arred">
            {a.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
      {a.citations?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">Citations</p>
          <ul className="list-disc pl-5">
            {a.citations.map((c, i) => (
              <li key={i}>{c.document_title} — {c.section}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-gray-400">
        confidence: <span className="font-semibold">{a.confidence}</span>
      </p>
    </div>
  )
}

function ReviewCard({ item, onScore }) {
  const { t } = useLang()
  const [score, setScore] = useState(null)
  const [correction, setCorrection] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  async function handleSubmit() {
    if (score === null) return
    setSubmitting(true)
    setError('')
    const res = await onScore({
      messageId: item.id,
      accuracyScore: score,
      correction,
    })
    setSubmitting(false)
    if (res.ok) {
      setDone(true)
    } else {
      setError(res.detail)
    }
  }

  if (done) return null

  const fb = item.latest_feedback

  return (
    <div className="bg-white rounded-card border border-gray-100 p-4 mb-4">
      <div className="flex items-start justify-between mb-3 gap-2 flex-wrap">
        <div className="text-xs text-gray-500">
          message_id: <code className="text-gray-700">{item.id}</code>
          <span className="ml-3">created: {item.created_at?.slice(0, 19).replace('T', ' ')}</span>
        </div>
        {fb && (
          <span className={
            'text-xs font-semibold px-2 py-0.5 rounded ' +
            (fb.rating === -1 ? 'bg-arred/15 text-arred' : 'bg-field/15 text-field')
          }>
            {fb.rating === -1 ? '👎' : '👍'} {t.queueLatestFeedback}
          </span>
        )}
      </div>

      {fb?.comment && (
        <div className="mb-3 bg-gray-50 border border-gray-100 rounded-md p-2 text-xs text-gray-700">
          "{fb.comment}"
        </div>
      )}

      <div className="mb-3">
        <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t.queueResponse}</p>
        <AdvisoryView item={item} />
      </div>

      <div className="mb-3">
        <ChunksList chunks={item.retrieved_chunks} />
      </div>

      <div className="border-t border-gray-100 pt-3 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-sm text-gray-600">{t.queueScore}:</span>
          <ScoreButtons value={score} onChange={setScore} />
        </div>
        <textarea
          value={correction}
          onChange={(e) => setCorrection(e.target.value)}
          placeholder={t.queueCorrection}
          rows={2}
          maxLength={2000}
          className="w-full text-sm border border-gray-200 rounded-md px-3 py-2
            focus:outline-none focus:ring-2 focus:ring-field/40 focus:border-field resize-none"
        />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={score === null || submitting}
            className="bg-field text-white text-sm font-medium rounded-md px-4 py-1.5
              hover:bg-field/90 disabled:opacity-50 min-h-touch"
          >
            {submitting ? '...' : t.queueSubmitScore}
          </button>
          {error && <span className="text-xs text-arred">{error}</span>}
        </div>
      </div>
    </div>
  )
}

export default function EvalQueuePage() {
  const { t } = useLang()
  const { items, loading, error, filter, load, submitScore } = useEvalQueue()

  const FILTERS = [
    { key: 'flagged', label: t.queueFilterFlagged },
    { key: 'spotcheck', label: t.queueFilterSpotcheck },
    { key: 'all', label: t.queueFilterAll },
  ]

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h1 className="text-xl font-bold text-charcoal">{t.adminQueue}</h1>
        <Link
          to="/admin"
          className="text-sm text-field hover:underline"
        >
          ← {t.adminDashboard}
        </Link>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => load({ filter: f.key, offset: 0 })}
            className={
              'text-sm rounded-full px-3 py-1.5 border transition-colors ' +
              (filter === f.key
                ? 'bg-field text-white border-field'
                : 'bg-white text-gray-600 border-gray-200 hover:border-field')
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : items.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">{t.queueEmpty}</p>
      ) : (
        items.map((item) => (
          <ReviewCard key={item.id} item={item} onScore={submitScore} />
        ))
      )}
    </div>
  )
}
