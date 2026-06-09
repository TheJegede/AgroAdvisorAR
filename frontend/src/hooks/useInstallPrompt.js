import { useEffect, useReducer } from 'react'

export const INITIAL_INSTALL_STATE = { installable: false, deferred: null, dismissed: false }

export function installReducer(state, action) {
  switch (action.type) {
    case 'captured':
      return { ...state, installable: true, deferred: action.event }
    case 'installed':
      return { ...state, installable: false, deferred: null }
    case 'dismissed':
      return { ...state, dismissed: true }
    default:
      return state
  }
}

export function useInstallPrompt() {
  const [state, dispatch] = useReducer(installReducer, INITIAL_INSTALL_STATE)

  useEffect(() => {
    const onBeforeInstall = (e) => {
      e.preventDefault()
      dispatch({ type: 'captured', event: e })
    }
    const onInstalled = () => dispatch({ type: 'installed' })
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  async function promptInstall() {
    if (state.deferred) {
      state.deferred.prompt()
      dispatch({ type: 'installed' })
    }
  }

  return { ...state, promptInstall, dismiss: () => dispatch({ type: 'dismissed' }) }
}
