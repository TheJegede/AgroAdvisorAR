export default function Skeleton({ className = '', variant = 'card', count = 1 }) {
  // Single skeleton is announced as a status; list items below are decorative
  // (the list wrapper carries the status role), so they get aria-hidden.
  const a11y = count > 1
    ? { 'aria-hidden': 'true' }
    : { role: 'status', 'aria-busy': 'true', 'aria-label': 'Loading' }

  const renderItem = (key) => {
    if (variant === 'circle') {
      return (
        <div
          key={key}
          {...a11y}
          className={`rounded-full animate-shimmer bg-gray-200 dark:bg-hc-muted ${className}`}
        />
      )
    }

    if (variant === 'text') {
      return (
        <div
          key={key}
          {...a11y}
          className={`h-4 rounded animate-shimmer bg-gray-200 dark:bg-hc-muted ${className}`}
        />
      )
    }

    // Default: Card layout matching the card/message bubble (avatar circle + two text lines)
    return (
      <div
        key={key}
        {...a11y}
        className={`flex items-start gap-3 p-4 bg-white dark:bg-hc-surface rounded-card border border-gray-100 dark:border-2 dark:border-hc-border w-full max-w-2xl my-2 ${className}`}
      >
        {/* Avatar Circle */}
        <div className="w-8 h-8 rounded-full animate-shimmer bg-gray-200 dark:bg-hc-muted flex-shrink-0" />

        {/* Two Text Lines */}
        <div className="flex-1 space-y-2.5 py-1">
          <div className="h-4 bg-gray-200 dark:bg-hc-muted rounded w-3/4 animate-shimmer" />
          <div className="h-4 bg-gray-200 dark:bg-hc-muted rounded w-1/2 animate-shimmer" />
        </div>
      </div>
    )
  }

  if (count > 1) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading" className="flex flex-col gap-2 w-full">
        {Array.from({ length: count }).map((_, i) => renderItem(i))}
      </div>
    )
  }

  return renderItem(0)
}
