import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Header from './Header'
import Sidebar from './Sidebar'
import SyncStatusBar from '../ui/SyncStatusBar'
import { useSyncStatus } from '../../hooks/useSyncStatus'

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { online } = useSyncStatus()

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-parchment dark:bg-hc-bg">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header onMenuClick={() => setSidebarOpen(true)} />
        <SyncStatusBar online={online} />
        <main className="flex-1 flex flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
