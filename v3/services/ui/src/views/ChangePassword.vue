<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ApiError } from '../api/client'
import PasswordInput from '../components/PasswordInput.vue'

const auth = useAuthStore()
const router = useRouter()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  error.value = null
  if (newPassword.value !== confirmPassword.value) {
    error.value = 'New passwords do not match'
    return
  }
  if (newPassword.value.length < 8) {
    error.value = 'New password must be at least 8 characters'
    return
  }
  submitting.value = true
  try {
    await auth.changePassword({
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    await router.push('/jobs')
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Password change failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="center-screen">
    <form class="card login-card" @submit.prevent="submit">
      <h2 style="margin-top: 0">Change your password</h2>
      <p class="muted" style="margin-top: 0">
        First-boot password must be replaced before you can use ARM.
      </p>
      <div class="field">
        <label for="current">Current password</label>
        <PasswordInput id="current" v-model="currentPassword" autocomplete="current-password" />
      </div>
      <div class="field">
        <label for="new">New password</label>
        <PasswordInput id="new" v-model="newPassword" autocomplete="new-password" />
      </div>
      <div class="field">
        <label for="confirm">Confirm new password</label>
        <PasswordInput id="confirm" v-model="confirmPassword" autocomplete="new-password" />
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <button :disabled="submitting" type="submit">
        {{ submitting ? 'Saving…' : 'Save' }}
      </button>
    </form>
  </div>
</template>
