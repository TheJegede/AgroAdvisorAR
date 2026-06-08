import { useLang } from '../contexts/LangContext'
import { useSprayRecords } from '../hooks/useSprayRecords'
import Alert from '../components/ui/Alert'

const STATUS_BADGE = {
  pass: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100',
  fail: 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100',
  needs_confirmation: 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100',
}

export default function SprayRecordsPage() {
  const { lang } = useLang()
  const es = lang === 'es'
  const { records, loading, error } = useSprayRecords()

  return (
    <div className="flex-1 overflow-y-auto bg-parchment dark:bg-hc-bg">
      <div className="max-w-2xl mx-auto py-8 px-4">
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
          <h1 className="text-lg font-bold text-charcoal dark:text-hc-fg mb-4">
            {es ? 'Registros de aplicación' : 'Spray records'}
          </h1>
          {error && <Alert variant="error" className="mb-4">{error}</Alert>}
          {loading ? (
            <p className="text-sm text-gray-500 dark:text-hc-fg">{es ? 'Cargando...' : 'Loading...'}</p>
          ) : records.length === 0 ? (
            <Alert variant="info">{es ? 'Aún no hay registros guardados.' : 'No saved records yet.'}</Alert>
          ) : (
            <ul className="space-y-2" data-testid="records-list">
              {records.map((r) => (
                <li key={r.id} className="flex items-center justify-between bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                  <div className="text-sm text-charcoal dark:text-hc-fg">
                    <span className="font-semibold">{r.product}</span>
                    {' · '}{new Date(r.applied_at).toLocaleDateString()}
                    <span className={`ml-2 text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[r.overall_status] || ''}`}>
                      {r.overall_status}
                    </span>
                  </div>
                  <a
                    href={`/api/v1/dicamba/record/${r.id}/pdf`}
                    className="text-sm font-semibold text-field-dark underline min-h-touch flex items-center"
                  >
                    PDF
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
