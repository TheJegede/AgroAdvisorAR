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

class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(e) { return { error: e } }
  render() {
    if (this.state.error) {
      return (
        <div className="bg-arred/10 border border-arred rounded-card p-4 my-2 text-sm text-arred-dark">
          Could not display advisory response. Please try again.
        </div>
      )
    }
    return this.props.children
  }
}

function AdvisoryCardInner({ response }) {
  return (
    <div className="bg-white rounded-card shadow-sm border border-gray-100 p-4 my-2 w-full max-w-2xl">
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
    </div>
  )
}

export default function AdvisoryCard({ response }) {
  return (
    <ErrorBoundary>
      <AdvisoryCardInner response={response} />
    </ErrorBoundary>
  )
}
