-- CF Pipelines SQL transform for VOLY TaskEvent telemetry
-- Configure in wrangler pipelines / Cloudflare dashboard.
-- Source stream: JSON array batches from emit_event() → send_to_pipeline()

INSERT INTO telemetry
SELECT
  task_id,
  agent,
  status,
  model,
  provider,
  executor,
  task_type,
  tokens_input,
  tokens_output,
  tokens_saved_rtk,
  tokens_saved_headroom,
  cost_usd,
  duration_ms,
  routing_score,
  automation_score,
  manual_steps_removed,
  cache_hit,
  fallback_used,
  dlp_blocked,
  to_timestamp_micros(ts_us) AS event_time
FROM telemetry_json
WHERE status IS NOT NULL
