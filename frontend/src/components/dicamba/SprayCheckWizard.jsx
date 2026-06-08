import { useState } from 'react'
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { useLang } from '../../contexts/LangContext'
import { useSprayCheck, getSprayStepErrors } from '../../hooks/useSprayCheck'
import Alert from '../ui/Alert'

// Bundlers strip Leaflet's default marker URLs; re-point them at the imported assets.
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

const TOTAL_STEPS = 3
// Arkansas centroid — the field is almost always in-state.
const AR_CENTER = [34.8, -92.2]

// Approved over-the-top products. Hardcoded from dicamba_rules.json (2026-AR-OTT);
// a rules-fetch endpoint can replace this later without touching the UI.
const APPROVED_PRODUCTS = [
  { id: 'engenia', name: 'Engenia' },
  { id: 'xtendimax', name: 'XtendiMax with VaporGrip' },
  { id: 'tavium', name: 'Tavium Plus VaporGrip' },
]

const INPUT_CLS =
  'w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-base text-charcoal outline-none transition placeholder:text-gray-400 focus:border-field focus:ring-2 focus:ring-field/20 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'
const INPUT_ERR_CLS = 'border-red-400/60 focus:border-red-400/80 focus:ring-red-300/25'
const BTN_PRIMARY_CLS =
  'flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-field px-5 py-3 font-bold text-white shadow transition hover:bg-field/90 focus:outline-none focus:ring-2 focus:ring-field/50 disabled:opacity-60 min-h-touch dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:text-hc-accent-fg'
const BTN_GHOST_CLS =
  'flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 font-semibold text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 min-h-touch dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'

const STEP_TITLES_EN = ['Eligibility', 'Live Conditions', 'Confirm & Result']
const STEP_TITLES_ES = ['Elegibilidad', 'Condiciones Actuales', 'Confirmar y Resultado']

// Status → high-contrast badge (≥4.5:1 per the design audit Low-badge fix).
const STATUS_BADGE = {
  pass: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100',
  fail: 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100',
  needs_confirmation: 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100',
}

function statusLabel(status, es) {
  if (status === 'pass') return es ? 'Cumple' : 'Met'
  if (status === 'fail') return es ? 'No cumple' : 'Not met'
  return es ? 'Confirmar' : 'Confirm'
}

function tierLabel(tier, es) {
  return tier === 'verifiable_fact'
    ? (es ? 'Dato verificable' : 'Verifiable fact')
    : (es ? 'Requiere confirmación' : 'Confirm on the ground')
}

