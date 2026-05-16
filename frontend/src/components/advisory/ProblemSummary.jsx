import { useLang } from '../../contexts/LangContext'

export default function ProblemSummary({ summary }) {
  const { t } = useLang()
  return (
    <div className="my-3">
      <h2 className="text-base font-semibold text-charcoal mb-1">{t.problemSummary}</h2>
      <p className="text-base text-gray-700 leading-relaxed">{summary}</p>
    </div>
  )
}
