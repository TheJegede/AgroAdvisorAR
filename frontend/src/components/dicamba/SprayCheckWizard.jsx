import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, Marker, Circle, CircleMarker, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { useLang } from '../../contexts/LangContext'
import { useSprayCheck, getSprayStepErrors } from '../../hooks/useSprayCheck'
import { downloadSprayPdf } from '../../hooks/useSprayRecords'
import Alert from '../ui/Alert'
import { SPRAY_DISCLAIMER_EN, SPRAY_DISCLAIMER_ES } from '../../lib/disclaimers'
import SprayFeedbackWidget from './SprayFeedbackWidget'

// Bundlers strip Leaflet's default marker URLs; re-point them at the imported assets.
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
})

const TOTAL_STEPS = 4
// Arkansas centroid — the field is almost always in-state.
const AR_CENTER = [34.8, -92.2]

// Approved over-the-top products. Hardcoded from dicamba_rules.json (2026-AR-OTT);
// a rules-fetch endpoint can replace this later without touching the UI.
const APPROVED_PRODUCTS = [
  { id: 'engenia', name: 'Engenia' },
  { id: 'xtendimax', name: 'XtendiMax with VaporGrip' },
  { id: 'tavium', name: 'Tavium Plus VaporGrip' },
]

// Buffer rings (Gate B). Hardcoded from dicamba_rules.json buffers_ft (2026-AR-OTT),
// converted ft → m (× 0.3048) for Leaflet Circle radii. Mirrors APPROVED_PRODUCTS.
const BUFFERS_M = {
  research_station: Math.round(5280 * 0.3048), // 1609 m
  organic_specialty: Math.round(2640 * 0.3048), // 805 m
  non_tolerant_crop: Math.round(1320 * 0.3048), // 402 m
}

const INPUT_CLS =
  'w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-base text-charcoal outline-none transition placeholder:text-gray-400 focus:border-field focus:ring-2 focus:ring-field/20 dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'
const INPUT_ERR_CLS = 'border-red-400/60 focus:border-red-400/80 focus:ring-red-300/25'
const BTN_PRIMARY_CLS =
  'flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-field px-5 py-3 font-bold text-white shadow transition hover:bg-field/90 focus:outline-none focus:ring-2 focus:ring-field/50 disabled:opacity-60 min-h-touch dark:border-2 dark:border-hc-border dark:bg-hc-accent dark:text-hc-accent-fg'
const BTN_GHOST_CLS =
  'flex-1 rounded-xl border border-gray-200 bg-white px-4 py-3 font-semibold text-gray-600 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 min-h-touch dark:border-2 dark:border-hc-border dark:bg-hc-bg dark:text-hc-fg'

// Official sensitive-site registries. We deep-link + ask the applicator to confirm
// (Gate B human_attested) because the registries are voluntary/incomplete and have
// no open API yet — honesty about the blind spot is the safety asset (PRD §10).
const FIELDWATCH_URL = 'https://fieldcheck.fieldwatch.com/'
const EPA_BULLETINS_URL = 'https://www.epa.gov/endangered-species/bulletins-live-two-view-bulletins'

const STEP_TITLES_EN = ['Eligibility', 'Field & Buffers', 'Live Conditions', 'Confirm & Result']
const STEP_TITLES_ES = ['Elegibilidad', 'Campo y Zonas', 'Condiciones Actuales', 'Confirmar y Resultado']

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

function DisclaimerBanner({ es }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl bg-amber-50/60 border border-amber-200/60 p-3 text-xs text-amber-900/90 dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg mb-4" data-testid="disclaimer-banner">
      <span className="text-sm select-none" role="img" aria-label="warning">⚠️</span>
      <p className="flex-1 leading-normal font-medium">
        {es ? SPRAY_DISCLAIMER_ES : SPRAY_DISCLAIMER_EN}
      </p>
    </div>
  )
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

