import { useState } from 'react'
import { useLang } from '../../contexts/LangContext'
import { useFeedback } from '../../hooks/useFeedback'

export default function FeedbackWidget({ messageId }) {
  const { t } = useLang()
  const { submit, submitting } = useFeedback()

  const [pendingRating, setPendingRating] = useState(null)
  const [comment, setComment] = useState('')
  const [status, setStatus] = useState('idle')
  const [errorMsg, setErrorMsg] = useState('')

  if (!messageId) return null

  async function handleSend() {
    if (pendingRating === null) return
    const res = await submit({ messageId, rating: pendingRating, comment })
    if (res.ok) {
      setStatus('done')
      setComment('')
      setPendingRating(null)
    } else if (res.status === 429) {
      setStatus('error')
      setErrorMsg(t.feedbackRateLimited)
    } else {
      setStatus('error')
      setErrorMsg(t.feedbackError)
    }
  }

  function chooseRating(rating) {
    setPendingRating(rating)
    setStatus('idle')
    setErrorMsg('')
  }

  function resetForNewSubmission() {
    setStatus('idle')
    setErrorMsg('')
    setPendingRating(null)
    setComment('')
  }

  return (
    <div className="mt-4 pt-3 border-t border-gray-100 dark:border-t-2 dark:border-hc-border text-sm">
      {status === 'done' ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-gray-500 dark:text-hc-fg">{t.feedbackThanks}</span>
          <button
            type="button"
            onClick={resetForNewSubmission}
            className="text-xs text-field dark:text-hc-accent font-bold hover:underline"
          >
            {t.feedbackPrompt}
          </button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-gray-600 dark:text-hc-fg">{t.feedbackPrompt}</span>
            <div className="flex gap-2">
              <button
                type="button"
                aria-label={t.feedbackHelpful}
                aria-pressed={pendingRating === 1}
                onClick={() => chooseRating(1)}
                disabled={submitting}
                className={
                  'w-9 h-9 rounded-full border flex items-center justify-center transition-colors dark:border-2 ' +
                  (pendingRating === 1
                    ? 'bg-field text-white border-field dark:bg-hc-accent dark:text-hc-accent-fg dark:border-hc-border'
                    : 'bg-white text-gray-500 border-gray-200 hover:border-field hover:text-field dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border dark:hover:bg-hc-accent dark:hover:text-hc-accent-fg')
                }
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V2.75A.75.75 0 0114.25 2a2.25 2.25 0 012.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 01-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 10.203 4.167 9.75 5 9.75h1.053c.472 0 .745.556.5.96a8.958 8.958 0 00-1.302 4.665c0 1.194.232 2.333.654 3.375z" />
                </svg>
              </button>
              <button
                type="button"
                aria-label={t.feedbackNotHelpful}
                aria-pressed={pendingRating === -1}
                onClick={() => chooseRating(-1)}
                disabled={submitting}
                className={
                  'w-9 h-9 rounded-full border flex items-center justify-center transition-colors dark:border-2 ' +
                  (pendingRating === -1
                    ? 'bg-arred text-white border-arred dark:bg-hc-danger dark:text-hc-danger-fg dark:border-hc-border'
                    : 'bg-white text-gray-500 border-gray-200 hover:border-arred hover:text-arred dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border dark:hover:bg-hc-danger dark:hover:text-hc-danger-fg')
                }
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M7.5 15h2.25m8.024-9.75c.011.05.028.1.052.148.591 1.2.924 2.55.924 3.977a8.96 8.96 0 01-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.831 4.398C20.613 14.547 19.833 15 19 15h-1.053c-.472 0-.745-.556-.5-.96a8.95 8.95 0 00.303-.54m.023-8.25H16.48a4.5 4.5 0 01-1.423-.23l-3.114-1.04a4.5 4.5 0 00-1.423-.23H6.504c-.618 0-1.217.247-1.605.729A11.95 11.95 0 002.25 12c0 .434.023.863.068 1.285C2.427 14.306 3.346 15 4.372 15h3.126c.618 0 .991.724.725 1.282A7.471 7.471 0 007.5 19.5a2.25 2.25 0 002.25 2.25.75.75 0 00.75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 002.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384" />
                </svg>
              </button>
            </div>
          </div>

          {pendingRating !== null && (
            <div className="mt-3 flex flex-col gap-2">
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={t.feedbackCommentPlaceholder}
                aria-label={t.feedbackCommentPlaceholder}
                maxLength={500}
                rows={2}
                className="w-full text-sm border border-gray-200 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg rounded-md px-3 py-2
                  focus:outline-none focus:ring-2 focus:ring-field/40 focus:border-field
                  resize-none"
              />
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={submitting}
                  className="bg-field text-white text-sm font-bold rounded-md px-4 py-1.5
                    hover:bg-field/90 disabled:opacity-50 min-h-touch
                    dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border"
                >
                  {submitting ? t.feedbackSubmitting : t.feedbackSubmit}
                </button>
                {status === 'error' && (
                  <span className="text-xs text-arred dark:text-hc-danger font-bold">{errorMsg}</span>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
