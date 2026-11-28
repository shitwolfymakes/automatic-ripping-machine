<script lang="ts">
	import type { JobView, TrackView } from '$lib/types/api.gen';
	import { patchJob } from '$lib/api/jobs';
	import EditionField from '$lib/components/jobs/EditionField.svelte';
	import { errorMessage } from '$lib/utils/errors';
	import { formatTrackDuration } from '$lib/utils/format';
	import { tickMeaning } from '$lib/jobs/rip-plan';
	import { UNRIPPABLE_LABEL } from '$lib/jobs/title-class';
	import {
		anglesFor,
		choiceEdits,
		otherMembers,
		targetFor,
		tickedMembers,
		versionChips,
		versionLine,
		viewsOf,
		type VersionMember,
		type VersionSet,
		type View
	} from '$lib/jobs/version-sets';

	interface Props {
		job: JobView;
		set: VersionSet;
		tracks: TrackView[];
		/** An admin may change the choice; anyone else reads it. */
		canEdit: boolean;
		onrefresh?: () => void;
	}
	let { job, set, tracks, canEdit, onrefresh }: Props = $props();

	let busy = $state(false);
	let error = $state<string | null>(null);
	// "Keep more than one" is view state: a set with two or more ticked opens in it.
	let multiOn = $state(false);

	let ticked = $derived(tickedMembers(set));
	let multi = $derived(multiOn || ticked.length > 1);
	let current = $derived<VersionMember | null>(ticked[0] ?? null);
	let anchor = $derived(current ?? set.members[0]);
	let views = $derived(viewsOf(set));
	let angles = $derived(anglesFor(set, anchor.view));
	let others = $derived(otherMembers(set));
	let hasAxes = $derived(views.length > 1 || angles.length > 1);
	let has3d = $derived(set.members.some((m) => m.view === '3d'));
	let onGrid = $derived(current !== null && !others.includes(current));

	function idOf(member: VersionMember): string {
		return member.row.trackId as string;
	}

	function locked(member: VersionMember): boolean {
		const track = tracks.find((t) => t.id === member.row.trackId);
		return !canEdit || busy || member.row.unrippable || (!!track && tickMeaning(track, job) === 'not-ripped');
	}

	async function save(chosenIds: string[]) {
		busy = true;
		error = null;
		try {
			await patchJob(job.id, { tracks: choiceEdits(set, chosenIds) });
			onrefresh?.();
		} catch (e) {
			error = errorMessage(e, 'Failed to save the choice');
		} finally {
			busy = false;
		}
	}

	function choose(member: VersionMember | null) {
		if (member) save([idOf(member)]);
	}

	function toggleMember(member: VersionMember, on: boolean) {
		const ids = ticked.map(idOf).filter((id) => id !== idOf(member));
		save(on ? [...ids, idOf(member)] : ids);
	}

	function toggleMulti(on: boolean) {
		multiOn = on;
		if (!on && ticked.length > 1) save([idOf(ticked[0])]);
	}

	function viewText(view: View): string {
		return view === '3d' ? '3D' : '2D';
	}

	function label(member: VersionMember): string {
		return `#${member.row.index} ${[...versionChips(set, member), versionLine(set, member)].join(' ')}`;
	}

	const groupName = $derived(`set-${set.pickRef}`);
</script>

