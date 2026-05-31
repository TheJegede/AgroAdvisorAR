import { Component } from 'react'
import { useLang } from '../../contexts/LangContext'
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

function CropChip({ category }) {
  const { t } = useLang()
  const config = CROP_CHIP_CONFIG[category]
  if (!config) return null
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full border ${config.cls}`}>
      {t[config.key]}
    </span>
  )
}

function AdvisoryCardInner({ response, messageId, category }) {
  return (
    <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-4 my-2 w-full max-w-2xl">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <ConfidenceBadge confidence={response.confidence} />
          <NLIConfidenceBadge confidence_score={response.confidence_score} />
          <CropChip category={category} />
        </div>
        <ContextMetaBar meta={response.context_meta} />
      </div>
      <ConfidenceExplainer explanation={response.confidence_explanation} />
      {/* EscalationCard is gated: when suppressed, SuppressedNotice already shows
          the escalation contact — don't duplicate it in EscalationCard. */}
      {!response.suppressed && <EscalationCard escalation={response.escalation} />}

      {response.confidence === 'Low' && <LowConfidenceBanner />}

      {response.suppressed ? (
        <SuppressedNotice escalation={response.escalation} />
      ) : (
        <>
          <WarningsBanner warnings={response.warnings} />
          <ProblemSummary summary={response.problem_summary} />
          <LikelyCauses causes={response.likely_causes} />
          <RecommendedActions actions={response.recommended_actions} />
          <ProductsRates products={response.products_rates} />
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
