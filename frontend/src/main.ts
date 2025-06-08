import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

// Criar instância do Pinia para gerenciamento de estado
const pinia = createPinia()

// Configurar rotas básicas (será expandido posteriormente)
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('./views/HomeView.vue')
  }
]

// Criar instância do router
const router = createRouter({
  history: createWebHistory(),
  routes
})

// Criar e configurar aplicação Vue
const app = createApp(App)

app.use(pinia)
app.use(router)

app.mount('#app')
