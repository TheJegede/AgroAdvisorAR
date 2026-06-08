import SprayCheckWizard from '../components/dicamba/SprayCheckWizard'

export default function SprayCheckPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-parchment dark:bg-hc-bg">
      <div className="max-w-2xl mx-auto py-8 px-4">
        <SprayCheckWizard />
      </div>
    </div>
  )
}
