import { CROPS } from '../../constants/crops'
import { useLang } from '../../contexts/LangContext'

export default function CropCheckboxGroup({ value = [], onChange }) {
  const { lang } = useLang()

  function toggle(cropValue) {
    const next = value.includes(cropValue)
      ? value.filter((v) => v !== cropValue)
      : [...value, cropValue]
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-2">
      {CROPS.map((crop) => (
        <label
          key={crop.value}
          className="flex items-center gap-3 min-h-touch cursor-pointer"
        >
          <input
            type="checkbox"
            checked={value.includes(crop.value)}
            onChange={() => toggle(crop.value)}
            className="w-5 h-5 accent-field"
          />
          <span className="text-base text-charcoal">{crop[lang]}</span>
        </label>
      ))}
    </div>
  )
}
