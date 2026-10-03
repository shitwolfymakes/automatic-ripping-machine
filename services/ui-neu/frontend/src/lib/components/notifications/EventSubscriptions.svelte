<script lang="ts">
	import { tick } from 'svelte';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';

	let {
		selected = $bindable(),
		templates = $bindable(),
		eventTypes = [],
		inputs = []
	}: {
		selected: string[];
		templates: Record<string, ChannelTemplate>;
		eventTypes: EventTypeInfo[];
		inputs?: ScriptInput[];
	} = $props();

	const overridable = $derived(inputs.filter((i) => !i.secret));

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
	function setInput(key: string, inputKey: string, value: string) {
		const t = ensure(key);
		const next = { ...(t.inputs ?? {}) };
		if (value === '') delete next[inputKey]; else next[inputKey] = value;
		t.inputs = Object.keys(next).length ? next : null;
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

<fieldset class="stack stack-sm event-subscriptions">
	<legend class="sr-only">Events</legend>
	{#each eventTypes as et (et.key)}
		<div class="panel-section event-subscriptions-item">
			<label class="field field-row">
				<input
					type="checkbox"
					aria-label={et.label}
					checked={selected.includes(et.key)}
					onchange={(e) => toggle(et.key, (e.currentTarget as HTMLInputElement).checked)}
				/>
				<span class="event-subscriptions-label">{et.label}</span>
			</label>
			{#if selected.includes(et.key)}
				<div class="stack stack-sm event-subscriptions-detail">
					<label class="field">
						<span class="field-label event-subscriptions-sublabel">Title</span>
						<input
							aria-label={`${et.key} title`}
							placeholder={defaultsFor(et.key).title}
							value={templates[et.key]?.title ?? ''}
							oninput={(e) => { ensure(et.key).title = (e.currentTarget as HTMLInputElement).value || null; rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement); }}
							onfocus={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
							onkeyup={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
							onclick={(e) => rememberCaret(et.key, 'title', e.currentTarget as HTMLInputElement)}
						/>
					</label>
					<label class="field">
						<span class="field-label event-subscriptions-sublabel">Body</span>
						<textarea
							aria-label={`${et.key} body`}
							rows="2"
							placeholder={defaultsFor(et.key).body}
							value={templates[et.key]?.body ?? ''}
							oninput={(e) => { ensure(et.key).body = (e.currentTarget as HTMLTextAreaElement).value || null; rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement); }}
							onfocus={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
							onkeyup={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
							onclick={(e) => rememberCaret(et.key, 'body', e.currentTarget as HTMLTextAreaElement)}
						></textarea>
					</label>
					{#each overridable as i (i.key)}
						<label class="field">
							<span class="field-label event-subscriptions-sublabel">{i.label}{i.required ? " *" : ""}</span>
							{#if i.values && i.values.length}
								<select aria-label={`${et.key} ${i.label}`} value={templates[et.key]?.inputs?.[i.key] ?? ''} onchange={(e) => setInput(et.key, i.key, (e.currentTarget as HTMLSelectElement).value)}>
									<option value="">inherit</option>
									{#each i.values as v}<option value={v}>{v}</option>{/each}
								</select>
							{:else}
								<input aria-label={`${et.key} ${i.label}`} placeholder="inherit" value={templates[et.key]?.inputs?.[i.key] ?? ''} oninput={(e) => setInput(et.key, i.key, (e.currentTarget as HTMLInputElement).value)} />
							{/if}
						</label>
					{/each}
					<p class="field-help">Leave blank to use the default shown{overridable.length ? "; blank inputs inherit the hook's values." : '.'}</p>
					<div class="cluster event-subscriptions-vars">
						{#each varsFor(et.key) as v}
							<button
								type="button"
								aria-label={`Insert {${v}}`}
								onclick={() => insertVariable(et.key, v)}
								class="chip"
							><code>{`{${v}}`}</code></button>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	{/each}
</fieldset>

<style>
	.event-subscriptions { position: relative; }
	/* the original per-event box was p-3 (0.75rem), tighter than panel-section's 1rem. */
	.event-subscriptions-item { padding: 0.75rem; }
	.event-subscriptions-label { font-weight: 500; }
	/* mt-3 pl-6: the detail block sits indented and offset under the checkbox row. */
	.event-subscriptions-detail { margin-top: 0.75rem; padding-left: 1.5rem; gap: 0.5rem; }
	.event-subscriptions-sublabel { font-size: 0.75rem; line-height: 1rem; }
	.event-subscriptions-vars { gap: 0.25rem; }
</style>
