-- ============================================================
-- LCC Bouldering Leaderboard — Supabase Schema
-- Run this in your Supabase project: SQL Editor → New Query
-- ============================================================

-- 1. Profiles (one per user, stores the public username)
CREATE TABLE profiles (
  id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username    TEXT UNIQUE NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Ascents (one row per climb sent per user)
CREATE TABLE ascents (
  id          SERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  climb_id    TEXT NOT NULL,       -- e.g. "problem-cheese-whiz"
  climb_name  TEXT NOT NULL,
  grade_label TEXT NOT NULL,       -- e.g. "V4"
  boulder_url TEXT NOT NULL,       -- e.g. "boulders/5-mile-cheese-whiz-cheese-whiz.html"
  sent_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, climb_id)        -- no duplicate sends
);

-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE ascents  ENABLE ROW LEVEL SECURITY;

-- Profiles: readable by all, writable by owner
CREATE POLICY "profiles_select" ON profiles FOR SELECT USING (true);
CREATE POLICY "profiles_insert" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "profiles_update" ON profiles FOR UPDATE USING (auth.uid() = id);

-- Ascents: readable by all, insert/delete by owner only
CREATE POLICY "ascents_select" ON ascents FOR SELECT USING (true);
CREATE POLICY "ascents_insert" ON ascents FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "ascents_delete" ON ascents FOR DELETE USING (auth.uid() = user_id);

-- ============================================================
-- IMPORTANT: Disable email confirmation in Supabase Dashboard
-- Authentication → Providers → Email → disable "Confirm email"
-- ============================================================
