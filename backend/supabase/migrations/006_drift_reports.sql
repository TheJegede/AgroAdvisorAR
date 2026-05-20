-- 006_drift_reports.sql
-- Dicamba drift incident reports table for F4 drift documentation tool.
-- Created by F4 Task 1.

CREATE TABLE IF NOT EXISTS public.drift_reports (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id              uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  incident_date          date NOT NULL,
  county_fips            text NOT NULL,
  affected_crop          text,
  affected_acres         float,
  suspected_herbicide    text DEFAULT 'dicamba',
  wind_direction         text,
  wind_speed_mph         float,
  temp_at_time_f         float,
  symptoms_description   text,
  neighboring_applicator text,
  photos_attached        bool DEFAULT false,
  weather_json           jsonb,
  aspb_submitted         bool DEFAULT false,
  created_at             timestamptz DEFAULT now()
);

ALTER TABLE public.drift_reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "farmer sees own drift reports" ON drift_reports;
CREATE POLICY "farmer sees own drift reports"
  ON drift_reports FOR ALL
  USING (farmer_id = auth.uid());

DROP POLICY IF EXISTS "admin sees all drift reports" ON drift_reports;
CREATE POLICY "admin sees all drift reports"
  ON drift_reports FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );

CREATE INDEX IF NOT EXISTS drift_reports_farmer_recent
  ON public.drift_reports USING btree (farmer_id, created_at DESC);
