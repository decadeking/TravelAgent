import { defineStore } from 'pinia'

const SIDEBAR_KEY = 'ta_sidebar_collapsed'
const MODEL_KEY = 'ta_preferred_model'

export const useUiStore = defineStore('ui', {
  state: () => ({
    sidebarCollapsed: localStorage.getItem(SIDEBAR_KEY) === '1',
    preferredModel: localStorage.getItem(MODEL_KEY) ?? '',
  }),
  actions: {
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem(SIDEBAR_KEY, this.sidebarCollapsed ? '1' : '0')
    },
    setPreferredModel(id: string) {
      this.preferredModel = id
      localStorage.setItem(MODEL_KEY, id)
    },
  },
})
