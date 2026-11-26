<script lang="ts">
	// The notice the ISO picker shows while the server has no ISO library
	// configured (a 503 from the library endpoint).
	import Glyph from '../../shared/Glyph.svelte';
</script>

<div class="alert alert-info iso-picker-setup">
	<p class="alert-title flex items-center gap-2">
		<Glyph name="info" />
		Set up your ISO library first
	</p>
	<div class="alert-body stack stack-sm">
		<p>ARM reads ISO files from one folder on the server. It doesn't know which folder yet.</p>
		<ol class="stack stack-sm iso-picker-setup-steps">
			<li>
				Add <code class="mono">ARM_HOST_ISO_LIBRARY_PATH</code> to the <code class="mono">.env</code> file, pointing at
				the folder that holds your ISO files, for example a share on your NAS.
				<pre class="code-block iso-picker-setup-code">ARM_HOST_ISO_LIBRARY_PATH=/mnt/nas/iso</pre>
			</li>
			<li>
				Run <code class="mono">armctl up</code> so the container can see the folder. On a development checkout, run
				<code class="mono">bash devtools/setup-dev.sh up</code> instead.
			</li>
			<li>Open Rip from ISO again and pick a file.</li>
		</ol>
		<p>ARM only reads this folder. It never moves, renames or deletes your ISO files.</p>
	</div>
</div>

<style>
	.iso-picker-setup-code {
		margin-top: 0.5rem;
	}
	.iso-picker-setup-steps {
		padding-left: 1.25rem;
		list-style: decimal;
	}
</style>
