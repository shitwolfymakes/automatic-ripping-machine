<script lang="ts">
    import { transcoderEnabled } from '$lib/stores/config';

    interface Props {
        drivesOnline: number | null;
        armOnline: boolean;
        transcoderOnline: boolean;
    }
    let { drivesOnline, armOnline, transcoderOnline }: Props = $props();
</script>

<section>
    <div class="panel empty-dashboard-panel">
        <svg class="empty-dashboard-icon mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="3" />
            <circle cx="12" cy="12" r="6.5" stroke-width="0.75" opacity="0.4" />
        </svg>
        <p class="empty-dashboard-title">
            {$transcoderEnabled ? 'No active rips or transcodes' : 'No active rips'}
        </p>
        <p class="empty-dashboard-hint">Insert a disc to get started - {drivesOnline} drive{drivesOnline !== 1 ? 's' : ''} online{#if !armOnline}, ARM offline{/if}{#if $transcoderEnabled && !transcoderOnline}, transcoder offline{/if}</p>
    </div>
</section>

<style>
    .empty-dashboard-panel {
        padding: 1.5rem;
        text-align: center;
    }
    .empty-dashboard-icon {
        width: 3rem;
        height: 3rem;
        color: var(--color-text-faint);
    }
    .empty-dashboard-title {
        margin-top: 0.75rem;
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--color-text-muted);
    }
    .empty-dashboard-hint {
        margin-top: 0.25rem;
        font-size: 0.75rem;
        color: var(--color-text-faint);
    }
</style>
