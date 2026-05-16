import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend,
} from 'recharts'
import { Link } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useAdminMetrics } from '../hooks/useAdmin'
import Spinner from '../components/ui/Spinner'
import Alert from '../components/ui/Alert'

const LANG_COLORS = { en: '#2D6A4F', es: '#E9A228' }
const FEEDBACK_COLORS = { positive: '#2D6A4F', negative: '#CC2936' }

function KpiCard({ label, value }) {
  return (
    <div className="bg-white rounded-card border border-gray-100 p-4 flex flex-col">
      <span className="text-xs uppercase tracking-wide text-gray-500">{label}</span>
      <span className="text-2xl font-bold text-charcoal mt-1">{value}</span>
    </div>
  )
}

function SectionCard({ title, children }) {
  return (
    <div className="bg-white rounded-card border border-gray-100 p-4">
      <h2 className="text-sm font-semibold text-charcoal mb-3">{title}</h2>
      {children}
    </div>
  )
}

export default function AdminDashboardPage() {
  const { t } = useLang()
  const { metrics, loading, error } = useAdminMetrics()

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
    }))

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h1 className="text-xl font-bold text-charcoal">{t.adminDashboard}</h1>
        <Link
          to="/admin/queue"
          className="bg-field text-white text-sm font-medium rounded-md px-4 py-2 hover:bg-field/90 min-h-touch flex items-center"
        >
          {t.adminQueue} →
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KpiCard label={t.metricRegisteredUsers} value={metrics.totals.registered_users} />
        <KpiCard label={t.metricSessions} value={metrics.totals.sessions} />
        <KpiCard label={t.metricAssistantMessages} value={metrics.totals.assistant_messages} />
        <KpiCard label={t.metricFeedback} value={metrics.totals.feedback_rows} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <SectionCard title={t.metricsLanguage}>
          {languageData.length === 0 ? (
            <p className="text-sm text-gray-500">No data yet.</p>
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
            <p className="text-sm text-gray-500">No feedback yet.</p>
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
        <SectionCard title={t.metricsHumanEval}>
          <div className="flex flex-col gap-2 text-sm text-charcoal">
            <div className="flex justify-between">
              <span className="text-gray-500">{t.queueScore} count</span>
              <span className="font-semibold">{metrics.human_eval_summary.score_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Mean accuracy</span>
              <span className="font-semibold">
                {metrics.human_eval_summary.mean_accuracy_score ?? '—'}
              </span>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={t.metricsEvalRuns}>
          {evalRunsData.length === 0 ? (
            <p className="text-sm text-gray-500">No automated eval runs logged yet.</p>
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
        </SectionCard>
      </div>

      <SectionCard title={t.metricsTopQueries}>
        {metrics.top_user_queries.length === 0 ? (
          <p className="text-sm text-gray-500">No queries yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {metrics.top_user_queries.map((q, i) => (
              <li key={i} className="flex justify-between gap-3 py-1.5 text-sm">
                <span className="text-charcoal truncate" title={q.query}>{q.query}</span>
                <span className="text-gray-500 flex-shrink-0">{q.count}</span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  )
}
