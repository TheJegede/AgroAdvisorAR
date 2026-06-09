-- 011_spray_feedback_append_only_rls.sql
-- Farmers may read and append feedback for their own spray records.
-- They may not update or delete prior feedback rows.

ALTER TABLE public.spray_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "farmer_all_spray_feedback" ON public.spray_feedback;
DROP POLICY IF EXISTS "farmer reads own spray feedback" ON public.spray_feedback;
CREATE POLICY "farmer reads own spray feedback"
  ON public.spray_feedback FOR SELECT
  USING (farmer_id = auth.uid());

DROP POLICY IF EXISTS "farmer inserts own spray feedback" ON public.spray_feedback;
CREATE POLICY "farmer inserts own spray feedback"
  ON public.spray_feedback FOR INSERT
  WITH CHECK (farmer_id = auth.uid());

DROP POLICY IF EXISTS "admin reads all spray feedback" ON public.spray_feedback;
CREATE POLICY "admin reads all spray feedback"
  ON public.spray_feedback FOR SELECT
  USING (
    auth.uid()::text = ANY(
      string_to_array(current_setting('app.admin_user_ids', true), ',')
    )
  );
