-- Dev seed: transcode tasks so the Transcoder page has visible jobs across all
-- four statuses (queued / in_progress / done / failed). Idempotent — fixed
-- seed IDs, ON CONFLICT DO UPDATE. Attaches to existing seeded movie tracks via
-- a session_application per job.
--
-- Run: docker compose exec -T arm-db psql -U arm -d arm -f - < devtools/seed-transcode-tasks.sql
--      (or: cat devtools/seed-transcode-tasks.sql | docker compose exec -T arm-db psql -U arm -d arm)

BEGIN;

-- One session_application per movie job (RUNNING) to satisfy the FK.
INSERT INTO session_applications (id, session_id, job_id, status, overwrite, created_at)
VALUES
  ('sap_seedtxmatrix0000000001', 'ses_builtin_movie_plex_1080p', 'job_01KVMDESHGR9W9SQ9E5CHMDR9E', 'running', false, now() - interval '40 minutes'),
  ('sap_seedtxoppenheimer00001', 'ses_builtin_movie_plex_2160p', 'job_01KVMDESHGR9W9SQ9E5CHMDR9H', 'running', false, now() - interval '25 minutes'),
  ('sap_seedtxcultdouble000001', 'ses_builtin_movie_archive',    'job_01KVMDESHGR9W9SQ9E5CHMDR9N', 'running', false, now() - interval '10 minutes')
ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status;

-- Transcode tasks across all four statuses.
INSERT INTO transcode_tasks
  (id, session_application_id, source_track_id, status, claimed_by, claim_heartbeat_at,
   attempts, output_path, progress_pct, last_error, created_at, updated_at)
VALUES
  -- DONE — finished main feature
  ('txt_seedmatrixfeature00001', 'sap_seedtxmatrix0000000001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9P',
   'done', 'transcoder-1', now() - interval '20 minutes',
   1, '/media/movies/The Matrix (1999)/The Matrix (1999) - h265.mkv', 100, NULL,
   now() - interval '40 minutes', now() - interval '20 minutes'),

  -- IN_PROGRESS — extra currently transcoding
  ('txt_seedmatrixbts00000001', 'sap_seedtxmatrix0000000001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9Q',
   'in_progress', 'transcoder-1', now() - interval '15 seconds',
   1, NULL, 62, NULL,
   now() - interval '18 minutes', now() - interval '15 seconds'),

  -- IN_PROGRESS — second worker on Oppenheimer main feature
  ('txt_seedoppenheimer0000001', 'sap_seedtxoppenheimer00001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9S',
   'in_progress', 'transcoder-2', now() - interval '5 seconds',
   1, NULL, 18, NULL,
   now() - interval '25 minutes', now() - interval '5 seconds'),

  -- QUEUED — Oppenheimer trailer waiting
  ('txt_seedoppentrailer000001', 'sap_seedtxoppenheimer00001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9T',
   'queued', NULL, NULL,
   0, NULL, 0, NULL,
   now() - interval '24 minutes', now() - interval '24 minutes'),

  -- QUEUED — Cult Double Feature first film waiting
  ('txt_seedcultphantasm00001', 'sap_seedtxcultdouble000001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9Y',
   'queued', NULL, NULL,
   0, NULL, 0, NULL,
   now() - interval '10 minutes', now() - interval '10 minutes'),

  -- FAILED — Cult Double Feature second film errored (retryable)
  ('txt_seedcultphantasm2_0001', 'sap_seedtxcultdouble000001', 'trk_01KVMDESHGR9W9SQ9E5CHMDR9Z',
   'failed', 'transcoder-2', now() - interval '6 minutes',
   2, NULL, 0, 'HandBrakeCLI exited 1: no title found at index 2 (source read error)',
   now() - interval '9 minutes', now() - interval '6 minutes')
ON CONFLICT (id) DO UPDATE SET
  status = EXCLUDED.status,
  claimed_by = EXCLUDED.claimed_by,
  claim_heartbeat_at = EXCLUDED.claim_heartbeat_at,
  attempts = EXCLUDED.attempts,
  output_path = EXCLUDED.output_path,
  progress_pct = EXCLUDED.progress_pct,
  last_error = EXCLUDED.last_error,
  updated_at = EXCLUDED.updated_at;

COMMIT;

SELECT status, count(*) FROM transcode_tasks GROUP BY status ORDER BY status;
