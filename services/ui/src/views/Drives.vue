<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { DriveUpdateRequest, DriveView, SessionView } from '../api/types'

const drives = ref<DriveView[]>([])
const sessions = ref<SessionView[]>([])
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    const [d, s] = await Promise.all([
      api.get<DriveView[]>('/api/drives'),
      api.get<SessionView[]>('/api/sessions'),
    ])
    drives.value = d
    sessions.value = s
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to load'
  }
})

async function onDefaultSessionChange(drive: DriveView, event: Event) {
  const target = event.target as HTMLSelectElement
  const newId = target.value === '' ? null : target.value
  const body: DriveUpdateRequest = { default_session_id: newId }
  try {
    const updated = await api.patch<DriveView>(`/api/drives/${drive.id}`, body)
    const idx = drives.value.findIndex((d) => d.id === updated.id)
    if (idx >= 0) drives.value[idx] = updated
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Failed to update drive'
    target.value = drive.default_session_id ?? ''
  }
}
</script>

<template>
  <h2>Drives</h2>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <table v-if="drives.length">
      <thead>
        <tr>
          <th>Hostname</th>
          <th>Device</th>
          <th>Display name</th>
          <th>Default session</th>
          <th>Status</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in drives" :key="d.id">
          <td>{{ d.hostname }}</td>
          <td>
            <code>{{ d.device_path }}</code>
          </td>
          <td>{{ d.display_name ?? '—' }}</td>
          <td>
            <select
              :value="d.default_session_id ?? ''"
              :data-testid="`default-session-${d.id}`"
              @change="onDefaultSessionChange(d, $event)"
            >
              <option value="">— none —</option>
              <option v-for="s in sessions" :key="s.id" :value="s.id">
                {{ s.name }}
              </option>
            </select>
          </td>
          <td>
            <span class="badge">{{ d.status }}</span>
          </td>
          <td>{{ d.last_seen_at ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No drives registered yet.</p>
  </div>
</template>
