-- 009_spray_records.sql
-- Immutable dicamba spray-decision records (F4 Phase 4).
-- Append-only: no UPDATE/DELETE policy -> both denied for everyone.

CREATE TABLE IF NOT EXISTS public.spray_records (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id       uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  created_at      timestamptz DEFAULT now(),
  lat             double precision NOT NULL,
  lon             double precision NOT NULL,
  product         text NOT NULL,
  applied_at      timestamptz NOT NULL,
  overall_status  text NOT NULL,
  rule_version    text NOT NULL,
  gates           jsonb NOT NULL,
  attestation     jsonb NOT NULL,
  weather_json    jsonb
);

ALTER TABLE public.spray_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "farmer reads own spray records" ON spray_records;
CREATE POLICY "farmer reads own spray records"
  ON spray_records FOR SELECT
  USING (farmer_id = auth.uid());

DROP POLICY IF EXISTS "farmer inserts own spray records" ON spray_records;
CREATE POLICY "farmer inserts own spray records"
  ON spray_records FOR INSERT
  WITH CHECK (farmer_id = auth.uid());

DROP POLICY IF EXISTS "admin reads all spray records" ON spray_records;
CREATE POLICY "admin reads all spray records"
  ON spray_records FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );

CREATE INDEX IF NOT EXISTS spray_records_farmer_recent
  ON public.spray_records USING btree (farmer_id, created_at DESC);
