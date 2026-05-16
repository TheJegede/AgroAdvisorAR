-- farmer_profiles: one row per registered farmer
-- id references auth.users (managed by Supabase GoTrue)
CREATE TABLE IF NOT EXISTS public.farmer_profiles (
    id            uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name     text NOT NULL,
    county_fips   char(5) NOT NULL,
    county_name   text NOT NULL,
    primary_crops text[] NOT NULL DEFAULT '{}',
    language      char(2) NOT NULL DEFAULT 'en',
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_active   timestamptz NOT NULL DEFAULT now()
);

-- Row Level Security: farmers can only read/write their own row
ALTER TABLE public.farmer_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "farmer can read own profile"
    ON public.farmer_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "farmer can insert own profile"
    ON public.farmer_profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

CREATE POLICY "farmer can update own profile"
    ON public.farmer_profiles FOR UPDATE
    USING (auth.uid() = id);
