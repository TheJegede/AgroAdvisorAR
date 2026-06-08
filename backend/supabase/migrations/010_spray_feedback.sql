-- 010_spray_feedback.sql
-- Thumbs up/down + optional comment per spray record (F4 Phase 6).
-- Append-only history.

CREATE TABLE IF NOT EXISTS public.spray_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  record_id   uuid NOT NULL REFERENCES public.spray_records(id) ON DELETE CASCADE,
  farmer_id   uuid NOT NULL REFERENCES public.farmer_profiles(id) ON DELETE CASCADE,
  rating      smallint NOT NULL CHECK (rating IN (-1, 1)),
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS spray_feedback_record
  ON public.spray_feedback USING btree (record_id, created_at DESC);

CREATE INDEX IF NOT EXISTS spray_feedback_farmer_recent
  ON public.spray_feedback USING btree (farmer_id, created_at DESC);

ALTER TABLE public.spray_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "farmer_all_spray_feedback" ON public.spray_feedback;
CREATE POLICY "farmer_all_spray_feedback"
  ON public.spray_feedback FOR ALL
  USING (farmer_id = auth.uid())
  WITH CHECK (farmer_id = auth.uid());

DROP POLICY IF EXISTS "admin reads all spray feedback" ON public.spray_feedback;
CREATE POLICY "admin reads all spray feedback"
  ON public.spray_feedback FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );
