import { create } from 'zustand'
import type { DashboardData } from '../types/admin'

const tokenStorageKey = 'titok2youtube-admin-token'

type AppState = {
  token: string
  dashboard?: DashboardData
  setToken: (token: string) => void
  setDashboard: (dashboard: DashboardData) => void
}

export const useAppStore = create<AppState>((set) => ({
  token: localStorage.getItem(tokenStorageKey) || '',
  setToken: (token) => {
    const normalized = token.trim()
    if (normalized) {
      localStorage.setItem(tokenStorageKey, normalized)
    } else {
      localStorage.removeItem(tokenStorageKey)
    }
    set({ token: normalized })
  },
  setDashboard: (dashboard) => set({ dashboard }),
}))
