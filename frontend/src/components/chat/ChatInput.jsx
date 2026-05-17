import { useState, useRef, useEffect } from 'react'
import { useLang } from '../../contexts/LangContext'

const MAX_CHARS = 800
const WARN_AT = 600

export default function ChatInput({ onSubmit, disabled }) {
  const { t } = useLang()
  const [text, setText] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }, [text])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || disabled || trimmed.length > MAX_CHARS) return
    onSubmit(trimmed)
    setText('')
  }

  const remaining = MAX_CHARS - text.length
  const showCounter = text.length > WARN_AT

  return (
    <div
      className="bg-white dark:bg-hc-bg border-t border-gray-100 dark:border-hc-border dark:border-t-2 px-4 py-3 flex-shrink-0"
      style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))' }}
    >
      {showCounter && (
        <p className={`text-xs mb-2 text-right ${remaining < 0 ? 'text-arred dark:text-hc-danger' : 'text-gray-600 dark:text-hc-fg'}`}>
          {remaining} {t.charsRemaining}
        </p>
      )}

      <div className="flex items-end gap-2 rounded-2xl border border-gray-200 dark:border-hc-border dark:border-2 px-3 py-2 bg-white dark:bg-hc-bg
        focus-within:border-field focus-within:ring-1 focus-within:ring-field/20 dark:focus-within:ring-2 dark:focus-within:ring-hc-focus transition-all">

        {/* Paperclip — decorative */}
        <span className="flex-shrink-0 text-gray-400 dark:text-hc-fg p-1 mb-0.5" aria-hidden>
          <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
          </svg>
        </span>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t.inputPlaceholder}
          aria-label={t.chatInputLabel}
          disabled={disabled}
          rows={1}
          maxLength={MAX_CHARS + 10}
          className="flex-1 resize-none bg-transparent text-base text-charcoal dark:text-hc-fg
            focus:outline-none disabled:opacity-50
            min-h-[36px] max-h-[120px] overflow-y-auto leading-relaxed py-1"
        />

        {/* Mic — decorative */}
        <span className="flex-shrink-0 text-gray-400 dark:text-hc-fg p-1 mb-0.5" aria-hidden>
          <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
          </svg>
        </span>

        {/* Send — circle button */}
        <button
          type="button"
          data-testid="chat-send"
          onClick={submit}
          disabled={disabled || !text.trim() || text.length > MAX_CHARS}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-field text-white
            hover:bg-field-dark active:bg-field-dark transition-colors flex-shrink-0 mb-0.5
            disabled:opacity-40 disabled:cursor-not-allowed
            dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border dark:hover:bg-hc-fg"
          aria-label={t.sendMessage}
        >
          <svg width="18" height="18" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
          </svg>
        </button>
      </div>
    </div>
  )
}
