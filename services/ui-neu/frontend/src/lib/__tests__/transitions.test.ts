import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('transitions', () => {
    beforeEach(() => {
        vi.resetModules();
    });

    it('does not export a crossfade: content must appear in place, never animate geometry', async () => {
        const mod = (await import('../transitions')) as Record<string, unknown>;
        expect(mod.send).toBeUndefined();
        expect(mod.receive).toBeUndefined();
    });

    it('fadeIn has duration 150 when reduced-motion is not set', async () => {
        vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
        const mod = await import('../transitions');
        expect(mod.fadeIn.duration).toBe(150);
    });

    it('fadeIn has duration 0 when reduced-motion is preferred', async () => {
        vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
        const mod = await import('../transitions');
        expect(mod.fadeIn.duration).toBe(0);
    });

    it('fadeOut mirrors fadeIn duration', async () => {
        vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
        const mod = await import('../transitions');
        expect(mod.fadeOut.duration).toBe(mod.fadeIn.duration);
    });
});
