<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ApiError } from '../api/client'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  error.value = null
  submitting.value = true
  try {
    const resp = await auth.login({ username: username.value, password: password.value })
    if (resp.password_must_change) {
      await router.push('/change-password')
    } else {
      await router.push('/jobs')
    }
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 401
        ? 'Invalid username or password'
        : e instanceof Error
          ? e.message
          : 'Login failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="center-screen">
    <form class="card login-card" @submit.prevent="submit">
      <h2 style="margin-top: 0">Sign in to ARM</h2>
      <div class="field">
        <label for="username">Username</label>
        <input id="username" v-model="username" autocomplete="username" autofocus />
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" v-model="password" type="password" autocomplete="current-password" />
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <button :disabled="submitting || !username || !password" type="submit">
        {{ submitting ? 'Signing in…' : 'Sign in' }}
      </button>
      <p class="muted" style="margin-top: 16px; font-size: 12px">
        First-boot default is <code>admin</code> / <code>admin</code>. You'll be required to change
        it before anything else loads.
      </p>
    </form>
  </div>
</template>
