-- backend/supabase/migrations/005_alerts.sql
CREATE TABLE alerts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farmer_id    uuid REFERENCES farmer_profiles(id) ON DELETE CASCADE,
  pest         text NOT NULL,
  county_fips  text NOT NULL,
  gdd_value    float,
  message_en   text,
  message_es   text,
  fired_at     timestamptz DEFAULT now(),
  dismissed_at timestamptz
);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "farmer sees own alerts" ON alerts
  FOR SELECT USING (farmer_id = auth.uid());
