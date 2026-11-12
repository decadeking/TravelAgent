import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { getToken } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    redirect: '/feed',
  },
  {
    path: '/feed',
    name: 'feed',
    component: () => import('@/views/FeedView.vue'),
    meta: { title: '世界那么大', requiresAuth: true },
  },
  {
    path: '/feed/:id',
    name: 'post-detail',
    component: () => import('@/views/PostDetailView.vue'),
    meta: { title: '动态详情', requiresAuth: true },
  },
  {
    path: '/u/:id',
    name: 'user-profile',
    component: () => import('@/views/UserProfileView.vue'),
    meta: { title: '用户主页', requiresAuth: true },
  },
  {
    path: '/plan',
    name: 'plan',
    component: () => import('@/views/PlanView.vue'),
    meta: { title: '新建规划', requiresAuth: true },
  },
  {
    path: '/trips',
    name: 'trips',
    component: () => import('@/views/TripsView.vue'),
    meta: { title: '个人行程', requiresAuth: true },
  },
  {
    path: '/moments',
    name: 'moments',
    component: () => import('@/views/MomentsView.vue'),
    meta: { title: '动态', requiresAuth: true },
  },
  {
    path: '/messages',
    name: 'messages',
    component: () => import('@/views/MessagesView.vue'),
    meta: { title: '消息', requiresAuth: true },
  },
  {
    path: '/trips/:id',
    name: 'trip-detail',
    component: () => import('@/views/TripDetailView.vue'),
    meta: { title: '行程详情', requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { title: '管理后台', requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: '个人中心', requiresAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/feed',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const token = getToken()
  if (to.meta.requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && token) {
    return { name: 'feed' }
  }
  if (to.meta.requiresAdmin) {
    const auth = useAuthStore()
    if (!auth.user && token) {
      try {
        await auth.fetchMe()
      } catch {
        /* 令牌失效时由拦截器统一处理 */
      }
    }
    if (auth.user?.role !== 'admin') {
      return { name: 'feed' }
    }
  }
  return true
})

router.afterEach((to) => {
  const title = (to.meta.title as string) || ''
  document.title = title ? `${title} · 旅行吧 TravelAgent` : '旅行吧 TravelAgent'
})

export default router
