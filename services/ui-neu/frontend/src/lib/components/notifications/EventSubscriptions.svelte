<script lang="ts">
	import { tick } from 'svelte';
	import type { ChannelTemplate } from '$lib/types/notifications';
	import type { EventTypeInfo, ScriptInput } from '$lib/api/channels';
	import { withInput, spliceToken, withText, type TemplateField } from '../../notifications/event-templates';

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

	type FocusTarget = {
		key: string;
		field: TemplateField;
		el: HTMLInputElement | HTMLTextAreaElement;
		start: number;
		end: number;
	};
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
	function rememberCaret(key: string, field: TemplateField, el: HTMLInputElement | HTMLTextAreaElement) {
		active = { key, field, el, start: el.selectionStart ?? el.value.length, end: el.selectionEnd ?? el.value.length };
	}
	// The handlers of an event's title or body: an edit writes the field,
	// null when blank, and every edit, focus, key and click remembers
	// where the caret is.
	function fieldHandlers(key: string, field: TemplateField) {
		const caret = (e: Event) => rememberCaret(key, field, e.currentTarget as HTMLInputElement | HTMLTextAreaElement);
		return {
			oninput: (e: Event) => {
				ensure(key)[field] = (e.currentTarget as HTMLInputElement | HTMLTextAreaElement).value || null;
				caret(e);
			},
			onfocus: caret,
			onkeyup: caret,
			onclick: caret
		};
	}
	function setInput(key: string, inputKey: string, value: string) {
		const t = ensure(key);
		t.inputs = withInput(t.inputs, inputKey, value);
	}
	async function insertVariable(key: string, varName: string) {
		const token = `{${varName}}`;
		const tmpl: ChannelTemplate = templates[key] ?? { title: null, body: null };
		const target =
			active && active.key === key
				? active
				: {
						key,
						field: 'title' as TemplateField,
						el: null,
						start: (tmpl.title ?? '').length,
						end: (tmpl.title ?? '').length
					};
		const current = (target.field === 'title' ? tmpl.title : tmpl.body) ?? '';
		const { text, caret } = spliceToken(current, target.start, target.end, token);
		templates = { ...templates, [key]: withText(tmpl, target.field, text) };
		await tick();
		if (target.el) {
			target.el.focus();
			target.el.setSelectionRange(caret, caret);
			active = { ...target, start: caret, end: caret };
		}
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
							placeholder={et.default_title}
							value={templates[et.key]?.title ?? ''}
							{...fieldHandlers(et.key, 'title')}
						/>
					</label>
					<label class="field">
						<span class="field-label event-subscriptions-sublabel">Body</span>
						<textarea
							aria-label={`${et.key} body`}
							rows="2"
							placeholder={et.default_body}
							value={templates[et.key]?.body ?? ''}
							{...fieldHandlers(et.key, 'body')}></textarea>
					</label>
					{#each overridable as i (i.key)}
						<label class="field">
							<span class="field-label event-subscriptions-sublabel">{i.label}{i.required ? ' *' : ''}</span>
							{#if i.values && i.values.length}
								<select
									aria-label={`${et.key} ${i.label}`}
									value={templates[et.key]?.inputs?.[i.key] ?? ''}
									onchange={(e) => setInput(et.key, i.key, (e.currentTarget as HTMLSelectElement).value)}
								>
									<option value="">inherit</option>
									{#each i.values as v (v)}<option value={v}>{v}</option>{/each}
								</select>
							{:else}
								<input
									aria-label={`${et.key} ${i.label}`}
									placeholder="inherit"
									value={templates[et.key]?.inputs?.[i.key] ?? ''}
									oninput={(e) => setInput(et.key, i.key, (e.currentTarget as HTMLInputElement).value)}
								/>
							{/if}
						</label>
					{/each}
					<p class="field-help">
						Leave blank to use the default shown{overridable.length ? "; blank inputs inherit the hook's values." : '.'}
					</p>
					<div class="cluster event-subscriptions-vars">
						{#each et.variables as v (v)}
							<button type="button" aria-label={`Insert {${v}}`} onclick={() => insertVariable(et.key, v)} class="chip"
								><code>{`{${v}}`}</code></button
							>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	{/each}
</fieldset>

<style>
	.event-subscriptions {
		position: relative;
	}
	/* the per-event box is 0.75rem, tighter than panel-section's 1rem. */
	.event-subscriptions-item {
		padding: 0.75rem;
	}
	.event-subscriptions-label {
		font-weight: 500;
	}
	/* mt-3 pl-6: the detail block sits indented and offset under the checkbox row. */
	.event-subscriptions-detail {
		margin-top: 0.75rem;
		padding-left: 1.5rem;
		gap: 0.5rem;
	}
	.event-subscriptions-sublabel {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.event-subscriptions-vars {
		gap: 0.25rem;
	}
</style>
