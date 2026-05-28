-- Migration 007: Add rice_fields column to farmer_profiles
ALTER TABLE farmer_profiles
  ADD COLUMN IF NOT EXISTS rice_fields jsonb NOT NULL DEFAULT '[]'::jsonb;