// Click-to-place field marker + Gate B buffer rings + research-station markers.
function MapPicker({ position, onPick, stations }) {
  return (
    <MapContainer
      center={position || AR_CENTER}
      zoom={position ? 12 : 7}
      style={{ height: '320px', width: '100%' }}
      className="rounded-xl"
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onPick={onPick} />
      {position && (
        <>
          {/* Buffer rings, largest first so smaller rings stay visible on top. */}
          <Circle center={position} radius={BUFFERS_M.research_station}
            pathOptions={{ color: '#b91c1c', weight: 1, fillOpacity: 0.04 }} />
          <Circle center={position} radius={BUFFERS_M.organic_specialty}
            pathOptions={{ color: '#b45309', weight: 1, fillOpacity: 0.05 }} />
          <Circle center={position} radius={BUFFERS_M.non_tolerant_crop}
            pathOptions={{ color: '#15803d', weight: 1, fillOpacity: 0.06 }} />
          <Marker position={position} />
        </>
      )}
      {/* Research stations as CircleMarkers — distinct from the field pin, no icon asset. */}
      {(stations || []).map((s) => (
        <CircleMarker key={s.id} center={[s.lat, s.lon]} radius={5}
          pathOptions={{ color: '#1d4ed8', fillColor: '#1d4ed8', fillOpacity: 0.9 }} />
      ))}
    </MapContainer>
  )
}

