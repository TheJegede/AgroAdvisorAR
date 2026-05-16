export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-4 py-3 w-fit bg-white rounded-card shadow-sm border border-gray-100 my-2">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="w-2 h-2 rounded-full bg-field animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}
