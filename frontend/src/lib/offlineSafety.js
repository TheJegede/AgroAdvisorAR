// Build the offline notice for time-sensitive advisories. Offline = abstention:
// never show a frozen actionable answer; show "verify + call the human".
import { isCacheableAsReference } from './offlineTiering'
import { LABELS } from '../constants/i18n'

export function offlineSafetyMessage(advisory, lang = 'en') {
  if (isCacheableAsReference(advisory)) return null // reference content needs no stub
  const t = LABELS[lang] || LABELS.en
  return {
    title: t.offlineVerifyTitle,
    body: t.offlineVerifyBody,
    escalation: advisory && advisory.escalation ? advisory.escalation : t.offlineEscalationFallback,
  }
}
