-- backend/supabase/migrations/005_alerts.sql
CREATE TABLE IF NOT EXISTS public.alerts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id    uuid NOT NULL REFERENCES public.farmer_profiles(id) ON DELETE CASCADE,
  pest         text NOT NULL,
  county_fips  text NOT NULL,
  gdd_value    float,
  message_en   text,
  message_es   text,
  fired_at     timestamptz DEFAULT now(),
  dismissed_at timestamptz
);

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "farmer sees own alerts" ON public.alerts
  FOR SELECT USING (farmer_id = auth.uid());

CREATE POLICY "farmer dismisses own alerts" ON public.alerts
  FOR UPDATE USING (farmer_id = auth.uid())
  WITH CHECK (farmer_id = auth.uid());

CREATE INDEX IF NOT EXISTS alerts_farmer_active
  ON public.alerts (farmer_id, dismissed_at, fired_at DESC);
