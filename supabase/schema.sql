-- ============================================================
-- LCC Bouldering Leaderboard — Supabase Schema
-- Run this in: SQL Editor → New Query
-- ============================================================

CREATE TABLE ascents (
  id          SERIAL PRIMARY KEY,
  username    TEXT NOT NULL,
  climb_id    TEXT NOT NULL,
  climb_name  TEXT NOT NULL,
  grade_label TEXT NOT NULL,
  boulder_url TEXT NOT NULL,
  sent_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(username, climb_id)
);

-- Open read/write — no login required
ALTER TABLE ascents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "open_select" ON ascents FOR SELECT USING (true);
CREATE POLICY "open_insert" ON ascents FOR INSERT WITH CHECK (true);
CREATE POLICY "open_delete" ON ascents FOR DELETE USING (true);
