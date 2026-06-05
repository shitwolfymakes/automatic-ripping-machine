<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { useRipPresetsStore } from '../stores/ripPresets'

const ripPresets = useRipPresetsStore()
const error = ref<string | null>(null)

onMounted(async () => {
  await ripPresets.fetchAll()
})

async function deletePreset(id: string, name: string): Promise<void> {
  if (!confirm(`Delete rip preset "${name}"?`)) return
  try {
    await ripPresets.remove(id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Delete failed'
  }
}
</script>

<template>
  <h2>Rip presets</h2>
  <div class="row" style="gap: 8px; align-items: center; margin-bottom: 12px">
    <RouterLink to="/rip-presets/new"><button>New preset</button></RouterLink>
    <span class="spacer" />
    <RouterLink to="/sessions" class="muted">Sessions</RouterLink>
    <RouterLink to="/transcode-presets" class="muted">Transcode presets</RouterLink>
  </div>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="ripPresets.error" class="error">{{ ripPresets.error }}</p>
    <table v-if="ripPresets.presets.length">
      <thead>
        <tr>
          <th>Name</th>
          <th>Media</th>
          <th>Track selection</th>
          <th>Identification</th>
          <th>Output</th>
          <th>Built-in</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in ripPresets.presets" :key="p.id">
          <td>{{ p.name }}</td>
          <td>{{ p.media_type }}</td>
          <td>{{ p.track_selection }}</td>
          <td>{{ p.identification_mode }}</td>
          <td>{{ p.output_mode }}</td>
          <td>{{ p.is_builtin ? 'yes' : 'no' }}</td>
          <td>
            <RouterLink :to="`/rip-presets/${p.id}/edit`"
              ><button class="secondary">Edit</button></RouterLink
            >
            <button v-if="!p.is_builtin" class="secondary" @click="deletePreset(p.id, p.name)">
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No rip presets.</p>
  </div>
</template>
