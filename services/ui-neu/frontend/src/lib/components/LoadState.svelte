<script lang="ts" generics="T">
    import type { Snippet } from 'svelte';

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
        transitionKey: string;
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
        errorSlot,
        transitionKey
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

<!-- Phase swaps are INSTANT — deliberately no transitions here. The previous
     send/receive crossfade kept the outgoing phase (e.g. the skeleton) in
     layout for its 200ms outro while the incoming content mounted, so the
     document was momentarily double-height: everything below slid down, then
     snapped back when the outro finished. An instant swap of the skeleton
     filling in with real content is the smoothest handoff (same rule as the
     transcoder stats block); page-entry softness comes from the route roots'
     in:panel, not from here. -->
{#if phase === 'waiting'}
    <!-- Pre-minDelay window: reserve the skeleton's space invisibly instead of
         rendering nothing. A fast load then fills already-reserved layout (no
         jump); a slow one shows the skeleton at minDelay as before.
         visibility:hidden keeps geometry without a skeleton flash. -->
    <div class="invisible" aria-hidden="true">
        {@render loadingSlot()}
    </div>
{:else if phase === 'error'}
    <div>
        {#if errorSlot}
            {@render errorSlot(error!)}
        {:else}
            <p class="text-red-600 dark:text-red-400">Failed to load: {error!.message}</p>
        {/if}
    </div>
{:else if phase === 'loading'}
    <div>
        {@render loadingSlot()}
    </div>
{:else if phase === 'empty'}
    <div>
        {#if empty}
            {@render empty()}
        {:else}
            {@render loadingSlot()}
        {/if}
    </div>
{:else if phase === 'ready'}
    <div>
        {@render ready(data!)}
    </div>
{/if}
