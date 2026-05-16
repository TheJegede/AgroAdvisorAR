import { useState, useEffect } from 'react'
import { useLang } from '../../contexts/LangContext'
import { useProfile } from '../../hooks/useProfile'
import Input from '../ui/Input'
import Select from '../ui/Select'
import Button from '../ui/Button'
import Alert from '../ui/Alert'
import CropCheckboxGroup from './CropCheckboxGroup'
import { COUNTY_OPTIONS } from '../../constants/counties'
import Spinner from '../ui/Spinner'

export default function ProfileForm() {
  const { t, setLang } = useLang()
  const { profile, loading, error: loadError, updateProfile } = useProfile()

  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (profile) {
      setForm({
        full_name: profile.full_name || '',
        county_fips: profile.county_fips || '',
        primary_crops: profile.primary_crops || [],
        language: profile.language || 'en',
      })
    }
  }, [profile])

  if (loading) return <div className="flex justify-center py-8"><Spinner /></div>
  if (loadError) return <Alert variant="error">{loadError}</Alert>
  if (!form) return null

  function set(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target ? e.target.value : e }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSuccess(false)
    try {
      await updateProfile(form)
      setLang(form.language)
      setSuccess(true)
    } catch (err) {
      setError(err.response?.data?.detail || t.errorGeneric)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {success && <Alert variant="success" dismissible>{t.profileSaved}</Alert>}
      {error && <Alert variant="error" dismissible>{error}</Alert>}

      <Input id="full_name" label={t.fullName} value={form.full_name}
        onChange={set('full_name')} required />

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

      <Button type="submit" loading={saving} className="w-full mt-2">
        {saving ? t.saving : t.save}
      </Button>
    </form>
  )
}
