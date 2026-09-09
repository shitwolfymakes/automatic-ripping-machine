<div class="panel stack">
	<h2 class="panel-title">Title</h2>
	<div class="cluster mt-2 gap-3 sm:gap-4">
		<span class="truncate min-w-0">x</span>
		<button class="btn btn-primary btn-sm" aria-pressed={on}>Go</button>
		<div class="progress-fill" style:--progress="{pct}%"></div>
		<p class="sr-only hidden md:block">hidden</p>
	</div>
</div>
<style>
	/* lucide renders its own svg; size it here */
	:global(.x svg) { width: 1rem; }
	.local { color: var(--color-text-muted); }
</style>
