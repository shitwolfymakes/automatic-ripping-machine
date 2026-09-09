<script lang="ts">
    interface Props {
        variant?: 'line' | 'rect' | 'circle';
        width?: string;
        height?: string;
        class?: string;
    }
    let { variant = 'rect', width, height, class: cls = '' }: Props = $props();
</script>

<div
    class="skeleton-surface {cls}"
    data-variant={variant}
    style:width
    style:height
    aria-hidden="true"
></div>

<style>
    /* Skeleton.svelte takes arbitrary width/height (callers size it per use),
       so it doesn't fit the fixed-size skeleton-text/block/card modifiers in
       skeleton.css - it keeps its own scoped rule, on the same token those
       use. */
    .skeleton-surface {
        border-radius: var(--radius-sm);
        background: var(--color-primary-tint-2);
    }
    @media (prefers-reduced-motion: no-preference) {
        .skeleton-surface {
            animation: pulse 1.5s ease-in-out infinite;
        }
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
</style>
