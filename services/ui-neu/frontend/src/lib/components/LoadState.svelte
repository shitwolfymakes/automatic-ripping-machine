<script lang="ts" generics="T">
    import type { Snippet } from 'svelte';
    import { fade } from 'svelte/transition';
    import { fadeIn } from '$lib/transitions';

    interface Props {
        data: T | null | undefined;
        loading: boolean;
        error?: Error | null;
        isEmpty?: (data: T) => boolean;
        minDelay?: number;
        loadingSlot: Snippet;
        ready: Snippet<[T]>;
        empty?: Snippet;
        errorSlot?: Snippet<[Error]>;
        // Kept for call-site compatibility; phases used to crossfade by key.
        transitionKey?: string;
    }

    let {
        data,
        loading,
        error = null,
        isEmpty,
        minDelay = 150,
        loadingSlot,
        ready,
        empty,
        errorSlot
    }: Props = $props();

    function defaultIsEmpty(d: T): boolean {
        if (Array.isArray(d)) return d.length === 0;
        return false;
    }

    let delayElapsed = $state(false);
    let timer: ReturnType<typeof setTimeout> | null = null;

    $effect(() => {
        if (loading) {
            if (minDelay === 0) {
                delayElapsed = true;
            } else {
                timer = setTimeout(() => {
                    delayElapsed = true;
                }, minDelay);
            }
        } else {
            if (timer) clearTimeout(timer);
            timer = null;
            delayElapsed = false;
        }
        return () => {
            if (timer) clearTimeout(timer);
        };
    });

    const phase = $derived.by(() => {
        if (error) return 'error';
        if (loading && delayElapsed) return 'loading';
        if (loading) return 'waiting';
        if (data == null) return 'loading';
        const emptyCheck = isEmpty ?? defaultIsEmpty;
        if (emptyCheck(data)) return 'empty';
        return 'ready';
    });
</script>

{#if phase === 'error'}
    <div in:fade|local={fadeIn}>
        {#if errorSlot}
            {@render errorSlot(error!)}
        {:else}
            <p class="text-red-600 dark:text-red-400">Failed to load: {error!.message}</p>
        {/if}
    </div>
{:else if phase === 'loading'}
    <div in:fade|local={fadeIn}>
        {@render loadingSlot()}
    </div>
{:else if phase === 'empty'}
    <div in:fade|local={fadeIn}>
        {#if empty}
            {@render empty()}
        {:else}
            {@render loadingSlot()}
        {/if}
    </div>
{:else if phase === 'ready'}
    <div in:fade|local={fadeIn}>
        {@render ready(data!)}
    </div>
{/if}
