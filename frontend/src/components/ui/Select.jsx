export default function Select({ label, id, options = [], error, className = '', ...rest }) {
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-charcoal">
          {label}
        </label>
      )}
      <select
        id={id}
        className={`
          w-full rounded-lg border px-4 py-3 text-base text-charcoal bg-white
          focus:outline-none focus:ring-2 focus:ring-field min-h-touch
          ${error ? 'border-arred focus:ring-arred' : 'border-gray-300'}
        `}
        {...rest}
      >
        <option value="">-- Select --</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="text-sm text-arred">{error}</p>}
    </div>
  )
}
