<script lang="ts">
	// A filled brand mark (Glyph draws stroke icons only). Decorative: the link
	// or button around it carries the accessible name.
	import { BRAND_MARK_PATHS, type BrandMarkName } from '../../ui/brand-marks';

	interface Props {
		name: BrandMarkName;
		class?: string;
	}

	let { name, class: className = '' }: Props = $props();
</script>

<svg class="shrink-0 {className}" viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true"
	><path d={BRAND_MARK_PATHS[name]} /></svg
>
