export default function MessageBubble({ role, content, id }) {
  const isUser = role === 'user'
  const time = id
    ? new Date(id).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} my-2`}>
      <div className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
        {!isUser && (
          <div className="w-8 h-8 rounded-lg bg-field flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
        )}
        <div
          className={[
            'max-w-[80%] rounded-2xl px-4 py-3 text-base leading-relaxed',
            isUser
              ? 'bg-terracotta text-white rounded-tr-sm'
              : 'bg-white text-charcoal shadow-sm rounded-tl-sm border border-gray-100',
          ].join(' ')}
        >
          {content}
        </div>
      </div>
      {time && (
        <p className="text-xs text-gray-400 mt-1 px-1">{time}</p>
      )}
    </div>
  )
}
