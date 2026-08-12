import { createRouter, createWebHashHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/chat',
    name: 'chatIndex',
    component: () => import('@/views/ChatWindow.vue')
  },
  {
    path: '/chat/:id',
    name: 'chat',
    component: () => import('@/views/ChatWindow.vue')
  },
  {
    path: '/life',
    name: 'life',
    component: () => import('@/views/LifeWindow.vue')
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})
export default router