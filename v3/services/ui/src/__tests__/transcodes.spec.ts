import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useTranscodesStore } from "../stores/transcodes";
import { wsClient, type WSEnvelope } from "../api/ws";
import type { TranscodeTaskView } from "../api/types";

function task(id: string, status: TranscodeTaskView["status"], progress = 0): TranscodeTaskView {
  return {
    id,
    session_application_id: "sap_1",
    source_track_id: `trk_${id}`,
    status,
    output_path: "Iron Man.mkv",
    progress_pct: progress,
    attempts: status === "queued" ? 0 : 1,
    claimed_by: status === "in_progress" ? "arm-transcode-host" : null,
    claim_heartbeat_at: null,
    last_error: null,
    created_at: null,
    updated_at: null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("transcodes store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.setItem("arm_token", "aaa.bbb.ccc");
  });

  afterEach(() => {
    wsClient.stop();
    vi.restoreAllMocks();
  });

  it("fetchAll loads tasks", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([task("txt_1", "in_progress", 25)])));
    const store = useTranscodesStore();
    await store.fetchAll();
    expect(store.tasks.length).toBe(1);
    expect(store.tasks[0].progress_pct).toBe(25);
  });

  it("WS progress updates liveProgress without mutating tasks list", () => {
    const store = useTranscodesStore();
    store.tasks = [task("txt_1", "in_progress", 10)];
    const env: WSEnvelope = {
      op: "event",
      event_id: "evt_1",
      event_type: "transcode.progress",
      emitted_at: "now",
      topic: "transcode.progress.txt_1",
      job_id: null,
      track_id: "txt_1",
      payload: { task_id: "txt_1", progress_pct: 73, eta_seconds: 120, current_pass: "main" },
    };
    store.onProgress(env);
    expect(store.liveProgress["txt_1"].progress_pct).toBe(73);
    expect(store.tasks[0].progress_pct).toBe(10); // raw row untouched
  });

  it("task.completed event flips status to done and sets progress to 100", () => {
    const store = useTranscodesStore();
    store.tasks = [task("txt_1", "in_progress", 50)];
    const env: WSEnvelope = {
      op: "event",
      event_id: "evt_1",
      event_type: "task.completed",
      emitted_at: "now",
      topic: "transcode.events",
      job_id: "job_1",
      track_id: "trk_1",
      payload: {
        task_id: "txt_1",
        session_application_id: "sap_1",
        output_path: "Iron Man.mkv",
      },
    };
    store.onEvent(env);
    expect(store.tasks[0].status).toBe("done");
    expect(store.tasks[0].progress_pct).toBe(100);
  });

  it("task.failed event flips status and copies last_error", () => {
    const store = useTranscodesStore();
    store.tasks = [task("txt_1", "in_progress", 30)];
    const env: WSEnvelope = {
      op: "event",
      event_id: "evt_1",
      event_type: "task.failed",
      emitted_at: "now",
      topic: "transcode.events",
      job_id: "job_1",
      track_id: "trk_1",
      payload: {
        task_id: "txt_1",
        session_application_id: "sap_1",
        last_error: "HandBrakeCLI exited rc=1",
      },
    };
    store.onEvent(env);
    expect(store.tasks[0].status).toBe("failed");
    expect(store.tasks[0].last_error).toBe("HandBrakeCLI exited rc=1");
  });

  it("cancel on a queued task marks it failed without DELETE round-trip wiping the row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    const store = useTranscodesStore();
    store.tasks = [task("txt_q", "queued")];
    await store.cancel("txt_q");
    expect(store.tasks[0].status).toBe("failed");
    expect(store.tasks[0].last_error).toBe("cancelled by user");
  });
});
