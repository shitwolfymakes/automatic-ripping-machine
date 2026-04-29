import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useSessionsStore } from "../stores/sessions";
import { ApiError } from "../api/client";

const sessionRow = {
  id: "ses_x",
  name: "My Plex 1080p",
  media_type: "movie",
  is_builtin: false,
  rip_preset_id: "rpr_x",
  transcode_preset_id: "tpr_x",
  output_path_template: "{title} ({year}).{ext}",
  overrides_json: null,
  created_by_user_id: "usr_admin",
  created_at: null,
  updated_at: null,
};

const applicationRow = {
  id: "sap_1",
  session_id: "ses_x",
  job_id: "job_1",
  status: "queued",
  overrides_json: null,
  overwrite: false,
  created_by_user_id: "usr_admin",
  created_at: null,
  completed_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("sessions store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    localStorage.setItem("arm_token", "aaa.bbb.ccc");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetchAll loads sessions and clears any prior error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse([sessionRow])),
    );
    const store = useSessionsStore();
    store.error = "stale";
    await store.fetchAll();
    expect(store.sessions.length).toBe(1);
    expect(store.error).toBeNull();
  });

  it("create posts and inserts the new row sorted by name", async () => {
    const sortedFirst = { ...sessionRow, id: "ses_a", name: "Alpha" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([sessionRow]))
      .mockResolvedValueOnce(jsonResponse(sortedFirst, 201));
    vi.stubGlobal("fetch", fetchMock);
    const store = useSessionsStore();
    await store.fetchAll();
    await store.create({
      name: "Alpha",
      media_type: "movie",
      rip_preset_id: "rpr_x",
      output_path_template: "{title}.{ext}",
    });
    expect(store.sessions.map((s) => s.name)).toEqual(["Alpha", "My Plex 1080p"]);
  });

  it("apply returns idempotent flag and tasks on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          session_application: applicationRow,
          tasks: [
            {
              id: "txt_1",
              session_application_id: "sap_1",
              source_track_id: "trk_1",
              status: "queued",
              output_path: "Iron Man.mkv",
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
    );
    const store = useSessionsStore();
    const resp = await store.apply("job_1", { session_id: "ses_x" });
    expect(resp.tasks.length).toBe(1);
    expect(resp.idempotent).toBe(false);
  });

  it("apply 409 surfaces collisions in ApiError.body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              message: "output_path collisions detected",
              collisions: [
                { output_path: "Iron Man.mkv", existing_task_id: "txt_other", on_filesystem: false },
              ],
            },
          },
          409,
        ),
      ),
    );
    const store = useSessionsStore();
    let thrown: ApiError | null = null;
    try {
      await store.apply("job_1", { session_id: "ses_x" });
    } catch (e) {
      if (e instanceof ApiError) thrown = e;
    }
    expect(thrown).not.toBeNull();
    expect(thrown!.status).toBe(409);
    const body = thrown!.body as { detail: { collisions: { output_path: string }[] } };
    expect(body.detail.collisions[0].output_path).toBe("Iron Man.mkv");
  });
});
