<script setup lang="ts">
import { RouterLink, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const router = useRouter();

async function logout() {
  await auth.logout();
  await router.push("/login");
}
</script>

<template>
  <nav class="topnav">
    <strong>ARM</strong>
    <RouterLink to="/jobs" active-class="active">Jobs</RouterLink>
    <RouterLink to="/drives" active-class="active">Drives</RouterLink>
    <RouterLink to="/sessions" active-class="active">Sessions</RouterLink>
    <RouterLink to="/config" active-class="active">Config</RouterLink>
    <RouterLink to="/diagnostics" active-class="active">Diagnostics</RouterLink>
    <span class="spacer" />
    <span class="muted" v-if="auth.username">{{ auth.username }}</span>
    <button class="secondary" @click="logout">Logout</button>
  </nav>
  <div class="container">
    <slot />
  </div>
</template>
