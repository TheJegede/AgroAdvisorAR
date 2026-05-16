import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import AdvisoryCard from '../advisory/AdvisoryCard'
import OutOfScopeCard from './OutOfScopeCard'
import TypingIndicator from './TypingIndicator'

export default function ChatHistory({ messages, streaming }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col">
      {messages.map((msg) => {
        if (msg.type === 'text') {
          return <MessageBubble key={msg.id} role={msg.role} content={msg.content} id={msg.id} />
        }
        if (msg.type === 'advisory') {
          return <AdvisoryCard key={msg.id} response={msg.content} />
        }
        if (msg.type === 'oos') {
          return <OutOfScopeCard key={msg.id} message={msg.content} />
        }
        if (msg.type === 'error') {
          return (
            <MessageBubble key={msg.id} role="assistant" content={msg.content} id={msg.id} />
          )
        }
        return null
      })}
      {streaming && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  )
}
