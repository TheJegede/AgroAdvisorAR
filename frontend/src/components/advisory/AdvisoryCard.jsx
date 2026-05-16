import { Component } from 'react'
import ConfidenceBadge from './ConfidenceBadge'
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

function AdvisoryCardInner({ response, messageId }) {
  return (
    <div className="bg-white dark:bg-hc-surface rounded-card shadow-sm dark:shadow-none border border-gray-100 dark:border-2 dark:border-hc-border p-4 my-2 w-full max-w-2xl">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <ConfidenceBadge confidence={response.confidence} />
        <ContextMetaBar meta={response.context_meta} />
      </div>
      <ConfidenceExplainer explanation={response.confidence_explanation} />

      {response.confidence === 'Low' && <LowConfidenceBanner />}
      <WarningsBanner warnings={response.warnings} />
      <ProblemSummary summary={response.problem_summary} />
      <LikelyCauses causes={response.likely_causes} />
      <RecommendedActions actions={response.recommended_actions} />
      <ProductsRates products={response.products_rates} />
      <CitationsSection citations={response.citations} />
      <FeedbackWidget messageId={messageId} />
    </div>
  )
}

export default function AdvisoryCard({ response, messageId }) {
  return (
    <ErrorBoundary>
      <AdvisoryCardInner response={response} messageId={messageId} />
    </ErrorBoundary>
  )
}
