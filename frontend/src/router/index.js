import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import VStarManagement from '../views/VStarManagement.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/vstars', name: 'VStarManagement', component: VStarManagement },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