function StepIndicator({ step, titles }) {
  return (
    <ol className="flex items-center justify-between mb-6">
      {titles.map((title, i) => {
        const n = i + 1
        const isCurrent = n === step
        const isDone = n < step
        return (
          <li key={n} className="flex-1 flex items-center">
            <div className="flex flex-col items-center">
              <span
                aria-current={isCurrent ? 'step' : undefined}
                className={[
                  'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-colors',
                  isCurrent
                    ? 'bg-field text-white border-field'
                    : isDone
                      ? 'bg-field/70 text-white border-field/70'
                      : 'bg-gray-100 text-gray-400 border-gray-200 dark:bg-hc-bg dark:text-hc-fg dark:border-hc-border',
                ].join(' ')}
              >
                {isDone ? '✓' : n}
              </span>
              <span className="text-[10px] text-gray-500 mt-1 text-center leading-tight dark:text-hc-fg">
                {title}
              </span>
            </div>
            {i < titles.length - 1 && (
              <div className={`flex-1 h-px mx-1 ${isDone ? 'bg-field/50' : 'bg-gray-200'}`} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-xs text-red-500 mt-1">{msg}</p>
}

// Headless map-event listener; relays a click's latlng up via onPick.
function ClickHandler({ onPick }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

// Click-to-place single marker; lifts the chosen lat/lon up via onPick.
function MapPicker({ position, onPick }) {
  return (
    <MapContainer
      center={position || AR_CENTER}
      zoom={position ? 11 : 7}
      style={{ height: '320px', width: '100%' }}
      className="rounded-xl"
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onPick={onPick} />
      {position && <Marker position={position} />}
    </MapContainer>
  )
}

function GateResultCard({ gate, es }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 dark:bg-hc-surface dark:border-hc-border">
      <div className="flex items-center justify-between mb-3">
        <p className="font-semibold text-charcoal dark:text-hc-fg">
          {es ? 'Compuerta' : 'Gate'} {gate.gate} · {gate.title}
        </p>
        <span className={`text-xs font-bold px-2 py-1 rounded-full ${STATUS_BADGE[gate.status]}`}>
          {statusLabel(gate.status, es)}
        </span>
      </div>
      <ul className="space-y-2">
        {gate.checks.map((c) => (
          <li key={c.id} className="text-sm">
            <div className="flex items-start justify-between gap-2">
              <span className="text-charcoal dark:text-hc-fg">{c.label}</span>
              <span className={`flex-shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[c.status]}`}>
                {statusLabel(c.status, es)}
              </span>
            </div>
            <p className="text-xs text-gray-500 dark:text-hc-fg mt-0.5">
              <span className="font-medium">{tierLabel(c.tier, es)}</span> · {c.reason}
              {c.observed != null && ` (${c.observed})`}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function SprayCheckWizard() {
  const { lang } = useLang()
  const es = lang === 'es'
  const { runCheck, loading, error } = useSprayCheck()

  const [step, setStep] = useState(1)
  const [errs, setErrs] = useState({})
  const [result, setResult] = useState(null)
  const [form, setForm] = useState({
    product: '',
    license_attested: false,
    training_attested: false,
    lat: null,
    lon: null,
    no_inversion_observed: false,
  })

  const stepTitles = es ? STEP_TITLES_ES : STEP_TITLES_EN

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
  }

  // Run the check with the current form + an optional attestation override.
  async function check(next) {
    const merged = { ...form, ...next }
    try {
      const res = await runCheck({
        lat: merged.lat,
        lon: merged.lon,
        product: merged.product,
        attestation: { no_inversion_observed: merged.no_inversion_observed },
      })
      setResult(res)
      return res
    } catch {
      // surfaced via hook error state
      return null
    }
  }

  async function handlePick(lat, lon) {
    setForm((f) => ({ ...f, lat, lon }))
    setErrs((e) => ({ ...e, pin: undefined }))
    await check({ lat, lon })
  }

  async function handleInversionToggle(checked) {
    set('no_inversion_observed', checked)
    await check({ no_inversion_observed: checked })
  }

  function handleNext() {
    const stepErrs = getSprayStepErrors(form, step)
    if (Object.keys(stepErrs).length > 0) {
      setErrs(stepErrs)
      return
    }
    setErrs({})
    setStep((s) => s + 1)
  }

  // Derive a compact live-conditions summary from Gate C's observed values.
  const gateC = result?.gates?.find((g) => g.gate === 'C')
  const observedOf = (id) => gateC?.checks?.find((c) => c.id === id)?.observed

  const failingReasons = (result?.gates || [])
    .flatMap((g) => g.checks)
    .filter((c) => c.status !== 'pass')
    .map((c) => c.reason)

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm dark:bg-hc-surface dark:border-hc-border">
      <h1 className="text-lg font-bold text-charcoal dark:text-hc-fg mb-1">
        {es ? 'Verificación Antes de Aplicar Dicamba' : 'Before-You-Spray Dicamba Check'}
      </h1>
      <p className="text-sm text-gray-500 dark:text-hc-fg mb-6">
        {es
          ? 'Revise los requisitos verificables antes de aplicar. Esta herramienta informa, no autoriza la aplicación.'
          : 'Walk the verifiable requirements before you spray. This tool informs — it does not authorize an application.'}
      </p>

      <StepIndicator step={step} titles={stepTitles} />

      {error && <Alert variant="error" className="mb-4">{error}</Alert>}

      {/* Step 1 — Eligibility (Gate A inputs) */}
      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-1">
              {es ? 'Producto a aplicar *' : 'Product you plan to apply *'}
            </label>
            <select
              value={form.product}
              onChange={(e) => set('product', e.target.value)}
              className={`${INPUT_CLS} ${errs.product ? INPUT_ERR_CLS : ''}`}
            >
              <option value="">{es ? 'Seleccionar producto...' : 'Select product...'}</option>
              {APPROVED_PRODUCTS.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <FieldError msg={errs.product} />
          </div>

          <div>
            <p className="block text-sm font-medium text-charcoal dark:text-hc-fg mb-2">
              {es ? 'Atestación del aplicador' : 'Applicator attestation'}
            </p>
            <label className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer mb-2">
              <input
                type="checkbox"
                checked={form.license_attested}
                onChange={(e) => set('license_attested', e.target.checked)}
                className="rounded accent-field mt-0.5"
              />
              {es
                ? 'Tengo una licencia de aplicador de pesticidas vigente.'
                : 'I hold a current Arkansas pesticide applicator license.'}
            </label>
            <label className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer">
              <input
                type="checkbox"
                checked={form.training_attested}
                onChange={(e) => set('training_attested', e.target.checked)}
                className="rounded accent-field mt-0.5"
              />
              {es
                ? 'Completé la capacitación anual de dicamba requerida.'
                : 'I have completed the required annual dicamba-specific training.'}
            </label>
            <FieldError msg={errs.license} />
          </div>
        </div>
      )}

      {/* Step 2 — Live conditions (Gate C) */}
      {step === 2 && (
        <div className="space-y-4">
          <p className="text-sm font-medium text-charcoal dark:text-hc-fg">
            {es ? 'Toque su campo en el mapa para colocar un pin.' : 'Tap your field on the map to drop a pin.'}
          </p>
          <MapPicker
            position={form.lat != null ? [form.lat, form.lon] : null}
            onPick={handlePick}
          />
          <FieldError msg={errs.pin} />

          {loading && (
            <p className="text-sm text-gray-500 dark:text-hc-fg">
              {es ? 'Obteniendo condiciones...' : 'Fetching live conditions...'}
            </p>
          )}

          {result && (
            <div className="bg-gray-50 rounded-xl p-4 text-sm dark:bg-hc-bg" data-testid="conditions-summary">
              <p className="font-semibold text-charcoal dark:text-hc-fg mb-2">
                {es ? 'Condiciones actuales' : 'Live conditions'}
                {!result.weather_available && (
                  <span className="ml-2 text-xs font-normal text-amber-700 dark:text-hc-fg">
                    {es ? '(clima no disponible)' : '(weather unavailable)'}
                  </span>
                )}
              </p>
              <p className="text-gray-600 dark:text-hc-fg">
                {es ? 'Viento' : 'Wind'}: {observedOf('wind_in_range') ?? '—'} · {es ? 'Temp' : 'Temp'}: {observedOf('temp_in_range') ?? '—'} · {es ? 'Lluvia 48h' : '48h rain'}: {observedOf('rain_free_48h') ?? '—'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Step 3 — Attest + result */}
      {step === 3 && (
        <div className="space-y-4">
          {result ? (
            <>
              <div
                className={[
                  'rounded-xl p-4',
                  result.overall_status === 'pass'
                    ? 'bg-emerald-50 dark:bg-hc-bg'
                    : 'bg-amber-50 dark:bg-hc-bg',
                ].join(' ')}
                data-testid="outcome-banner"
              >
                <p className="font-bold text-charcoal dark:text-hc-fg">
                  {result.overall_status === 'pass'
                    ? (es ? 'Cumple los requisitos que confirmó' : 'Meets the requirements you confirmed')
                    : (es ? 'No está claro — esto es por qué' : "Not clear — here's why")}
                </p>
                {result.overall_status !== 'pass' && failingReasons.length > 0 && (
                  <ul className="list-disc list-inside text-sm text-charcoal dark:text-hc-fg mt-2 space-y-1">
                    {failingReasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
                <p className="text-xs text-gray-500 dark:text-hc-fg mt-2">
                  {es
                    ? 'Esto no es una autorización para aplicar. Verifique siempre la etiqueta del producto y las normas estatales vigentes.'
                    : 'This is not an authorization to spray. Always verify the product label and current state rules.'}
                </p>
              </div>

              <label className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                <input
                  type="checkbox"
                  checked={form.no_inversion_observed}
                  onChange={(e) => handleInversionToggle(e.target.checked)}
                  className="rounded accent-field mt-0.5"
                  data-testid="inversion-toggle"
                />
                {es
                  ? 'Confirmo que no observo una inversión térmica en el campo en este momento.'
                  : 'I confirm I do not observe a temperature inversion in the field right now.'}
              </label>

              <div className="space-y-3">
                {result.gates.map((g) => (
                  <GateResultCard key={g.gate} gate={g} es={es} />
                ))}
              </div>

              <p className="text-[11px] text-gray-400 dark:text-hc-fg">
                {es ? 'Versión de reglas' : 'Rule version'}: {result.rule_version}
              </p>
            </>
          ) : (
            <Alert variant="info">
              {es
                ? 'Vuelva al paso 2 y coloque un pin para ejecutar la verificación.'
                : 'Go back to step 2 and drop a pin to run the check.'}
            </Alert>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3 mt-8">
        {step > 1 && (
          <button
            type="button"
            onClick={() => { setErrs({}); setStep((s) => s - 1) }}
            className={BTN_GHOST_CLS}
          >
            {es ? 'Atrás' : 'Back'}
          </button>
        )}
        {step < TOTAL_STEPS && (
          <button type="button" onClick={handleNext} className={BTN_PRIMARY_CLS}>
            {es ? 'Siguiente' : 'Next'}
          </button>
        )}
      </div>
    </div>
  )
}
