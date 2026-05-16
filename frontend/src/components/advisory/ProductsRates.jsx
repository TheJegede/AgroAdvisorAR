import { useLang } from '../../contexts/LangContext'

export default function ProductsRates({ products }) {
  const { t } = useLang()
  if (!products?.length) return null
  return (
    <div className="my-3">
      <h2 className="text-base font-semibold text-charcoal mb-2">{t.products}</h2>

      {/* Mobile: cards */}
      <div className="flex flex-col gap-3 md:hidden">
        {products.map((p, i) => (
          <div key={i} className="rounded-lg border border-gray-200 p-4 bg-white">
            <p className="font-semibold text-sm text-charcoal mb-2">{p.product}</p>
            <div className="flex flex-col gap-1 text-sm text-gray-700">
              <div><span className="font-medium">{t.rate}:</span> {p.rate}</div>
              <div><span className="font-medium">{t.appMethod}:</span> {p.application_method}</div>
              {p.pre_harvest_interval && (
                <div><span className="font-medium">{t.phi}:</span> {p.pre_harvest_interval}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Desktop: table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-2 font-semibold text-charcoal">{t.product}</th>
              <th className="text-left px-4 py-2 font-semibold text-charcoal">{t.rate}</th>
              <th className="text-left px-4 py-2 font-semibold text-charcoal">{t.appMethod}</th>
              <th className="text-left px-4 py-2 font-semibold text-charcoal">{t.phi}</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-charcoal">{p.product}</td>
                <td className="px-4 py-3 text-gray-700">{p.rate}</td>
                <td className="px-4 py-3 text-gray-700">{p.application_method}</td>
                <td className="px-4 py-3 text-gray-700">{p.pre_harvest_interval || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
