PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS batch_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'generate_only',
  state TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL,
  notes TEXT,
  watch_started_at TEXT,
  watch_finished_at TEXT,
  last_summary_json TEXT
);

CREATE TABLE IF NOT EXISTS briefing_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  crm_id TEXT NOT NULL,
  company_name TEXT NOT NULL,
  website_url TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT NOT NULL,
  campaign_segment TEXT,
  post_generation_action TEXT NOT NULL DEFAULT 'generate_only',
  force_regenerate INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued-for-briefing',
  job_id TEXT,
  remote_status TEXT,
  batch_id TEXT,
  last_polled_at TEXT,
  report_url TEXT,
  created_at TEXT NOT NULL,
  submitted_at TEXT,
  completed_at TEXT,
  pack_created_at TEXT,
  error_message TEXT,
  FOREIGN KEY (run_id) REFERENCES batch_runs(id) ON DELETE SET NULL,
  UNIQUE (crm_id, website_url, contact_email)
);

CREATE TABLE IF NOT EXISTS send_packs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  briefing_queue_id INTEGER NOT NULL,
  crm_id TEXT NOT NULL,
  company_name TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT NOT NULL,
  report_url TEXT NOT NULL,
  email_subject TEXT NOT NULL,
  email_body TEXT NOT NULL,
  campaign_segment TEXT,
  validation_status TEXT NOT NULL DEFAULT 'pending',
  validation_errors TEXT,
  signature_present INTEGER NOT NULL DEFAULT 0,
  delivery_status TEXT NOT NULL DEFAULT 'pending',
  provider_message_id TEXT,
  verification_notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft-pending-review',
  approved_at TEXT,
  scheduled_send_at TEXT,
  sent_at TEXT,
  error_message TEXT,
  FOREIGN KEY (briefing_queue_id) REFERENCES briefing_queue(id) ON DELETE CASCADE,
  UNIQUE (briefing_queue_id)
);

CREATE TABLE IF NOT EXISTS outbound_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  send_pack_id INTEGER NOT NULL,
  contact_email TEXT NOT NULL,
  email_subject TEXT NOT NULL,
  email_body TEXT NOT NULL,
  report_url TEXT NOT NULL,
  scheduled_send_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  provider_message_id TEXT,
  verification_notes TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  error_message TEXT,
  FOREIGN KEY (send_pack_id) REFERENCES send_packs(id) ON DELETE CASCADE,
  UNIQUE (send_pack_id)
);
