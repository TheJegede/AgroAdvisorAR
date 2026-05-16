export default function WarningsBanner({ warnings }) {
  if (!warnings?.length) return null
  return (
    <div className="flex flex-col gap-2 my-2">
      {warnings.map((w, i) => (
        <div key={i} className="bg-arred text-white dark:bg-hc-danger dark:text-hc-danger-fg dark:border-2 dark:border-hc-border rounded-lg px-4 py-3 flex items-start gap-2">
          <span className="text-lg leading-none">⚠️</span>
          <p className="text-sm leading-relaxed">{w}</p>
        </div>
      ))}
    </div>
  )
}
