<script lang="ts">
	import { tick } from 'svelte';
	import { FIELD_INPUT_CLASS } from '$lib/types/notifications';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo } from '$lib/api/channels';

	let {
		selected = $bindable(),
		templates = $bindable(),
		eventTypes = []
	}: { selected: string[]; templates: Record<string, ChannelTemplate>; eventTypes: EventTypeInfo[] } = $props();

	type FieldName = 'title' | 'body';
	type FocusTarget = { key: string; field: FieldName; el: HTMLInputElement | HTMLTextAreaElement; start: number; end: number };
	let active: FocusTarget | null = $state(null);

	function toggle(key: string, checked: boolean) {
		if (checked) {
			if (!selected.includes(key)) selected = [...selected, key];
		} else {
			selected = selected.filter((k) => k !== key);
		}
	}

	function ensure(key: string): ChannelTemplate {
		if (!templates[key]) templates[key] = { title: null, body: null };
		return templates[key];
	}
	function varsFor(key: string): string[] {
		return eventTypes.find((e) => e.key === key)?.variables ?? [];
	}
	function defaultsFor(key: string): { title: string; body: string } {
		const et = eventTypes.find((e) => e.key === key);
		return et ? { title: et.default_title, body: et.default_body } : { title: '', body: '' };
	}
	function rememberCaret(key: string, field: FieldName, el: HTMLInputElement | HTMLTextAreaElement) {
		active = { key, field, el, start: el.selectionStart ?? el.value.length, end: el.selectionEnd ?? el.value.length };
	}
	async function insertVariable(key: string, varName: string) {
		const token = `{${varName}}`;
		const tmpl: ChannelTemplate = templates[key] ?? { title: null, body: null };
		const target = active && active.key === key
			? active
			: { key, field: 'title' as FieldName, el: null, start: (tmpl.title ?? '').length, end: (tmpl.title ?? '').length };
		const current = (target.field === 'title' ? tmpl.title : tmpl.body) ?? '';
		const start = Math.min(target.start, current.length);
		const end = Math.min(target.end, current.length);
		const next = current.slice(0, start) + token + current.slice(end);
		templates = {
			...templates,
			[key]: {
				title: target.field === 'title' ? next || null : tmpl.title ?? null,
				body: target.field === 'body' ? next || null : tmpl.body ?? null
			}
		};
		const caret = start + token.length;
		await tick();
		if (target.el) { target.el.focus(); target.el.setSelectionRange(caret, caret); active = { ...target, start: caret, end: caret }; }
	}
</script>

<fieldset class="relative space-y-3">
	<legend class="sr-only">Events</legend>
	{#each eventTypes as et (et.key)}
		<div class="rounded-md border border-primary/15 bg-page p-3 dark:border-primary/20 dark:bg-primary/5">
			<label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
				<input
					type="checkbox"
					aria-label={et.label}
					checked={selected.includes(et.key)}
					onchange={(e) => toggle(et.key, (e.currentTarget as HTMLInputElement).checked)}
					class="rounded border-primary/40 text-primary focus:ring-primary"
				/>
				<span class="font-medium">{et.label}</span>
			</label>
			{#if selected.includes(et.key)}
				<div class="mt-3 space-y-2 pl-6">
					<label class="flex flex-col gap-1">
						<span class="text-xs font-medium text-gray-600 dark:text-gray-400">Title</span>
						<input
							aria-label={`${et.key} title`}
							placeholder={defaultsFor(et.key).title}
							value={templates[et.key]?.title ?? ''}
							oninput={(e) => { ensure(et.key).title = (e.currentTarget as HTMLInputElement).value || null; rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement); }}
							onfocus={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
							onkeyup={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
							onclick={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
							class={FIELD_INPUT_CLASS}
						/>
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-xs font-medium text-gray-600 dark:text-gray-400">Body</span>
						<textarea
							aria-label={`${et.key} body`}
							rows="2"
							placeholder={defaultsFor(et.key).body}
							value={templates[et.key]?.body ?? ''}
							oninput={(e) => { ensure(et.key).body = (e.currentTarget as HTMLTextAreaElement).value || null; rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement); }}
							onfocus={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
							onkeyup={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
							onclick={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
							class={FIELD_INPUT_CLASS}
						></textarea>
					</label>
					<p class="text-xs text-gray-500 dark:text-gray-400">Leave blank to use the default shown.</p>
					<div class="flex flex-wrap gap-1">
						{#each varsFor(et.key) as v}
							<button
								type="button"
								aria-label={`Insert {${v}}`}
								onclick={() => insertVariable(et.key, v)}
								class="rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary hover:bg-primary/20 dark:bg-primary/15 dark:hover:bg-primary/25"
							><code>{`{${v}}`}</code></button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	{/each}
</fieldset>
