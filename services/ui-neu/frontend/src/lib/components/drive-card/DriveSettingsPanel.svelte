<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
	import { updateDrive } from '$lib/api/drives';
	import {
		numberInputText,
		parsePrescanInput,
		parseRipSpeed,
		PRESCAN_FIELDS,
		prescanInputTexts,
		type PrescanField,
		type PrescanKey
	} from '$lib/utils/drive-settings';
	import SlideOver from '../SlideOver.svelte';

	interface Props {
		/** The drive whose settings the panel edits. */
		drive: Drive;
		/** Whether the slide-over is open. Bindable: Escape in a field closes it. */
		open?: boolean;
		/** The default session picker's choices. */
		sessions: SessionView[];
		/** The global prescan defaults, shown as the inputs' placeholders. */
		globalDefaults?: Partial<Record<PrescanKey, number>>;
		/** Called after a setting is saved. */
		onupdate?: () => void | Promise<void>;
	}

	let { drive, open = $bindable(false), sessions, globalDefaults = {}, onupdate }: Props = $props();

	let savingDefaultSession = $state(false);
	let defaultSessionError = $state<string | null>(null);
	let speedInput = $state('');
	let savingSpeed = $state(false);
	let savingPrescan = $state(false);

	// Prescan override inputs - empty string means "use global default"
	let prescanInputs = $state<Record<PrescanKey, string>>(prescanInputTexts(undefined));

	// Sync server values to inputs when settings panel closes
	$effect.pre(() => {
		if (!open) prescanInputs = prescanInputTexts(drive);
	});

	async function savePrescanField(field: PrescanField) {
		const parsed = parsePrescanInput(prescanInputs[field.key], field, globalDefaults[field.key]);
		if (!parsed) return;
		if (parsed.matchesDefault) prescanInputs[field.key] = '';
		if (parsed.value === (drive[field.key] ?? null)) return;

		savingPrescan = true;
		try {
			await updateDrive(drive.id, { [field.key]: parsed.value });
			onupdate?.();
		} catch {
			prescanInputs[field.key] = numberInputText(drive[field.key]);
		} finally {
			savingPrescan = false;
		}
	}

	$effect.pre(() => {
		const serverValue = numberInputText(drive.rip_speed);
		if (!open) {
			speedInput = serverValue;
		}
	});

	async function saveSpeed() {
		const newSpeed = parseRipSpeed(speedInput);
		if (newSpeed === undefined || newSpeed === (drive.rip_speed ?? null)) return;

		savingSpeed = true;
		try {
			await updateDrive(drive.id, { rip_speed: newSpeed });
			onupdate?.();
		} catch {
			// revert input on failure
			speedInput = numberInputText(drive.rip_speed);
		} finally {
			savingSpeed = false;
		}
	}

	function onSpeedKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			(e.target as HTMLInputElement).blur();
		}
		if (e.key === 'Escape') {
			speedInput = numberInputText(drive.rip_speed);
			open = false;
		}
	}

	async function saveDefaultSession(value: string) {
		savingDefaultSession = true;
		defaultSessionError = null;
		try {
			await updateDrive(drive.id, { default_session_id: value || null });
			onupdate?.();
		} catch (e) {
			defaultSessionError = errorMessage(e, 'Failed to set default session');
		} finally {
			savingDefaultSession = false;
		}
	}
</script>

<SlideOver bind:open title="{drive.display_name || drive.device_path || 'Drive'} settings" width="max-w-md">
	<div class="flex flex-col gap-5 drive-card-settings-body">
		<div class="field">
			<label for="default-session-{drive.id}" class="field-label">Default session</label>
			<select
				id="default-session-{drive.id}"
				data-testid="drive-default-session"
				value={drive.default_session_id ?? ''}
				onchange={(e) => saveDefaultSession((e.currentTarget as HTMLSelectElement).value)}
				disabled={savingDefaultSession}
			>
				<option value="">- none -</option>
				{#each sessions as s (s.id)}
					<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
				{/each}
			</select>
			<p class="field-help">Auto-applied to auto-mode rips on this drive.</p>
			{#if defaultSessionError}
				<p class="field-error" data-testid="drive-default-session-error">{defaultSessionError}</p>
			{/if}
		</div>

		<div class="field">
			<div class="flex items-center justify-between gap-2">
				<label for="rip-speed-{drive.id}" class="field-label">Rip Speed</label>
				<input
					id="rip-speed-{drive.id}"
					type="number"
					min="1"
					max="99"
					bind:value={speedInput}
					onblur={saveSpeed}
					onkeydown={onSpeedKeydown}
					disabled={savingSpeed}
					class="drive-card-number-input"
				/>
			</div>
			<p class="field-help">Empty = max speed. Lower values help with read errors on problematic discs.</p>
		</div>

		<div class="stack drive-card-prescan-section">
			<div class="eyebrow">Pre-scan tuning</div>
			{#each PRESCAN_FIELDS as field (field.key)}
				<div class="field">
					<div class="flex items-center justify-between gap-2">
						<label for="prescan-{field.key}-{drive.id}" class="field-label">
							{field.label}{#if field.unit}&nbsp;<span class="drive-card-unit">({field.unit})</span>{/if}
						</label>
						<input
							id="prescan-{field.key}-{drive.id}"
							type="number"
							min={field.min}
							max={field.max}
							placeholder={numberInputText(globalDefaults[field.key])}
							value={prescanInputs[field.key]}
							oninput={(e) => (prescanInputs[field.key] = (e.target as HTMLInputElement).value)}
							onblur={() => savePrescanField(field)}
							onkeydown={(e) => {
								if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
								if (e.key === 'Escape') {
									prescanInputs[field.key] = numberInputText(drive[field.key]);
									open = false;
								}
							}}
							disabled={savingPrescan}
							class="drive-card-number-input"
						/>
					</div>
					<p class="field-help">{field.tooltip}</p>
				</div>
			{/each}
		</div>
	</div>
</SlideOver>

<style>
	.drive-card-settings-body {
		font-size: 0.875rem;
	}
	.drive-card-number-input {
		width: 6rem;
		text-align: center;
	}
	/* the original was space-y-3 (0.75rem) - between stack-sm's 0.5rem and
	   stack's own 1rem, so neither modifier matches exactly. */
	.drive-card-prescan-section {
		gap: 0.75rem;
		border-top: 1px solid var(--color-border-strong);
		padding-top: 1rem;
	}
	.drive-card-unit {
		font-size: 0.75rem;
		color: var(--color-text-faint);
	}
</style>
