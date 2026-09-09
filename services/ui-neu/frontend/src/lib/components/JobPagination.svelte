<script lang="ts">
	interface Props {
		page: number;
		pages: number;
		perPage: number;
		total: number;
		onpage: (page: number) => void;
	}

	let { page, pages, perPage, total, onpage }: Props = $props();
</script>

{#if pages > 1}
	<div class="job-pagination flex items-center justify-between">
		<p class="job-pagination-summary">
			Showing {(page - 1) * perPage + 1}&ndash;{Math.min(page * perPage, total)} of {total}
		</p>
		<div class="flex gap-1">
			<button disabled={page <= 1} onclick={() => onpage(page - 1)} class="btn btn-sm">Prev</button>
			{#each Array.from({ length: pages }, (_, i) => i + 1) as p}
				{#if p === page || p === 1 || p === pages || Math.abs(p - page) <= 1}
					<button
						onclick={() => onpage(p)}
						aria-pressed={p === page}
						class="btn btn-sm {p === page ? 'btn-primary' : ''}"
					>{p}</button>
				{:else if Math.abs(p - page) === 2}
					<span class="job-pagination-ellipsis px-1">...</span>
				{/if}
			{/each}
			<button disabled={page >= pages} onclick={() => onpage(page + 1)} class="btn btn-sm">Next</button>
		</div>
	</div>
{/if}

<style>
	.job-pagination-summary { font-size: 0.875rem; color: var(--color-text-muted); }
	.job-pagination-ellipsis { color: var(--color-text-faint); }
</style>
