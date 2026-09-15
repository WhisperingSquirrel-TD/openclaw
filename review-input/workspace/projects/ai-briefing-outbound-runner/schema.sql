PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS briefing_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  crm_id TEXT NOT NULL,
  company_name TEXT NOT NULL,
  website_url TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT NOT NULL,
  campaign_segment TEXT,
  force_regenerate INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued-for-briefing',
  job_id TEXT,
  report_url TEXT,
  created_at TEXT NOT NULL,
  submitted_at TEXT,
  completed_at TEXT,
  pack_created_at TEXT,
  error_message TEXT,
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
  created_at TEXT NOT NULL,
  sent_at TEXT,
  error_message TEXT,
  FOREIGN KEY (send_pack_id) REFERENCES send_packs(id) ON DELETE CASCADE,
  UNIQUE (send_pack_id)
);
