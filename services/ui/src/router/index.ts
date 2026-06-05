import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/change-password',
    component: () => import('../views/ChangePassword.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/jobs',
    component: () => import('../views/Jobs.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/jobs/manual',
    component: () => import('../views/JobManual.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/jobs/:id',
    component: () => import('../views/JobDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/drives',
    component: () => import('../views/Drives.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions',
    component: () => import('../views/Sessions.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions/new',
    component: () => import('../views/SessionForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sessions/:id/edit',
    component: () => import('../views/SessionForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/rip-presets',
    component: () => import('../views/RipPresets.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/rip-presets/new',
    component: () => import('../views/RipPresetForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/rip-presets/:id/edit',
    component: () => import('../views/RipPresetForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/transcode-presets',
    component: () => import('../views/TranscodePresets.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/transcode-presets/new',
    component: () => import('../views/TranscodePresetForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/transcode-presets/:id/edit',
    component: () => import('../views/TranscodePresetForm.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/config',
    component: () => import('../views/Config.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/diagnostics',
    component: () => import('../views/Diagnostics.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login' }
  }
  if (auth.isAuthenticated && auth.passwordMustChange && to.path !== '/change-password') {
    return { path: '/change-password' }
  }
  if (to.path === '/login' && auth.isAuthenticated && !auth.passwordMustChange) {
    return { path: '/dashboard' }
  }
  return true
})
