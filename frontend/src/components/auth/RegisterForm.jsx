import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'
import api from '../../lib/api'
import Input from '../ui/Input'
import Select from '../ui/Select'
import Button from '../ui/Button'
import Alert from '../ui/Alert'
import CropCheckboxGroup from '../profile/CropCheckboxGroup'
import { COUNTY_OPTIONS } from '../../constants/counties'

export default function RegisterForm() {
  const { login } = useAuth()
  const { t, setLang } = useLang()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    full_name: '',
    email: '',
    password: '',
    county_fips: '',
    primary_crops: [],
    language: 'en',
  })
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)

  function set(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target ? e.target.value : e }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setInfo('')

    if (!form.county_fips) { setError('Please select your county.'); return }
    if (form.password.length < 8) { setError('Password must be at least 8 characters.'); return }

    setLoading(true)
    try {
      const { data } = await api.post('/auth/register', form)
      setLang(form.language)
      login(data.access_token, data.refresh_token)
      navigate('/')
    } catch (err) {
      const detail = err.response?.data?.detail || ''
      if (detail.includes('Email confirmation')) {
        setInfo(t.emailConfirmRequired)
        setTimeout(() => navigate('/login'), 3000)
      } else {
        setError(detail || t.errorGeneric)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && <Alert variant="error" dismissible>{error}</Alert>}
      {info && <Alert variant="success">{info}</Alert>}

      <Input id="full_name" label={t.fullName} value={form.full_name}
        onChange={set('full_name')} required autoComplete="name" />

      <Input id="email" label={t.email} type="email" value={form.email}
        onChange={set('email')} required autoComplete="email" />

      <Input id="password" label={t.password} type="password" value={form.password}
        onChange={set('password')} required autoComplete="new-password" />

      <Select id="county_fips" label={t.county} options={COUNTY_OPTIONS}
        value={form.county_fips} onChange={set('county_fips')} />

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-charcoal">{t.primaryCrops}</p>
        <CropCheckboxGroup
          value={form.primary_crops}
          onChange={(crops) => setForm((f) => ({ ...f, primary_crops: crops }))}
        />
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-charcoal">{t.languagePref}</p>
        <div className="flex gap-4">
          {['en', 'es'].map((l) => (
            <label key={l} className="flex items-center gap-2 cursor-pointer min-h-touch">
              <input type="radio" name="language" value={l}
                checked={form.language === l}
                onChange={() => setForm((f) => ({ ...f, language: l }))}
                className="accent-field w-5 h-5" />
              <span className="text-base">{l === 'en' ? 'English' : 'Espanol'}</span>
            </label>
          ))}
        </div>
      </div>

      <Button type="submit" loading={loading} className="w-full mt-2">
        {t.register}
      </Button>
      <p className="text-center text-sm text-gray-600">
        {t.alreadyHaveAccount}{' '}
        <Link to="/login" className="text-field font-medium hover:underline">
          {t.login}
        </Link>
      </p>
    </form>
  )
}
