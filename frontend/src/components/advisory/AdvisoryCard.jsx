import { Component } from 'react'
import { useLang } from '../../contexts/LangContext'
import { LABELS } from '../../constants/i18n'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { offlineSafetyMessage } from '../../lib/offlineSafety'
import { isCacheableAsReference } from '../../lib/offlineTiering'
import OfflineSafetyStub from './OfflineSafetyStub'
import ConfidenceBadge from './ConfidenceBadge'
import NLIConfidenceBadge from './NLIConfidenceBadge'
import EscalationCard from './EscalationCard'
import ContextMetaBar from './ContextMetaBar'
import LowConfidenceBanner from './LowConfidenceBanner'
import WarningsBanner from './WarningsBanner'
import ProblemSummary from './ProblemSummary'
import LikelyCauses from './LikelyCauses'
import RecommendedActions from './RecommendedActions'
import ProductsRates from './ProductsRates'
import CitationsSection from './CitationsSection'
import ConfidenceExplainer from './ConfidenceExplainer'
import FeedbackWidget from './FeedbackWidget'
import SuppressedNotice from './SuppressedNotice'

class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(e) { return { error: e } }
  render() {
    if (this.state.error) {
      return (
        <div className="bg-arred/10 dark:bg-hc-surface border border-arred dark:border-2 dark:border-hc-danger rounded-card p-4 my-2 text-sm text-arred-dark dark:text-hc-danger">
          Could not display advisory response. Please try again.
        </div>
      )
    }
    return this.props.children
  }
}

const CROP_CHIP_CONFIG = {
  IN_SCOPE_RICE:      { key: 'cropChipRice',     cls: 'bg-field/10 text-field border-field/30' },
  IN_SCOPE_SOYBEANS:  { key: 'cropChipSoybeans', cls: 'bg-harvest/10 text-harvest-dark border-harvest/30' },
  IN_SCOPE_POULTRY:   { key: 'cropChipPoultry',  cls: 'bg-terracotta/10 text-terracotta border-terracotta/30' },
  SAFETY_CRITICAL:    { key: 'cropChipSafety',   cls: 'bg-arred/10 text-arred border-arred/30' },
}

function DetailSection({ heading, children }) {
  return (
    <div className="mt-4 border-t border-gray-100 dark:border-hc-border pt-4">
      <h4 className="text-sm font-semibold text-charcoal dark:text-hc-fg">{heading}</h4>
      {children}
    </div>
  )
}

// An advisory with no renderable content (e.g. a stray non-advisory frame that
// slipped through) must not paint an empty "Problem Summary" / "Confidence:"
// shell. Render nothing instead.
function hasRenderableContent(r) {
  if (!r || typeof r !== 'object') return false
  if (r.suppressed) return true
  return Boolean(
    r.problem_summary ||
    r.detailed_explanation ||
    (r.recommended_actions?.length) ||
    (r.likely_causes?.length) ||
    (r.products_rates?.length) ||
    (r.key_points?.length) ||
    (r.citations?.length)
  )
}

function AdvisoryCardInner({ response, messageId, category }) {
  const { t, lang } = useLang()
  const online = useOnlineStatus()
  if (!hasRenderableContent(response)) return null
  const cleanCat = category ? category.split(':')[0] : category
  const chipConfig = CROP_CHIP_CONFIG[cleanCat]

  // Offline = abstention. When offline AND the content is time-sensitive
  // (rates/spray/warnings/diagnostic), never show the frozen actionable body —
  // route to the human via the verify + escalation stub instead.
  const offlineStub = !online ? offlineSafetyMessage(response, lang) : null
  if (offlineStub) {
    return (
      <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-4 my-2 w-full max-w-2xl">
        <OfflineSafetyStub message={offlineStub} />
      </div>
    )
  }
  const showReferenceBadge = !online && isCacheableAsReference(response)

  return (
    <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-4 my-2 w-full max-w-2xl">
      {showReferenceBadge && (
        <span className="mb-2 inline-block rounded bg-stone-200 px-2 py-0.5 text-xs text-stone-700">
          {(LABELS[lang] || LABELS.en).offlineReferenceBadge}
        </span>
      )}
      {/* Orientation row: crop chip + context meta only — no confidence badges */}
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {chipConfig && (
            <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border ${chipConfig.cls}`}>
              {t[chipConfig.key]}
            </span>
          )}
        </div>
        <ContextMetaBar meta={response.context_meta} />
      </div>

      {response.suppressed ? (
        <SuppressedNotice escalation={response.escalation} />
      ) : response.response_type === 'informational' ? (
        <>
          <ProblemSummary summary={response.problem_summary} />
          {response.detailed_explanation && (
            <DetailSection heading={t.detailedExplanation}>
              <p className="text-sm text-charcoal-light dark:text-hc-fg mt-2 leading-relaxed whitespace-pre-wrap">
                {response.detailed_explanation}
              </p>
            </DetailSection>
          )}
          {response.key_points?.length > 0 && (
            <DetailSection heading={t.keyPoints}>
              <ul className="list-disc pl-5 mt-2 space-y-1">
                {response.key_points.map((p, idx) => (
                  <li key={idx} className="text-sm text-charcoal-light dark:text-hc-fg leading-relaxed">{p}</li>
                ))}
              </ul>
            </DetailSection>
          )}
          <RecommendedActions actions={response.recommended_actions} />
          {/* EscalationCard is gated: when suppressed, SuppressedNotice already shows
              the escalation contact — don't duplicate it in EscalationCard. */}
          {!response.suppressed && <EscalationCard escalation={response.escalation} />}
          <WarningsBanner warnings={response.warnings} />
          <div className="flex items-center gap-2 flex-wrap mt-4">
            <ConfidenceBadge confidence={response.confidence} />
            <NLIConfidenceBadge confidence_score={response.confidence_score} />
          </div>
          <ConfidenceExplainer explanation={response.confidence_explanation} />
          {response.confidence === 'Low' && <LowConfidenceBanner />}
        </>
      ) : (
        <>
          <ProblemSummary summary={response.problem_summary} />
          <RecommendedActions actions={response.recommended_actions} />
          <ProductsRates products={response.products_rates} />
          <LikelyCauses causes={response.likely_causes} />
          {/* EscalationCard is gated: when suppressed, SuppressedNotice already shows
              the escalation contact — don't duplicate it in EscalationCard. */}
          {!response.suppressed && <EscalationCard escalation={response.escalation} />}
          <WarningsBanner warnings={response.warnings} />
          <div className="flex items-center gap-2 flex-wrap mt-4">
            <ConfidenceBadge confidence={response.confidence} />
            <NLIConfidenceBadge confidence_score={response.confidence_score} />
          </div>
          <ConfidenceExplainer explanation={response.confidence_explanation} />
          {response.confidence === 'Low' && <LowConfidenceBanner />}
        </>
      )}
      <CitationsSection citations={response.citations} />
      <FeedbackWidget messageId={messageId} />
    </div>
  )
}

export default function AdvisoryCard({ response, messageId, category }) {
  return (
    <ErrorBoundary>
      <AdvisoryCardInner response={response} messageId={messageId} category={category} />
    </ErrorBoundary>
  )
}
