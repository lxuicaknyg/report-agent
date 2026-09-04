import { createApp } from 'vue'
import App from './App.vue'
import router from './app/router'
import { createPinia } from 'pinia'
import './styles.css'

const pinia = createPinia()
if (import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).__PINIA__ = pinia
}

const app = createApp(App)
app.use(pinia)
app.use(router)
app.mount('#app')
