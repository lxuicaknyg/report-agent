import { createApp } from 'vue'
import App from './App.vue'
import router from './app/router'
import { createPinia } from 'pinia'
import './styles.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
