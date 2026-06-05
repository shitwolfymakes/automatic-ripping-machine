<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { useSessionsStore } from '../stores/sessions'

const sessions = useSessionsStore()
const router = useRouter()
const error = ref<string | null>(null)
const cloneTarget = ref<string | null>(null)
const cloneName = ref('')

onMounted(async () => {
  await sessions.fetchAll()
})

async function deleteSession(id: string, name: string): Promise<void> {
  if (!confirm(`Delete session "${name}"?`)) return
  try {
    await sessions.remove(id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Delete failed'
  }
}

function openClone(id: string, name: string): void {
  cloneTarget.value = id
  cloneName.value = `${name} (copy)`
}

async function submitClone(): Promise<void> {
  if (cloneTarget.value === null) return
  try {
    const created = await sessions.clone(cloneTarget.value, { name: cloneName.value })
    cloneTarget.value = null
    await router.push(`/sessions/${created.id}/edit`)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Clone failed'
  }
}
</script>

<template>
  <h2>Sessions</h2>
  <div class="row" style="gap: 8px; align-items: center; margin-bottom: 12px">
    <RouterLink to="/sessions/new"><button>New session</button></RouterLink>
    <span class="spacer" />
    <RouterLink to="/rip-presets" class="muted">Rip presets</RouterLink>
    <RouterLink to="/transcode-presets" class="muted">Transcode presets</RouterLink>
  </div>
  <div class="card">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="sessions.error" class="error">{{ sessions.error }}</p>
    <table v-if="sessions.sessions.length">
      <thead>
        <tr>
          <th>Name</th>
          <th>Media</th>
          <th>Built-in</th>
          <th>Output template</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in sessions.sessions" :key="s.id">
          <td>{{ s.name }}</td>
          <td>{{ s.media_type }}</td>
          <td>{{ s.is_builtin ? 'yes' : 'no' }}</td>
          <td>
            <code>{{ s.output_path_template }}</code>
          </td>
          <td>
            <RouterLink :to="`/sessions/${s.id}/edit`"
              ><button class="secondary">Edit</button></RouterLink
            >
            <button class="secondary" @click="openClone(s.id, s.name)">Clone</button>
            <button v-if="!s.is_builtin" class="secondary" @click="deleteSession(s.id, s.name)">
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">No sessions found.</p>
  </div>

  <div v-if="cloneTarget !== null" class="card" style="max-width: 480px">
    <h3 style="margin-top: 0">Clone session</h3>
    <div class="field">
      <label for="clone-name">New name</label>
      <input id="clone-name" v-model="cloneName" />
    </div>
    <div class="row" style="gap: 8px">
      <button @click="submitClone" :disabled="!cloneName">Create clone</button>
      <button class="secondary" @click="cloneTarget = null">Cancel</button>
    </div>
  </div>
</template>
