import { useState } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json'

// Interpolate between light parchment (#F0F7F3) and field green (#2D6A4F)
function countyColor(count, maxCount) {
  if (count === 0) return '#EEF2EF'
  const t = Math.sqrt(count / maxCount)
  const r = Math.round(240 + (45 - 240) * t)
  const g = Math.round(242 + (106 - 242) * t)
  const b = Math.round(240 + (79 - 240) * t)
  return `rgb(${r},${g},${b})`
}

// Interpolate between light amber (#FEF9EE) and harvest amber (#E9A228)
function driftColor(count, maxCount) {
  if (count === 0) return '#FEF9EE'
  const t = Math.sqrt(count / maxCount)
  const r = Math.round(254 + (233 - 254) * t)
  const g = Math.round(249 + (162 - 249) * t)
  const b = Math.round(238 + (40 - 238) * t)
  return `rgb(${r},${g},${b})`
}

function aquiferColor(stress) {
  if (stress === 'critical') return '#EF4444'  // red-500
  if (stress === 'stressed') return '#F59E0B'  // amber-500
  return '#10B981'                             // emerald-500
}

export default function ARCountyMap({ countyData = [], dataLayer = 'queries', driftData = {}, aquiferData = {} }) {
  const [tooltip, setTooltip] = useState(null)

  const isDrift = dataLayer === 'drift'
  const isAquifer = dataLayer === 'aquifer'

  const countByFips = {}
  let maxCount = 1
  if (isDrift) {
    Object.entries(driftData).forEach(([fips, count]) => {
      countByFips[fips] = count
      if (count > maxCount) maxCount = count
    })
  } else if (!isAquifer) {
    countyData.forEach(({ county_fips, count }) => {
      countByFips[county_fips] = count
      if (count > maxCount) maxCount = count
    })
  }

  function getFips(geoId) {
    return String(geoId).padStart(5, '0')
  }

  return (
    <div className="relative w-full" style={{ minHeight: 220 }}>
      <ComposableMap
        projection="geoAlbersUsa"
        projectionConfig={{ scale: 4800, center: [-92.4, 34.75] }}
        style={{ width: '100%', height: 'auto' }}
        role="img"
        aria-label="Arkansas county map"
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies
              .filter(geo => getFips(geo.id).startsWith('05'))
              .map(geo => {
                const fips = getFips(geo.id)
                const count = countByFips[fips] || 0
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={
                      isAquifer
                        ? aquiferColor(aquiferData[fips] || 'normal')
                        : isDrift
                          ? driftColor(count, maxCount)
                          : countyColor(count, maxCount)
                    }
                    stroke="#ffffff"
                    strokeWidth={0.8}
                    onMouseEnter={() => {
                      const name = geo.properties?.name || fips
                      setTooltip({ name, count, fips })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    style={{
                      default: { outline: 'none' },
                      hover: { outline: 'none', opacity: 0.75, cursor: 'pointer' },
                      pressed: { outline: 'none' },
                    }}
                  />
                )
              })
          }
        </Geographies>
      </ComposableMap>

      {tooltip && (
        <div className="absolute top-2 right-2 bg-white border border-gray-200 rounded-md px-3 py-1.5 text-xs shadow-sm pointer-events-none dark:bg-hc-surface dark:border-hc-border dark:text-hc-fg">
          <span className="font-semibold">{tooltip.name} County</span>
          <span className="text-gray-500 dark:text-hc-fg ml-2">
            {isAquifer
              ? (aquiferData[tooltip?.fips] || 'normal')
              : `${tooltip.count} ${isDrift ? 'reports' : 'queries'}`}
          </span>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-2 mt-2 text-xs text-gray-500 dark:text-hc-fg px-1">
        {isAquifer ? (
          <>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#10B981'}} /> Normal</span>
            <span className="flex items-center gap-1 ml-2"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#F59E0B'}} /> Stressed</span>
            <span className="flex items-center gap-1 ml-2"><span className="w-3 h-3 rounded-full inline-block" style={{background:'#EF4444'}} /> Critical</span>
          </>
        ) : (
          <>
            <span>0</span>
            <div
              className="flex-1 h-2 rounded"
              style={{ background: isDrift
                ? 'linear-gradient(to right, #FEF9EE, #E9A228)'
                : 'linear-gradient(to right, #EEF2EF, #2D6A4F)' }}
            />
            <span>{maxCount}</span>
            <span className="ml-1">{isDrift ? 'reports' : 'queries'}</span>
          </>
        )}
      </div>
    </div>
  )
}
