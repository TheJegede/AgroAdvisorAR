import Spinner from './Spinner'

const VARIANTS = {
  primary:   'bg-field text-white hover:bg-field-dark active:bg-field-dark',
  secondary: 'bg-harvest text-charcoal hover:bg-harvest-dark active:bg-harvest-dark',
  danger:    'bg-arred text-white hover:bg-arred-dark active:bg-arred-dark',
  ghost:     'bg-transparent text-field border border-field hover:bg-field/10',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2.5 text-base',
  lg: 'px-6 py-3 text-lg',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  type = 'button',
  onClick,
  children,
  className = '',
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        inline-flex items-center justify-center gap-2 rounded-lg font-semibold
        min-h-touch transition-colors duration-150 cursor-pointer
        disabled:opacity-50 disabled:cursor-not-allowed
        ${VARIANTS[variant]} ${SIZES[size]} ${className}
      `}
    >
      {loading && <Spinner size={18} />}
      {children}
    </button>
  )
}