{#snippet facts(member: VersionMember)}
	<span class="version-set-facts">
		{formatTrackDuration(member.row.durationSeconds)} | {member.row.sizeLabel}
	</span>
{/snippet}

{#snippet detail(member: VersionMember)}
	<span class="version-set-detail">
		{#if member.row.unrippable}
			<span class="chip chip-sm chip-warning">{UNRIPPABLE_LABEL}</span>
		{:else}
			<span class="version-set-line">{versionLine(set, member)}</span>
		{/if}
		<span class="version-set-source mono">{member.row.sourceName}</span>
	</span>
{/snippet}

{#snippet chips(member: VersionMember)}
	{#each versionChips(set, member) as chip (chip)}
		<span class="chip chip-sm chip-info">{chip}</span>
	{/each}
{/snippet}

{#snippet fullRow(member: VersionMember, kind: 'radio' | 'checkbox')}
	<label class="version-set-item" data-testid="version-member">
		{#if kind === 'radio'}
			<input
				type="radio"
				name="{groupName}-pick"
				aria-label={label(member)}
				checked={current === member}
				disabled={locked(member)}
				onchange={() => choose(member)}
			/>
		{:else}
			<input
				type="checkbox"
				aria-label={label(member)}
				checked={!member.row.excluded}
				disabled={locked(member)}
				onchange={(e) => toggleMember(member, e.currentTarget.checked)}
			/>
		{/if}
		<span class="mono">#{member.row.index}</span>
		{@render chips(member)}
		{@render facts(member)}
		{@render detail(member)}
	</label>
{/snippet}

<div class="version-set" data-testid="version-set-choice">
	{#if multi}
		{#each set.members as member (idOf(member))}
			{@render fullRow(member, 'checkbox')}
			<div class="version-set-edition" data-testid="version-edition">
				<span>Edition name</span>
				<EditionField
					jobId={job.id}
					trackId={idOf(member)}
					edition={tracks.find((t) => t.id === idOf(member))?.edition}
					{canEdit}
					onsaved={onrefresh}
				/>
			</div>
		{/each}
	{:else if hasAxes}
		{#if views.length > 1}
			<fieldset class="version-set-group">
				<legend class="version-set-legend">View</legend>
				{#each views as view (view)}
					{@const target = targetFor(set, anchor, { view })}
					<label class="version-set-item">
						<input
							type="radio"
							name="{groupName}-view"
							aria-label={viewText(view)}
							checked={onGrid && anchor.view === view}
							disabled={!target || locked(target)}
							onchange={() => choose(target)}
						/>
						<span>{viewText(view)}</span>
						{#if target}{@render facts(target)}{@render detail(target)}{/if}
					</label>
				{/each}
			</fieldset>
		{/if}
		{#if angles.length > 1}
			<fieldset class="version-set-group">
				<legend class="version-set-legend">Angle</legend>
				{#each angles as angle (angle)}
					{@const target = targetFor(set, anchor, { angle })}
					<label class="version-set-item">
						<input
							type="radio"
							name="{groupName}-angle"
							aria-label="Angle {angle}"
							checked={onGrid && (anchor.angle ?? 1) === angle}
							disabled={!target || locked(target)}
							onchange={() => choose(target)}
						/>
						<span>Angle {angle}</span>
						{#if target}{@render facts(target)}{@render detail(target)}{/if}
					</label>
				{/each}
			</fieldset>
		{/if}
		{#if others.length > 0}
			<fieldset class="version-set-group">
				<legend class="version-set-legend">Other versions</legend>
				{#each others as member (idOf(member))}
					{@render fullRow(member, 'radio')}
				{/each}
			</fieldset>
		{/if}
	{:else}
		{#each set.members as member (idOf(member))}
			{@render fullRow(member, 'radio')}
		{/each}
	{/if}

	<label class="version-set-item">
		<input
			type="checkbox"
			aria-label="Keep more than one"
			checked={multi}
			disabled={!canEdit || busy}
			onchange={(e) => toggleMulti(e.currentTarget.checked)}
		/>
		<span>Keep more than one</span>
	</label>

	{#if has3d}
		<p class="alert alert-info">3D titles keep their 3D only with a passthrough session.</p>
	{/if}
	{#if error}
		<p class="field-error">{error}</p>
	{/if}
</div>

<style>
	.version-set {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.version-set-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		margin: 0;
		border: 0;
		padding: 0;
		min-width: 0;
	}
	.version-set-legend {
		padding: 0;
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.version-set-item {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		min-width: 0;
	}
	.version-set-edition {
		display: flex;
		gap: 0.5rem;
		margin-left: 1.5rem;
		font-size: 0.75rem;
		color: var(--color-text-secondary);
	}
	.version-set-facts,
	.version-set-line {
		color: var(--color-text-secondary);
	}
	.version-set-detail {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.5rem;
		min-width: 0;
	}
	.version-set-source {
		color: var(--color-text-muted);
	}
</style>
