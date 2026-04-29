<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import AppShell from "./components/AppShell.vue";
import { computed } from "vue";

const route = useRoute();
const showShell = computed(() => route.meta.requiresAuth === true);
</script>

<template>
  <AppShell v-if="showShell">
    <RouterView />
  </AppShell>
  <RouterView v-else />
</template>
