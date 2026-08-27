<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { API_UNAUTHORIZED_EVENT } from './services/api/client'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

function handleUnauthorized() {
  if (route.name === 'login') return
  authStore.logout()
  void router.replace({ name: 'login', query: { redirect: route.fullPath } })
}

onMounted(() => window.addEventListener(API_UNAUTHORIZED_EVENT, handleUnauthorized))
onUnmounted(() => window.removeEventListener(API_UNAUTHORIZED_EVENT, handleUnauthorized))
</script>

<template>
  <RouterView />
</template>
