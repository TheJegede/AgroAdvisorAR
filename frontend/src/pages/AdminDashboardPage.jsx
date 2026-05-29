import { lazy, Suspense, useState, useEffect } from 'react'
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useAdminMetrics, useDriftReportAdmin } from '../hooks/useAdmin'
import Spinner from '../components/ui/Spinner'
import Alert from '../components/ui/Alert'
import api from '../lib/api'
import { AR_COUNTIES } from '../constants/counties'

const LANG_COLORS = { en: '#2D6A4F', es: '#E9A228' }
const FEEDBACK_COLORS = { positive: '#2D6A4F', negative: '#CC2936' }
const ARCountyMap = lazy(() => import('../components/admin/ARCountyMap'))

function MapFallback() {
  return <div className="min-h-[220px] rounded-md bg-gray-50 dark:bg-hc-bg" />
}

function KpiCard({ label, value }) {
  return (
    <div className="bg-white rounded-card border border-gray-100 p-4 flex flex-col dark:bg-hc-surface dark:border-2 dark:border-hc-border">
      <span className="text-xs uppercase tracking-wide text-gray-500 dark:text-hc-fg">{label}</span>
      <span className="text-2xl font-bold text-charcoal dark:text-hc-fg mt-1">{value}</span>
    </div>
  )
}

function SectionCard({ title, children }) {
  return (
    <div className="bg-white rounded-card border border-gray-100 p-4 dark:bg-hc-surface dark:border-2 dark:border-hc-border">
      <h2 className="text-sm font-semibold text-charcoal dark:text-hc-fg mb-3">{title}</h2>
      {children}
    </div>
  )
}

const PAGE_SIZE = 20

function countyName(fips) {
  return AR_COUNTIES[fips]?.name || fips
}

function truncate(str, n) {
  if (!str) return '—'
  return str.length > n ? str.slice(0, n) + '…' : str
}

