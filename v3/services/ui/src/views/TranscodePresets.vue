<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ApiError } from "../api/client";
import { useTranscodePresetsStore } from "../stores/transcodePresets";

const tcPresets = useTranscodePresetsStore();
const error = ref<string | null>(null);

onMounted(async () => {
  await tcPresets.fetchAll();
});

async function deletePreset(id: string, name: string): Promise<void> {
  if (!confirm(`Delete transcode preset "${name}"?`)) return;
  try {
    await tcPresets.remove(id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Delete failed";
  }
}
</script>

<template>
  <h2>Transcode presets</h2>
  <div class="row" style="gap: 8px; align-items: center; margin-bottom: 12px">
    <RouterLink to="/transcode-presets/new"><button>New preset</button></RouterLink>
    <span class="spacer" />
    <RouterLink to="/sessions" class="muted">Sessions</RouterLink>
    <RouterLink to="/rip-presets" class="muted">Rip presets</RouterLink>
  </div>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="tcPresets.error" class="error">{{ tcPresets.error }}</p>
    <table v-if="tcPresets.presets.length">
      <thead>
        <tr>
          <th>Name</th>
          <th>Media</th>
          <th>Tool</th>
          <th>Container</th>
          <th>HW</th>
          <th>Built-in</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in tcPresets.presets" :key="p.id">
          <td>{{ p.name }}</td>
          <td>{{ p.media_type }}</td>
          <td>{{ p.tool }}</td>
          <td>{{ p.container }}</td>
          <td>{{ p.hw_preference ?? "—" }}</td>
          <td>{{ p.is_builtin ? "yes" : "no" }}</td>
          <td>
            <RouterLink :to="`/transcode-presets/${p.id}/edit`"><button class="secondary">Edit</button></RouterLink>
            <button v-if="!p.is_builtin" class="secondary" @click="deletePreset(p.id, p.name)">Delete</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No transcode presets.</p>
  </div>
</template>
