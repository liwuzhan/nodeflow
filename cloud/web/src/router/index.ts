import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'map',
    component: () => import('@/views/FarmMapView.vue'),
  },
  {
    path: '/machines',
    name: 'machines',
    component: () => import('@/views/MachineDashboard.vue'),
  },
  {
    path: '/jobs',
    name: 'jobs',
    component: () => import('@/views/JobListView.vue'),
  },
  {
    path: '/jobs/create',
    name: 'jobCreate',
    component: () => import('@/views/JobCreateView.vue'),
  },
  {
    path: '/jobs/:id',
    name: 'jobDetail',
    component: () => import('@/views/JobDetailView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