export default function AdminDashboardPage() {
  const { t } = useLang()
  const { metrics, loading, error } = useAdminMetrics()
  const { reports: driftReports, loading: driftLoading, error: driftError } = useDriftReportAdmin()
  const [activeTab, setActiveTab] = useState('overview')
  const [mapLayer, setMapLayer] = useState('queries')
  const [aquiferData, setAquiferData] = useState({})
  useEffect(() => {
    if (mapLayer !== 'aquifer' || Object.keys(aquiferData).length > 0) return
    api.get('/admin/aquifer-stress')
      .then(res => setAquiferData(res.data.data || {}))
      .catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapLayer])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(0)

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert variant="error">{error}</Alert>
      </div>
    )
  }

  if (!metrics) return null

  const languageData = Object.entries(metrics.language_split).map(([k, v]) => ({
    name: k.toUpperCase(),
    value: v,
    color: LANG_COLORS[k] || '#888',
  }))

  const feedbackData = [
    { name: 'positive', value: metrics.feedback_distribution.positive, color: FEEDBACK_COLORS.positive },
    { name: 'negative', value: metrics.feedback_distribution.negative, color: FEEDBACK_COLORS.negative },
  ]

  const evalRunsData = [...metrics.recent_eval_runs]
    .reverse()
    .map((r) => ({
      run_at: r.run_at?.slice(0, 10),
      mrr: Number(r.mrr_at_5 ?? 0),
      ndcg: Number(r.ndcg_at_5 ?? 0),
      status: r.run_status ?? r.status ?? 'not_run',
    }))

  const filteredDrift = driftReports.filter((r) => {
    if (dateFrom && r.incident_date < dateFrom) return false
    if (dateTo && r.incident_date > dateTo) return false
    return true
  })

  const driftCountMap = driftReports.reduce((acc, r) => {
    acc[r.county_fips] = (acc[r.county_fips] || 0) + 1
    return acc
  }, {})

  const totalPages = Math.ceil(filteredDrift.length / PAGE_SIZE)
  const pageItems = filteredDrift.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h1 className="text-xl font-bold text-charcoal dark:text-hc-fg">{t.adminDashboard}</h1>
        <Link
          to="/admin/queue"
          className="bg-field text-white text-sm font-bold rounded-md px-4 py-2 hover:bg-field/90 min-h-touch flex items-center dark:bg-hc-accent dark:text-hc-accent-fg dark:border-2 dark:border-hc-border"
        >
          {t.adminQueue} →
        </Link>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-4 border-b border-gray-200 dark:border-hc-border">
        {['overview', 'drift'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={[
              'px-4 py-2 text-sm font-semibold rounded-t-lg border-b-2 transition-colors',
              activeTab === tab
                ? 'border-field text-field dark:border-hc-accent dark:text-hc-accent'
                : 'border-transparent text-gray-500 hover:text-charcoal dark:text-hc-fg',
            ].join(' ')}
          >
            {tab === 'overview' ? 'Overview' : 'Drift Reports'}
          </button>
        ))}
      </div>

      {activeTab === 'drift' && (
        <div className="space-y-4">
          {driftError && <Alert variant="error">{driftError}</Alert>}

          {/* Choropleth toggle + map */}
          <SectionCard title="Drift incident map">
            <div className="flex gap-2 mb-3">
              {[['queries', 'Query Volume'], ['drift', 'Drift Reports'], ['aquifer', 'Aquifer Stress']].map(([layer, label]) => (
                <button
                  key={layer}
                  onClick={() => setMapLayer(layer)}
                  className={[
                    'px-3 py-1.5 rounded-lg text-sm font-semibold border transition-colors',
                    mapLayer === layer
                      ? layer === 'drift'
                        ? 'bg-harvest text-white border-harvest'
                        : layer === 'aquifer'
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-field text-white border-field'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                  ].join(' ')}
                >
                  {label}
                </button>
              ))}
            </div>
            <Suspense fallback={<MapFallback />}>
              <ARCountyMap
                countyData={metrics?.county_query_volume ?? []}
                dataLayer={mapLayer}
                driftData={driftCountMap}
                aquiferData={aquiferData}
              />
            </Suspense>
          </SectionCard>

          {/* Date filter */}
          <SectionCard title="Filter by incident date">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs text-gray-500 dark:text-hc-fg mb-1">From</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setPage(0) }}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-hc-fg mb-1">To</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setPage(0) }}
                  className="rounded-lg border border-gray-200 px-3 py-2 text-sm dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg"
                />
              </div>
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(''); setDateTo(''); setPage(0) }}
                  className="text-sm text-gray-500 hover:text-charcoal dark:text-hc-fg underline"
                >
                  Clear
                </button>
              )}
              <span className="text-xs text-gray-400 dark:text-hc-fg ml-auto">
                {filteredDrift.length} report{filteredDrift.length !== 1 ? 's' : ''}
              </span>
            </div>
          </SectionCard>

          {/* Report list */}
          <SectionCard title="Reports">
            {driftLoading ? (
              <Spinner />
            ) : filteredDrift.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-hc-fg">No drift reports found.</p>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 dark:text-hc-fg border-b border-gray-100 dark:border-hc-border">
                        <th className="pb-2 pr-3 font-semibold">County</th>
                        <th className="pb-2 pr-3 font-semibold">Date</th>
                        <th className="pb-2 pr-3 font-semibold">Crop</th>
                        <th className="pb-2 pr-3 font-semibold">Symptoms</th>
                        <th className="pb-2 font-semibold">ASPB</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50 dark:divide-hc-border">
                      {pageItems.map((r) => (
                        <tr key={r.id} className="text-charcoal dark:text-hc-fg">
                          <td className="py-2 pr-3">{countyName(r.county_fips)}</td>
                          <td className="py-2 pr-3 whitespace-nowrap">{r.incident_date}</td>
                          <td className="py-2 pr-3 capitalize">{r.affected_crop || '—'}</td>
                          <td className="py-2 pr-3 text-gray-500 dark:text-hc-fg">{truncate(r.symptoms_description, 60)}</td>
                          <td className="py-2">{r.aspb_submitted ? '✓' : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-3">
                    <button
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                      className="px-3 py-1 rounded-lg border border-gray-200 text-sm disabled:opacity-40 hover:bg-gray-50 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
                    >
                      ← Prev
                    </button>
                    <span className="text-xs text-gray-500 dark:text-hc-fg">
                      Page {page + 1} / {totalPages}
                    </span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                      className="px-3 py-1 rounded-lg border border-gray-200 text-sm disabled:opacity-40 hover:bg-gray-50 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg"
                    >
                      Next →
                    </button>
                  </div>
                )}
              </>
            )}
          </SectionCard>
        </div>
      )}

      {activeTab === 'overview' && (<>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KpiCard label={t.metricRegisteredUsers} value={metrics.totals.registered_users} />
        <KpiCard label={t.metricSessions} value={metrics.totals.sessions} />
        <KpiCard label={t.metricAssistantMessages} value={metrics.totals.assistant_messages} />
        <KpiCard label={t.metricFeedback} value={metrics.totals.feedback_rows} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <SectionCard title={t.metricsLanguage}>
          {languageData.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-hc-fg">No data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={languageData} dataKey="value" nameKey="name" outerRadius={80} label>
                  {languageData.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        <SectionCard title={t.metricsFeedback}>
          {feedbackData[0].value + feedbackData[1].value === 0 ? (
            <p className="text-sm text-gray-500 dark:text-hc-fg">No feedback yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={feedbackData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value">
                  {feedbackData.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <SectionCard title={t.metricsCounty}>
          {metrics.county_query_volume.length === 0 ? (
            <p className="text-sm text-gray-500">No data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(220, metrics.county_query_volume.length * 24)}>
              <BarChart layout="vertical" data={metrics.county_query_volume} margin={{ left: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="county_name" width={120} />
                <Tooltip />
                <Bar dataKey="count" fill="#2D6A4F" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </SectionCard>

        <SectionCard title={t.metricsCountyMap}>
          <Suspense fallback={<MapFallback />}>
            <ARCountyMap countyData={metrics.county_query_volume} />
          </Suspense>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
        <SectionCard title={t.metricsHumanEval}>
          <div className="flex flex-col gap-2 text-sm text-charcoal dark:text-hc-fg">
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-hc-fg">{t.queueScore} count</span>
              <span className="font-semibold">{metrics.human_eval_summary.score_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-hc-fg">Mean accuracy</span>
              <span className="font-semibold">
                {metrics.human_eval_summary.mean_accuracy_score ?? '—'}
              </span>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t.metricsEvalRuns}>
          {evalRunsData.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-hc-fg">No automated eval runs logged yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={evalRunsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="run_at" />
                <YAxis domain={[0, 1]} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="mrr" stroke="#2D6A4F" />
                <Line type="monotone" dataKey="ndcg" stroke="#E9A228" />
              </LineChart>
            </ResponsiveContainer>
          )}
          {evalRunsData.some((r) => r.status !== 'ok') && (
            <p className="text-xs text-gray-500 dark:text-hc-fg mt-2">
              Latest status: {evalRunsData[evalRunsData.length - 1]?.status}
            </p>
          )}
        </SectionCard>
      </div>

      <SectionCard title={t.metricsTopQueries}>
        {metrics.top_user_queries.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-hc-fg">No queries yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-hc-border">
            {metrics.top_user_queries.map((q, i) => (
              <li key={i} className="flex justify-between gap-3 py-1.5 text-sm">
                <span className="text-charcoal dark:text-hc-fg truncate" title={q.query}>{q.query}</span>
                <span className="text-gray-500 dark:text-hc-fg flex-shrink-0">{q.count}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      </>)}
    </div>
  )
}
