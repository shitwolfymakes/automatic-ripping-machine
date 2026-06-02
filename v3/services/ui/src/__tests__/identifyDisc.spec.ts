import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import IdentifyDiscDialog from '../components/IdentifyDiscDialog.vue'
import type { JobView } from '../api/types'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function makeJob(overrides: Partial<JobView> = {}): JobView {
  return {
    id: 'job_x',
    drive_id: 'drv_x',
    disc_type: 'dvd',
    status: 'awaiting_user_id',
    title: null,
    year: null,
    poster_url: null,
    poster_url_manual: null,
    metadata_json: {},
    resumed_from_crash: false,
    ...overrides,
  }
}

function resolveSuccessResponse(jobOverrides: Partial<JobView> = {}) {
  return {
    job: makeJob({ status: 'identified', title: 'Iron Man', year: 2008, ...jobOverrides }),
    fan_out: [],
  }
}

describe('IdentifyDiscDialog.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('submits title + year and emits identified with the resolve response', async () => {
    const resp = resolveSuccessResponse()
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(resp))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(IdentifyDiscDialog, { props: { job: makeJob() } })
    await wrapper.find('[data-testid="identify-title"]').setValue('Iron Man')
    await wrapper.find('[data-testid="identify-year"]').setValue('2008')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const call = fetchMock.mock.calls[0]
    expect(call[0]).toMatch(/\/api\/jobs\/job_x\/resolve$/)
    const body = JSON.parse((call[1] as RequestInit).body as string)
    expect(body).toEqual({ title: 'Iron Man', year: 2008 })

    const emitted = wrapper.emitted('identified')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(resp)
  })

  it('submit is disabled while title is blank or whitespace, enabled once set', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(IdentifyDiscDialog, { props: { job: makeJob() } })
    const btn = wrapper.find<HTMLButtonElement>('[data-testid="identify-submit"]')
    expect(btn.attributes('disabled')).toBeDefined()
    await wrapper.find('[data-testid="identify-title"]').setValue('   ')
    expect(btn.attributes('disabled')).toBeDefined()
    await wrapper.find('[data-testid="identify-title"]').setValue('Blade Runner')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('surfaces API errors in the .error paragraph and does not emit identified', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'something broke' }, 500))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(IdentifyDiscDialog, { props: { job: makeJob() } })
    await wrapper.find('[data-testid="identify-title"]').setValue('Iron Man')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('.error').text()).toContain('something broke')
    expect(wrapper.emitted('identified')).toBeFalsy()
  })

  it('cancel button emits close', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(IdentifyDiscDialog, { props: { job: makeJob() } })
    await wrapper.find('button.secondary').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('prefills the form with existing job.title / job.year if present', () => {
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(IdentifyDiscDialog, {
      props: { job: makeJob({ title: 'Sintel', year: 2010 }) },
    })
    const titleInput = wrapper.find<HTMLInputElement>('[data-testid="identify-title"]')
    const yearInput = wrapper.find<HTMLInputElement>('[data-testid="identify-year"]')
    expect(titleInput.element.value).toBe('Sintel')
    expect(yearInput.element.value).toBe('2010')
  })

  describe('CD mode', () => {
    function makeCdJob(extra: Partial<JobView> = {}): JobView {
      return makeJob({
        disc_type: 'cd',
        title: null,
        metadata_json: {
          scan_result: {
            titles: [
              { index: 1, duration_seconds: 180 },
              { index: 2, duration_seconds: 220 },
              { index: 3, duration_seconds: 195 },
            ],
          },
        },
        ...extra,
      })
    }

    it('renders the CD body (album / artist / per-track) when disc_type is cd', () => {
      vi.stubGlobal('fetch', vi.fn())
      const wrapper = mount(IdentifyDiscDialog, { props: { job: makeCdJob() } })
      expect(wrapper.find('[data-testid="identify-album"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="identify-artist"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="identify-track-1"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="identify-track-2"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="identify-track-3"]').exists()).toBe(true)
      // The DVD/movie title field should NOT render for CDs.
      expect(wrapper.find('[data-testid="identify-title"]').exists()).toBe(false)
    })

    it('prefills album from job.title when set', () => {
      vi.stubGlobal('fetch', vi.fn())
      const wrapper = mount(IdentifyDiscDialog, {
        props: { job: makeCdJob({ title: 'Vol Label Album' }) },
      })
      const albumInput = wrapper.find<HTMLInputElement>('[data-testid="identify-album"]')
      expect(albumInput.element.value).toBe('Vol Label Album')
    })

    it('disables submit until both album and artist have values', async () => {
      vi.stubGlobal('fetch', vi.fn())
      const wrapper = mount(IdentifyDiscDialog, { props: { job: makeCdJob() } })
      const btn = wrapper.find<HTMLButtonElement>('[data-testid="identify-submit"]')
      expect(btn.attributes('disabled')).toBeDefined()
      await wrapper.find('[data-testid="identify-album"]').setValue('Album')
      expect(btn.attributes('disabled')).toBeDefined()
      await wrapper.find('[data-testid="identify-artist"]').setValue('Artist')
      expect(btn.attributes('disabled')).toBeUndefined()
    })

    it('submit posts structured metadata with artist + album + tracks array', async () => {
      const resp = resolveSuccessResponse({
        disc_type: 'cd',
        title: 'Animals',
        metadata_json: {
          artist: 'Pink Floyd',
          album: 'Animals',
          tracks: [
            { title: 'Pigs on the Wing 1' },
            { title: 'Dogs' },
            { title: 'Pigs (Three Different Ones)' },
          ],
        },
      })
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(resp))
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = mount(IdentifyDiscDialog, { props: { job: makeCdJob() } })
      await wrapper.find('[data-testid="identify-album"]').setValue('Animals')
      await wrapper.find('[data-testid="identify-artist"]').setValue('Pink Floyd')
      await wrapper.find('[data-testid="identify-track-1"]').setValue('Pigs on the Wing 1')
      await wrapper.find('[data-testid="identify-track-2"]').setValue('Dogs')
      await wrapper.find('[data-testid="identify-track-3"]').setValue('Pigs (Three Different Ones)')
      await wrapper.find('[data-testid="identify-year"]').setValue('1977')
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      const call = fetchMock.mock.calls[0]
      expect(call[0]).toMatch(/\/api\/jobs\/job_x\/resolve$/)
      const body = JSON.parse((call[1] as RequestInit).body as string)
      expect(body).toEqual({
        title: 'Animals',
        year: 1977,
        metadata: {
          artist: 'Pink Floyd',
          album: 'Animals',
          tracks: [
            { title: 'Pigs on the Wing 1' },
            { title: 'Dogs' },
            { title: 'Pigs (Three Different Ones)' },
          ],
        },
      })
      expect(wrapper.emitted('identified')).toBeTruthy()
    })

    it('falls back gracefully when scan_result has no titles', () => {
      vi.stubGlobal('fetch', vi.fn())
      const wrapper = mount(IdentifyDiscDialog, {
        props: { job: makeJob({ disc_type: 'cd', metadata_json: {} }) },
      })
      expect(wrapper.find('[data-testid="identify-track-1"]').exists()).toBe(false)
      // Helper line is shown so the user knows track names won't be set.
      expect(wrapper.text()).toContain("couldn't be determined")
    })
  })
})
