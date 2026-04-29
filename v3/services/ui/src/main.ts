import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { router } from './router'
import { useAuthStore } from './stores/auth'
import './styles.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Hydrate auth from localStorage before any route guard fires.
useAuthStore().hydrate()

app.mount('#app')
