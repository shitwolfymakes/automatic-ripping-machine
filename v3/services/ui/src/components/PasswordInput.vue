<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  modelValue: string
  id: string
  autocomplete: 'current-password' | 'new-password'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const show = ref(false)
const inputType = computed(() => (show.value ? 'text' : 'password'))

function onInput(e: Event): void {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="password-input">
    <input
      :id="props.id"
      :type="inputType"
      :value="props.modelValue"
      :autocomplete="props.autocomplete"
      @input="onInput"
    />
    <button
      type="button"
      class="toggle-visibility"
      :data-testid="`toggle-password-visibility-${props.id}`"
      :aria-label="show ? 'Hide password' : 'Show password'"
      :aria-pressed="show"
      @click="show = !show"
    >
      {{ show ? 'Hide' : 'Show' }}
    </button>
  </div>
</template>

<style scoped>
.password-input {
  display: flex;
  gap: 4px;
}
.password-input input {
  flex: 1;
  min-width: 0;
}
.toggle-visibility {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid var(--c-border, #ddd);
  border-radius: 4px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--c-muted, #666);
  cursor: pointer;
}
.toggle-visibility:hover {
  background: var(--c-border, #eee);
}
</style>
