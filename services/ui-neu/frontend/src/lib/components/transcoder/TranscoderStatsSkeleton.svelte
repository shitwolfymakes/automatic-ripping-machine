<div class="stack">
	<div class="panel">
		<!-- Same box as the real header row (mb-3 + text-sm line) so the card
	     is the same height before and after the first poll. -->
		<div class="mb-3 flex items-center justify-between">
			<div class="skeleton skeleton-text transcoder-page-skeleton-title"></div>
			<div class="skeleton skeleton-text transcoder-page-skeleton-subtitle"></div>
		</div>
	</div>
	<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
		{#each Array(5) as _unused, i (i)}
			<div class="panel">
				<div class="skeleton skeleton-text transcoder-page-skeleton-label"></div>
				<div class="skeleton skeleton-text transcoder-page-skeleton-value"></div>
			</div>
		{/each}
	</div>
</div>

<style>
	.transcoder-page-skeleton-title {
		height: 1.5rem;
		width: 14rem;
	}
	.transcoder-page-skeleton-subtitle {
		height: 1rem;
		width: 12rem;
	}
	.transcoder-page-skeleton-label {
		height: 1rem;
		width: 4rem;
	}
	.transcoder-page-skeleton-value {
		margin-top: 0.5rem;
		height: 2rem;
		width: 3rem;
	}
</style>
