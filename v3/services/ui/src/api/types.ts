// Hand-typed projections of the wire schemas that the UI actually reads.
// `openapi-typescript` writes ./generated.ts at build time; we re-export the
// few types the views care about so the rest of the codebase imports from one
// spot (and we can swap the source of truth later without touching call sites).

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  expires_at: string;
  password_must_change: boolean;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export type JobStatus =
  | "created"
  | "awaiting_user_id"
  | "identified"
  | "ripping"
  | "ripped"
  | "ripped_partial"
  | "abandoned"
  | "failed";

export type DiscType = "dvd" | "bluray" | "cd" | "data" | "unknown";

export interface JobView {
  id: string;
  drive_id: string;
  disc_type: DiscType;
  status: JobStatus;
  title: string | null;
  year: number | null;
  metadata_json: Record<string, unknown>;
}

export interface TrackView {
  id: string;
  job_id: string;
  kind: string;
  index: number;
  source_ref: string;
  status: string;
  output_path: string | null;
  size_bytes: number | null;
  duration_seconds: number | null;
  attempts: number;
  last_error: string | null;
}

export interface JobDetailView {
  job: JobView;
  tracks: TrackView[];
}

export interface DriveView {
  id: string;
  hostname: string;
  device_path: string;
  display_name: string | null;
  status: string;
  last_seen_at: string | null;
  default_session_id: string | null;
}

export interface SessionView {
  id: string;
  name: string;
  media_type: string;
  is_builtin: boolean;
  rip_preset_id: string;
  transcode_preset_id: string | null;
  output_path_template: string;
}

export interface ConfigView {
  tmdb_api_key: string | null;
  omdb_api_key: string | null;
  musicbrainz_user_agent: string | null;
  auto_transcode_on_idle: boolean;
  block_on_miss: boolean;
  default_retention_policy: string;
  notification_apprise_urls: string[];
  updated_by_user_id: string | null;
  updated_at: string | null;
}

export interface ConfigUpdateRequest {
  tmdb_api_key?: string | null;
  omdb_api_key?: string | null;
  musicbrainz_user_agent?: string | null;
  auto_transcode_on_idle?: boolean;
  block_on_miss?: boolean;
  default_retention_policy?: string;
  notification_apprise_urls?: string[];
}

export interface DiagnosticsServiceView {
  name: string;
  log_level: string;
}

export interface DiagnosticsResponse {
  services: DiagnosticsServiceView[];
  bug_report_zip_url: string | null;
}
