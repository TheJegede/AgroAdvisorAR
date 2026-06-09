export default function OfflineSafetyStub({ message }) {
  if (!message) return null
  return (
    <div role="alert" className="rounded-lg border border-amber-500 bg-amber-50 p-4 text-charcoal">
      <p className="font-semibold">⚠ {message.title}</p>
      <p className="mt-1 text-sm">{message.body}</p>
      <p className="mt-2 text-sm font-medium">{message.escalation}</p>
    </div>
  )
}
