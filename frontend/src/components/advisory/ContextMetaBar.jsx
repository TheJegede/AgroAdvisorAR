import { useLang } from '../../contexts/LangContext'
import { getCountyName } from '../../constants/counties'

function Pill({ label, available }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium dark:border-2 dark:border-hc-border
      ${available ? 'bg-field/10 text-field-dark dark:bg-hc-bg dark:text-hc-fg' : 'bg-gray-100 text-gray-600 dark:bg-hc-bg dark:text-hc-fg'}`}>
      <span>{available ? '✓' : '–'}</span>
      {label}
    </span>
  )
}

export default function ContextMetaBar({ meta }) {
  const { t } = useLang()
  if (!meta) return null
  return (
    <div className="flex flex-wrap items-center gap-2 mt-1">
      <span className="text-xs text-gray-500 dark:text-hc-fg font-medium">{getCountyName(meta.county_fips)}</span>
      <Pill label={t.soilData} available={meta.soil_data_available} />
      <Pill label={t.weatherData} available={meta.weather_data_available} />
    </div>
  )
}
