<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ApiError } from "../api/client";
import { useRipPresetsStore } from "../stores/ripPresets";
import { useSessionsStore } from "../stores/sessions";
import { useTranscodePresetsStore } from "../stores/transcodePresets";
import type { MediaType, SessionView } from "../api/types";

const route = useRoute();
const router = useRouter();
const sessions = useSessionsStore();
const ripPresets = useRipPresetsStore();
const tcPresets = useTranscodePresetsStore();

const editing = computed(() => typeof route.params.id === "string");
const editId = computed(() => (editing.value ? (route.params.id as string) : null));

const name = ref("");
const mediaType = ref<MediaType>("movie");
const ripPresetId = ref("");
const transcodePresetId = ref<string | "">("");
const template = ref("");
const isBuiltin = ref(false);

const error = ref<string | null>(null);
const saving = ref(false);
const previewText = ref("");
const previewError = ref<string | null>(null);
let previewTimer: number | null = null;

const filteredRipPresets = computed(() => ripPresets.byMediaType(mediaType.value));
const filteredTranscodePresets = computed(() => tcPresets.byMediaType(mediaType.value));

onMounted(async () => {
  await Promise.all([ripPresets.fetchAll(), tcPresets.fetchAll()]);
  if (editing.value && editId.value) {
    try {
      const s: SessionView = await sessions.getById(editId.value);
      name.value = s.name;
      mediaType.value = s.media_type;
      ripPresetId.value = s.rip_preset_id;
      transcodePresetId.value = s.transcode_preset_id ?? "";
      template.value = s.output_path_template;
      isBuiltin.value = s.is_builtin;
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Failed to load";
    }
  }
});

watch([template, mediaType, transcodePresetId], () => {
  if (previewTimer !== null) window.clearTimeout(previewTimer);
  if (!template.value) {
    previewText.value = "";
    previewError.value = null;
    return;
  }
  previewTimer = window.setTimeout(async () => {
    try {
      const resp = await sessions.previewTemplate({
        template: template.value,
        media_type: mediaType.value,
        has_transcode_preset: Boolean(transcodePresetId.value),
      });
      previewText.value = resp.expansion;
      previewError.value = null;
    } catch (e) {
      previewText.value = "";
      previewError.value = e instanceof ApiError ? e.message : "Preview failed";
    }
  }, 300);
});

async function save(): Promise<void> {
  saving.value = true;
  error.value = null;
  try {
    if (editing.value && editId.value) {
      const payload = isBuiltin.value
        ? { name: name.value }
        : {
            name: name.value,
            rip_preset_id: ripPresetId.value,
            transcode_preset_id: transcodePresetId.value || null,
            output_path_template: template.value,
          };
      await sessions.update(editId.value, payload);
    } else {
      await sessions.create({
        name: name.value,
        media_type: mediaType.value,
        rip_preset_id: ripPresetId.value,
        transcode_preset_id: transcodePresetId.value || null,
        output_path_template: template.value,
      });
    }
    await router.push("/sessions");
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Save failed";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <h2>{{ editing ? "Edit session" : "New session" }}</h2>
  <p v-if="isBuiltin" class="muted">
    This is a built-in session — only the name can be edited. Use <strong>Clone</strong> from the
    list to customise the rest.
  </p>
  <p v-if="error" class="error">{{ error }}</p>
  <form class="card" style="max-width: 720px" @submit.prevent="save">
    <div class="field">
      <label for="name">Name</label>
      <input id="name" v-model="name" required />
    </div>

    <div class="field">
      <label for="media-type">Media type</label>
      <select id="media-type" v-model="mediaType" :disabled="editing">
        <option value="movie">Movie</option>
        <option value="tv">TV</option>
        <option value="music">Music</option>
        <option value="data">Data</option>
        <option value="iso">ISO</option>
      </select>
    </div>

    <div class="field">
      <label for="rip-preset">Rip preset</label>
      <select id="rip-preset" v-model="ripPresetId" :disabled="isBuiltin" required>
        <option value="" disabled>Choose…</option>
        <option v-for="p in filteredRipPresets" :key="p.id" :value="p.id">
          {{ p.name }}{{ p.is_builtin ? " (built-in)" : "" }}
        </option>
      </select>
    </div>

    <div class="field">
      <label for="tc-preset">Transcode preset</label>
      <select id="tc-preset" v-model="transcodePresetId" :disabled="isBuiltin">
        <option value="">(none)</option>
        <option v-for="p in filteredTranscodePresets" :key="p.id" :value="p.id">
          {{ p.name }}{{ p.is_builtin ? " (built-in)" : "" }}
        </option>
      </select>
    </div>

    <div class="field">
      <label for="template">Output path template</label>
      <input id="template" v-model="template" :disabled="isBuiltin" required />
      <p v-if="previewText" class="muted" style="margin-top: 4px; font-size: 12px">
        Preview: <code>{{ previewText }}</code>
      </p>
      <p v-else-if="previewError" class="error" style="margin-top: 4px; font-size: 12px">
        {{ previewError }}
      </p>
    </div>

    <div class="row" style="gap: 8px">
      <button type="submit" :disabled="saving || !name || (!isBuiltin && (!ripPresetId || !template))">
        {{ saving ? "Saving…" : "Save" }}
      </button>
      <RouterLink to="/sessions"><button class="secondary" type="button">Cancel</button></RouterLink>
    </div>
  </form>
</template>
