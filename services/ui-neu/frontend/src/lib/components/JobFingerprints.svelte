<script lang="ts">
	import type { DiscFingerprintView } from '$lib/types/api.gen';

	interface Props {
		fingerprints: DiscFingerprintView[];
	}

	let { fingerprints }: Props = $props();
</script>

<section>
	<h2 class="mb-3 job-detail-section-title">Disc fingerprints</h2>
	<div class="overflow-x-auto job-detail-table-scroll">
		<table class="table responsive-table">
			<thead>
				<tr>
					<th class="table-header">Algorithm</th>
					<th class="table-header">Value</th>
				</tr>
			</thead>
			<tbody>
				{#each fingerprints as fp (`${fp.algo}:${fp.value}`)}
					<tr class="table-row">
						<td class="table-cell job-detail-uppercase" data-label="Algorithm">{fp.algo}</td>
						<td class="truncate table-cell mono job-detail-fingerprint-value" data-label="Value" title={fp.value}
							>{fp.value}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<style>
	.job-detail-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.job-detail-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
	.job-detail-uppercase {
		text-transform: uppercase;
	}
	.job-detail-fingerprint-value {
		max-width: 420px;
		color: var(--color-text-secondary);
	}
</style>