function GateResultCard({ gate, es }) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 dark:bg-hc-surface dark:border-hc-border">
      <div className="flex items-center justify-between mb-3">
        <p className="font-semibold text-charcoal dark:text-hc-fg">
          {es ? 'Compuerta' : 'Gate'} {gate.gate} · {es ? (gate.title_es || gate.title) : gate.title}
        </p>
        <span className={`text-xs font-bold px-2 py-1 rounded-full ${STATUS_BADGE[gate.status]}`}>
          {statusLabel(gate.status, es)}
        </span>
      </div>
      <ul className="space-y-2">
        {gate.checks.map((c) => (
          <li key={c.id} className="text-sm">
            <div className="flex items-start justify-between gap-2">
              <span className="text-charcoal dark:text-hc-fg">{es ? (c.label_es || c.label) : c.label}</span>
              <span className={`flex-shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_BADGE[c.status]}`}>
                {statusLabel(c.status, es)}
              </span>
            </div>
            <p className="text-xs text-gray-500 dark:text-hc-fg mt-0.5">
              <span className="font-medium">{tierLabel(c.tier, es)}</span> · {es ? (c.reason_es || c.reason) : c.reason}
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
  const { runCheck, fetchStations, saveRecord, loading, error } = useSprayCheck()

  const [step, setStep] = useState(1)
  const [errs, setErrs] = useState({})
  const [result, setResult] = useState(null)
  const [stations, setStations] = useState([])
  const [savedRecord, setSavedRecord] = useState(null)
  const [pdfError, setPdfError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    product: '',
    license_attested: false,
    training_attested: false,
    lat: null,
    lon: null,
    no_inversion_observed: false,
    sensitive_crops_checked: false,
    organic_specialty_checked: false,
    boom_height_ok: false,
    droplet_setup_ok: false,
    tank_clean_ok: false,
    additives_ok: false,
    ground_application_only: false,
  })

  // Load the static station seed list once for the Gate B map markers.
  useEffect(() => {
    fetchStations().then(setStations).catch(() => setStations([]))
  }, [fetchStations])

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
        attestation: {
          license_attested: merged.license_attested,
          training_attested: merged.training_attested,
          no_inversion_observed: merged.no_inversion_observed,
          sensitive_crops_checked: merged.sensitive_crops_checked,
          organic_specialty_checked: merged.organic_specialty_checked,
          boom_height_ok: merged.boom_height_ok,
          droplet_setup_ok: merged.droplet_setup_ok,
          tank_clean_ok: merged.tank_clean_ok,
          additives_ok: merged.additives_ok,
          ground_application_only: merged.ground_application_only,
        },
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

  // Gate B neighbor confirmations — toggling re-runs /check (like the inversion toggle).
  async function handleGateBToggle(field, checked) {
    set(field, checked)
    await check({ [field]: checked })
  }

  // Gate D equipment confirmations — toggling re-runs /check (like the inversion toggle).
  async function handleGateDToggle(field, checked) {
    set(field, checked)
    await check({ [field]: checked })
  }

  async function handleSaveRecord() {
    setSaving(true)
    try {
      const rec = await saveRecord({
        lat: form.lat,
        lon: form.lon,
        product: form.product,
        attestation: {
          license_attested: form.license_attested,
          training_attested: form.training_attested,
          no_inversion_observed: form.no_inversion_observed,
          sensitive_crops_checked: form.sensitive_crops_checked,
          organic_specialty_checked: form.organic_specialty_checked,
          boom_height_ok: form.boom_height_ok,
          droplet_setup_ok: form.droplet_setup_ok,
          tank_clean_ok: form.tank_clean_ok,
          additives_ok: form.additives_ok,
          ground_application_only: form.ground_application_only,
        },
      })
      setSavedRecord(rec)
    } catch {
      // surfaced via hook error state
    } finally {
      setSaving(false)
    }
  }

  async function handleDownloadPdf() {
    setPdfError(null)
    try {
      await downloadSprayPdf(savedRecord.id)
    } catch (err) {
      setPdfError(err.response?.data?.detail || (es ? 'No se pudo descargar el PDF' : 'Failed to download PDF'))
    }
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

  // Gate B nearest-station distance label.
  const gateB = result?.gates?.find((g) => g.gate === 'B')
  const stationDistance = gateB?.checks?.find((c) => c.id === 'station_buffer')?.observed

  const failingReasons = (result?.gates || [])
    .flatMap((g) => g.checks)
    .filter((c) => c.status !== 'pass')
    .map((c) => (es ? (c.reason_es || c.reason) : c.reason))

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

      <DisclaimerBanner es={es} />

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

      {/* Step 2 — Field & Buffers (Gate B) */}
      {step === 2 && (
        <div className="space-y-4">
          <p className="text-sm font-medium text-charcoal dark:text-hc-fg">
            {es ? 'Toque su campo en el mapa para dibujar las zonas de protección.' : 'Tap your field on the map to draw the buffer rings.'}
          </p>
          <MapPicker
            position={form.lat != null ? [form.lat, form.lon] : null}
            onPick={handlePick}
            stations={stations}
          />
          <FieldError msg={errs.pin} />

          {/* Buffer-ring legend. */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-hc-fg">
            <span><span className="inline-block w-3 h-3 rounded-full bg-red-700/70 mr-1 align-middle" />{es ? 'Estación de inv. (1 mi)' : 'Research station (1 mi)'}</span>
            <span><span className="inline-block w-3 h-3 rounded-full bg-amber-700/70 mr-1 align-middle" />{es ? 'Orgánico/especial (½ mi)' : 'Organic/specialty (½ mi)'}</span>
            <span><span className="inline-block w-3 h-3 rounded-full bg-green-700/70 mr-1 align-middle" />{es ? 'Cultivo no tolerante (¼ mi)' : 'Non-tolerant crop (¼ mi)'}</span>
            <span><span className="inline-block w-3 h-3 rounded-full bg-blue-700 mr-1 align-middle" />{es ? 'Estación de investigación' : 'Research station'}</span>
          </div>

          {/* Deep-link fallback for the voluntary registries (no open API yet). */}
          <div className="rounded-xl bg-blue-50 border border-blue-100 p-3 text-xs text-charcoal dark:bg-hc-bg dark:border-hc-border dark:text-hc-fg" data-testid="registry-links">
            <p className="font-semibold mb-1">
              {es ? 'Verifique los registros oficiales' : 'Check the official registries'}
            </p>
            <p className="text-gray-600 dark:text-hc-fg mb-1">
              {es
                ? 'Los datos de sitios sensibles están incompletos. Antes de aplicar, revise:'
                : 'Sensitive-site data is incomplete. Before you spray, check:'}
            </p>
            <ul className="space-y-1">
              <li>
                <a href={FIELDWATCH_URL} target="_blank" rel="noopener noreferrer"
                  className="font-semibold text-field-dark underline">FieldWatch / FieldCheck</a>
                {' — '}{es ? 'cultivos sensibles registrados cerca' : 'registered sensitive crops nearby'}
              </li>
              <li>
                <a href={EPA_BULLETINS_URL} target="_blank" rel="noopener noreferrer"
                  className="font-semibold text-field-dark underline">EPA Bulletins Live! Two</a>
                {' — '}{es ? 'restricciones por especies en peligro' : 'endangered-species restrictions for this field'}
              </li>
            </ul>
          </div>

          {loading && (
            <p className="text-sm text-gray-500 dark:text-hc-fg">
              {es ? 'Calculando distancias...' : 'Calculating distances...'}
            </p>
          )}

          {stationDistance && (
            <p className="text-sm text-gray-600 dark:text-hc-fg" data-testid="station-distance">
              {es ? 'Estación más cercana' : 'Nearest station'}: {stationDistance}
            </p>
          )}

          {result && (
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                <input
                  type="checkbox"
                  checked={form.sensitive_crops_checked}
                  onChange={(e) => handleGateBToggle('sensitive_crops_checked', e.target.checked)}
                  className="rounded accent-field mt-0.5"
                  data-testid="non-tolerant-toggle"
                />
                {es
                  ? 'Confirmo que revisé que no hay cultivos no tolerantes al dicamba dentro de ¼ de milla.'
                  : 'I confirm I checked for non-dicamba-tolerant crops within ¼ mile.'}
              </label>
              <label className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                <input
                  type="checkbox"
                  checked={form.organic_specialty_checked}
                  onChange={(e) => handleGateBToggle('organic_specialty_checked', e.target.checked)}
                  className="rounded accent-field mt-0.5"
                  data-testid="organic-toggle"
                />
                <span>
                  {es
                    ? 'Confirmo que revisé que no hay cultivos orgánicos o especiales dentro de ½ milla.'
                    : 'I confirm I checked for organic or specialty crops within ½ mile.'}
                  <span className="block text-xs text-gray-500 dark:text-hc-fg mt-0.5">
                    {es
                      ? 'Los registros voluntarios (FieldWatch) aún no están integrados — datos incompletos.'
                      : 'Voluntary registries (FieldWatch) are not yet integrated — data is incomplete.'}
                  </span>
                </span>
              </label>
            </div>
          )}
        </div>
      )}

      {/* Step 3 — Live conditions (Gate C) */}
      {step === 3 && (
        <div className="space-y-4">
          {result ? (
            <>
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

      {/* Step 4 — Confirm & result */}
      {step === 4 && (
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
              </div>

              <div className="space-y-3">
                {result.gates.map((g) => (
                  <GateResultCard key={g.gate} gate={g} es={es} />
                ))}
              </div>

              <div className="space-y-2" data-testid="gate-d-attestations">
                <p className="text-sm font-semibold text-charcoal dark:text-hc-fg">
                  {es ? 'Equipo y objetivo (Compuerta D)' : 'Equipment & target (Gate D)'}
                </p>
                {[
                  ['boom_height_ok', es ? 'Altura de botavara dentro del máximo de la etiqueta.' : 'Boom height within the label maximum.'],
                  ['droplet_setup_ok', es ? 'Boquillas producen gotas Ultra Gruesas o más.' : 'Nozzles produce Ultra Coarse or coarser droplets.'],
                  ['tank_clean_ok', es ? 'Tanque limpiado antes de cargar.' : 'Sprayer cleaned out before loading.'],
                  ['additives_ok', es ? 'VRA + DRA aprobados presentes; sin AMS.' : 'Approved VRA + DRA present; no AMS.'],
                  ['ground_application_only', es ? 'Aplicación terrestre solamente (sin aérea).' : 'Ground application only (no aerial).'],
                ].map(([field, label]) => (
                  <label key={field} className="flex items-start gap-2 text-sm text-charcoal dark:text-hc-fg cursor-pointer bg-gray-50 rounded-xl p-3 dark:bg-hc-bg">
                    <input
                      type="checkbox"
                      checked={form[field]}
                      onChange={(e) => handleGateDToggle(field, e.target.checked)}
                      className="rounded accent-field mt-0.5"
                      data-testid={`gate-d-${field}`}
                    />
                    {label}
                  </label>
                ))}
              </div>

              {savedRecord ? (
                <>
                  <button
                    type="button"
                    onClick={handleDownloadPdf}
                    className={BTN_PRIMARY_CLS}
                    data-testid="download-pdf-link"
                  >
                    {es ? 'Descargar PDF del registro' : 'Download record PDF'}
                  </button>
                  {pdfError && <Alert variant="error" className="mt-2">{pdfError}</Alert>}
                  <SprayFeedbackWidget recordId={savedRecord.id} />
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleSaveRecord}
                  disabled={saving}
                  className={BTN_PRIMARY_CLS}
                  data-testid="save-record-btn"
                >
                  {saving
                    ? (es ? 'Guardando...' : 'Saving...')
                    : (es ? 'Guardar registro' : 'Save record')}
                </button>
              )}

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
