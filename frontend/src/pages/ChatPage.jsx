import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useSSEQuery } from '../hooks/useSSEQuery'
import { useSessions } from '../hooks/useSessions'
import ChatHistory from '../components/chat/ChatHistory'
import ChatInput from '../components/chat/ChatInput'
import Alert from '../components/ui/Alert'
import Spinner from '../components/ui/Spinner'

export default function ChatPage() {
  const { lang, t } = useLang()
  const { sendQuery, streaming } = useSSEQuery()
  const { createSession, loadSession } = useSessions()
  const [searchParams] = useSearchParams()

  const [messages, setMessages] = useState([])
  const [sessionHistory, setSessionHistory] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [loadingSession, setLoadingSession] = useState(false)

  const sessionParam = searchParams.get('session')

  // Load past session from URL param on mount
  useEffect(() => {
    if (!sessionParam) return
    setLoadingSession(true)
    loadSession(sessionParam)
      .then(({ messages: loaded, sessionHistory: history }) => {
        setMessages(loaded)
        setSessionHistory(history)
        setSessionId(sessionParam)
      })
      .catch(() => setLoadError(t.sessionLoadError))
      .finally(() => setLoadingSession(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(message) {
    const userMsg = { id: Date.now(), role: 'user', type: 'text', content: message }
    setMessages((prev) => [...prev, userMsg])

    let activeSessionId = sessionId
    if (!activeSessionId) {
      try {
        const session = await createSession(message)
        activeSessionId = session.id
        setSessionId(activeSessionId)
      } catch {
        // proceed without persistence
      }
    }

    const updatedHistory = [...sessionHistory, { role: 'user', content: message }]

    sendQuery({
      message,
      language: lang,
      sessionHistory: updatedHistory,
      sessionId: activeSessionId,
      onResult: (advisory, messageId) => {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            messageId,
            role: 'assistant',
            type: 'advisory',
            content: advisory,
          },
        ])
        setSessionHistory((h) => [
          ...h,
          { role: 'user', content: message },
          { role: 'assistant', content: advisory.problem_summary },
        ])
      },
      onOOS: (msg, messageId) => {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            messageId,
            role: 'assistant',
            type: 'oos',
            content: msg,
          },
        ])
      },
      onError: (errMsg) => {
        setMessages((prev) => [
          ...prev,
          { id: Date.now() + 1, role: 'assistant', type: 'error', content: errMsg },
        ])
      },
    })
  }

  const examples = (t.exampleQuestions || [])

  if (loadingSession) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {loadError && (
        <div className="px-4 pt-4 flex-shrink-0">
          <Alert variant="error" dismissible>{loadError}</Alert>
        </div>
      )}

      {messages.length === 0 ? (
        /* Empty state — centered welcome */
        <div className="flex-1 flex flex-col items-center justify-center px-6 gap-6 text-center">
          <div>
            <div className="w-14 h-14 rounded-2xl bg-field dark:bg-hc-accent dark:border-2 dark:border-hc-border flex items-center justify-center mx-auto mb-4">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-charcoal dark:text-hc-fg mb-1">{t.appName}</h1>
            <p className="text-sm text-gray-600 dark:text-hc-fg">{t.welcomeHeading}</p>
          </div>
          <div className="flex flex-wrap gap-2 justify-center max-w-md">
            {examples.map((q) => (
              <button
                key={q}
                onClick={() => handleSubmit(q)}
                disabled={streaming}
                className="text-sm bg-white border border-gray-200 rounded-full px-4 py-2
                  hover:border-field hover:bg-field/5 transition-colors text-gray-600
                  min-h-touch disabled:opacity-50
                  dark:bg-hc-bg dark:text-hc-fg dark:border-2 dark:border-hc-border dark:hover:bg-hc-fg dark:hover:text-hc-bg"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ChatHistory messages={messages} streaming={streaming} />
      )}

      {/* Suggestion chips row — shown above input when messages present */}
      {messages.length > 0 && !streaming && (
        <div className="flex-shrink-0 px-4 pt-2 flex gap-2 overflow-x-auto scrollbar-none">
          {examples.map((q) => (
            <button
              key={q}
              onClick={() => handleSubmit(q)}
              disabled={streaming}
              className="flex-shrink-0 text-xs bg-white border border-gray-200 rounded-full px-3 py-1.5
                hover:border-field hover:bg-field/5 transition-colors text-gray-600
                disabled:opacity-50
                dark:bg-hc-bg dark:text-hc-fg dark:border-2 dark:border-hc-border dark:hover:bg-hc-fg dark:hover:text-hc-bg"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <ChatInput onSubmit={handleSubmit} disabled={streaming} />
    </div>
  )
}
