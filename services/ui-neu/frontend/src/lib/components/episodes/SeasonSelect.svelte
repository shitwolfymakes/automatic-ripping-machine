<script lang="ts">
	// One season control for the Re-run form and the per-track rows: a select
	// over the source's seasons, or a number input when that list could not
	// load. It reads "-" when unset; no season is ever assumed.
	type Season = number | 'scan' | null;
	interface Props {
		value: Season;
		/** The source's regular seasons; null when the list could not load. */
		seasons: number[] | null;
		/** Offer "Scan all seasons" (the Re-run form only). */
		allowScan?: boolean;
		ariaLabel?: string;
		id?: string;
		class?: string;
		disabled?: boolean;
		onchange: (value: Season) => void;
	}
	let {
		value,
		seasons,
		allowScan = false,
		ariaLabel,
		id,
		class: className = '',
		disabled = false,
		onchange
	}: Props = $props();

	// The current season stays selectable while the list loads or lacks it.
	const listed = $derived(
		[...new Set([...(seasons ?? []), ...(typeof value === 'number' ? [value] : [])])]
			.filter((n) => n > 0)
			.sort((a, b) => a - b)
	);

	// The string/number boundary: '' is unset, 'scan' scans (when allowed), and
	// anything but a whole number from 0 up is unset.
	function toSeason(raw: string): Season {
		if (raw === '') return null;
		if (raw === 'scan') return allowScan ? 'scan' : null;
		const n = Number(raw);
		return Number.isInteger(n) && n >= 0 ? n : null;
	}
</script>

{#if seasons}
	<select
		{id}
		class="field-control {className}"
		aria-label={ariaLabel}
		{disabled}
		value={value == null ? '' : String(value)}
		onchange={(e) => onchange(toSeason(e.currentTarget.value))}
	>
		<option value="" disabled>-</option>
		{#if allowScan}<option value="scan">Scan all seasons</option>{/if}
		<option value="0">Specials</option>
		{#each listed as n (n)}
			<option value={String(n)}>Season {n}</option>
		{/each}
	</select>
{:else}
	<input
		{id}
		class="field-control {className}"
		aria-label={ariaLabel}
		{disabled}
		type="number"
		min="0"
		placeholder="-"
		value={typeof value === 'number' ? value : ''}
		oninput={(e) => onchange(toSeason(e.currentTarget.value))}
	/>
{/if}
