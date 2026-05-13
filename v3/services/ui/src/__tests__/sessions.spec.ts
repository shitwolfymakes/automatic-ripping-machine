import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionsStore } from '../stores/sessions'
import { ApiError } from '../api/client'

const sessionRow = {
  id: 'ses_x',
  name: 'My Plex 1080p',
  media_type: 'movie',
  is_builtin: false,
  rip_preset_id: 'rpr_x',
  transcode_preset_id: 'tpr_x',
  output_path_template: '{title} ({year}).{ext}',
  overrides_json: null,
  created_by_user_id: 'usr_admin',
  created_at: null,
  updated_at: null,
}

const applicationRow = {
  id: 'sap_1',
  session_id: 'ses_x',
  job_id: 'job_1',
  status: 'queued',
  overrides_json: null,
  overwrite: false,
  created_by_user_id: 'usr_admin',
  created_at: null,
  completed_at: null,
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('sessions store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    localStorage.setItem('arm_token', 'aaa.bbb.ccc')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetchAll loads sessions and clears any prior error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([sessionRow])))
    const store = useSessionsStore()
    store.error = 'stale'
    await store.fetchAll()
    expect(store.sessions.length).toBe(1)
    expect(store.error).toBeNull()
  })

  it('create posts and inserts the new row sorted by name', async () => {
    const sortedFirst = { ...sessionRow, id: 'ses_a', name: 'Alpha' }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([sessionRow]))
      .mockResolvedValueOnce(jsonResponse(sortedFirst, 201))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSessionsStore()
    await store.fetchAll()
    await store.create({
      name: 'Alpha',
      media_type: 'movie',
      rip_preset_id: 'rpr_x',
      output_path_template: '{title}.{ext}',
    })
    expect(store.sessions.map((s) => s.name)).toEqual(['Alpha', 'My Plex 1080p'])
  })

  it('apply returns idempotent flag and tasks on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          session_application: applicationRow,
          tasks: [
            {
              id: 'txt_1',
              session_application_id: 'sap_1',
              source_track_id: 'trk_1',
              status: 'queued',
              output_path: 'Iron Man.mkv',
              progress_pct: 0,
              attempts: 0,
              last_error: null,
              created_at: null,
              updated_at: null,
            },
          ],
          collisions: [],
          idempotent: false,
        }),
      ),
    )
    const store = useSessionsStore()
    const resp = await store.apply('job_1', { session_id: 'ses_x' })
    expect(resp.tasks.length).toBe(1)
    expect(resp.idempotent).toBe(false)
  })

  it('getById returns a single session by id', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(sessionRow)))
    const store = useSessionsStore()
    const row = await store.getById('ses_x')
    expect(row.id).toBe('ses_x')
    expect(row.name).toBe('My Plex 1080p')
  })

  it('update patches and replaces the row in state', async () => {
    const renamed = { ...sessionRow, name: 'Renamed' }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([sessionRow]))
      .mockResolvedValueOnce(jsonResponse(renamed))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSessionsStore()
    await store.fetchAll()
    const updated = await store.update('ses_x', { name: 'Renamed' })
    expect(updated.name).toBe('Renamed')
    expect(store.sessions[0].name).toBe('Renamed')
    // PATCH call uses the correct verb against the per-id URL
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init.method).toBe('PATCH')
  })

  it('remove deletes and prunes state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([sessionRow]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSessionsStore()
    await store.fetchAll()
    expect(store.sessions.length).toBe(1)
    await store.remove('ses_x')
    expect(store.sessions.length).toBe(0)
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init.method).toBe('DELETE')
  })

  it('clone inserts the new row sorted by name', async () => {
    const cloned = { ...sessionRow, id: 'ses_a', name: 'Alpha Clone' }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([sessionRow]))
      .mockResolvedValueOnce(jsonResponse(cloned, 201))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSessionsStore()
    await store.fetchAll()
    const out = await store.clone('ses_x', { name: 'Alpha Clone' })
    expect(out.id).toBe('ses_a')
    expect(store.sessions.map((s) => s.name)).toEqual(['Alpha Clone', 'My Plex 1080p'])
  })

  it('previewTemplate returns the expansion body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ expansion: 'Iron Man (2008).mkv' })),
    )
    const store = useSessionsStore()
    const resp = await store.previewTemplate({
      template: '{title} ({year}).{ext}',
      media_type: 'movie',
      has_transcode_preset: true,
    })
    expect(resp.expansion).toBe('Iron Man (2008).mkv')
  })

  it('fetchAll surfaces server error into store.error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'kaboom' }, 500)))
    const store = useSessionsStore()
    await store.fetchAll()
    expect(store.error).not.toBeNull()
    expect(store.sessions.length).toBe(0)
    expect(store.loading).toBe(false)
  })

  it('apply 409 surfaces collisions in ApiError.body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              message: 'output_path collisions detected',
              collisions: [
                {
                  output_path: 'Iron Man.mkv',
                  existing_task_id: 'txt_other',
                  on_filesystem: false,
                  reason: 'existing_task',
                },
              ],
            },
          },
          409,
        ),
      ),
    )
    const store = useSessionsStore()
    let thrown: ApiError | null = null
    try {
      await store.apply('job_1', { session_id: 'ses_x' })
    } catch (e) {
      if (e instanceof ApiError) thrown = e
    }
    expect(thrown).not.toBeNull()
    expect(thrown!.status).toBe(409)
    const body = thrown!.body as { detail: { collisions: { output_path: string }[] } }
    expect(body.detail.collisions[0].output_path).toBe('Iron Man.mkv')
  })
})
