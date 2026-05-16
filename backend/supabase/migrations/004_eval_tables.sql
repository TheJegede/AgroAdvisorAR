-- Eval infrastructure for admin dashboard + human-review queue.
-- Adds:
--   1. retrieved_chunks JSONB column on chat_messages (faithful evaluator view)
--   2. human_eval_scores table (extension agent 1-5 scoring, append-only history)
--   3. eval_runs table (automated retrieval metrics over time)

ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS retrieved_chunks jsonb;

CREATE TABLE IF NOT EXISTS public.human_eval_scores (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id      uuid NOT NULL REFERENCES public.chat_messages(id) ON DELETE CASCADE,
    evaluator_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    accuracy_score  smallint NOT NULL CHECK (accuracy_score BETWEEN 1 AND 5),
    correction      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS human_eval_scores_message
    ON public.human_eval_scores USING btree (message_id, created_at DESC);

CREATE INDEX IF NOT EXISTS human_eval_scores_evaluator_recent
    ON public.human_eval_scores USING btree (evaluator_id, created_at DESC);

-- RLS: evaluators can read their own scores; service-role bypasses for queue queries.
ALTER TABLE public.human_eval_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "evaluator_read_own_scores"
    ON public.human_eval_scores FOR SELECT
    USING (evaluator_id = auth.uid());

CREATE POLICY "evaluator_insert_own_scores"
    ON public.human_eval_scores FOR INSERT
    WITH CHECK (evaluator_id = auth.uid());

CREATE TABLE IF NOT EXISTS public.eval_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_at              timestamptz NOT NULL DEFAULT now(),
    mrr_at_5            numeric(4,3),
    ndcg_at_5           numeric(4,3),
    answer_correct_pct  numeric(4,1),
    total_items         integer,
    model_version       text,
    retrieval_status    text NOT NULL DEFAULT 'not_run'
        CHECK (retrieval_status IN ('not_run', 'ok', 'partial', 'failed')),
    answer_status       text NOT NULL DEFAULT 'not_run'
        CHECK (answer_status IN ('not_run', 'ok', 'partial', 'failed')),
    run_status          text NOT NULL DEFAULT 'not_run'
        CHECK (run_status IN ('not_run', 'ok', 'partial', 'failed')),
    error_message       text
);

ALTER TABLE public.eval_runs
    ADD COLUMN IF NOT EXISTS retrieval_status text NOT NULL DEFAULT 'not_run'
        CHECK (retrieval_status IN ('not_run', 'ok', 'partial', 'failed')),
    ADD COLUMN IF NOT EXISTS answer_status text NOT NULL DEFAULT 'not_run'
        CHECK (answer_status IN ('not_run', 'ok', 'partial', 'failed')),
    ADD COLUMN IF NOT EXISTS run_status text NOT NULL DEFAULT 'not_run'
        CHECK (run_status IN ('not_run', 'ok', 'partial', 'failed')),
    ADD COLUMN IF NOT EXISTS error_message text;

CREATE INDEX IF NOT EXISTS eval_runs_recent
    ON public.eval_runs USING btree (run_at DESC);

-- eval_runs is read by admin metrics dashboard; service-role inserts from CI.
ALTER TABLE public.eval_runs ENABLE ROW LEVEL SECURITY;
-- No policies: only service-role (which bypasses RLS) reads/writes. Locked down by default.

CREATE OR REPLACE FUNCTION public.get_admin_dashboard_metrics()
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
WITH totals AS (
    SELECT jsonb_build_object(
        'registered_users', (SELECT count(*) FROM farmer_profiles),
        'sessions', (SELECT count(*) FROM chat_sessions),
        'assistant_messages', (SELECT count(*) FROM chat_messages WHERE role = 'assistant'),
        'feedback_rows', (SELECT count(*) FROM response_feedback)
    ) AS payload
),
language_split AS (
    SELECT coalesce(jsonb_object_agg(language, count), '{}'::jsonb) AS payload
    FROM (
        SELECT trim(language) AS language, count(*)::int AS count
        FROM farmer_profiles
        GROUP BY trim(language)
    ) s
),
county_query_volume AS (
    SELECT coalesce(jsonb_agg(row_payload ORDER BY count DESC), '[]'::jsonb) AS payload
    FROM (
        SELECT jsonb_build_object(
            'county_fips', fp.county_fips,
            'county_name', fp.county_name,
            'count', count(*)::int
        ) AS row_payload,
        count(*)::int AS count
        FROM chat_messages cm
        JOIN farmer_profiles fp ON fp.id = cm.user_id
        WHERE cm.role = 'assistant'
        GROUP BY fp.county_fips, fp.county_name
        ORDER BY count(*) DESC
        LIMIT 20
    ) s
),
feedback_distribution AS (
    SELECT jsonb_build_object(
        'positive', count(*) FILTER (WHERE rating = 1)::int,
        'negative', count(*) FILTER (WHERE rating = -1)::int
    ) AS payload
    FROM response_feedback
),
human_eval_summary AS (
    SELECT jsonb_build_object(
        'score_count', count(*)::int,
        'mean_accuracy_score', round(avg(accuracy_score)::numeric, 2)
    ) AS payload
    FROM human_eval_scores
),
top_user_queries AS (
    SELECT coalesce(jsonb_agg(row_payload ORDER BY count DESC), '[]'::jsonb) AS payload
    FROM (
        SELECT jsonb_build_object('query', content, 'count', count(*)::int) AS row_payload,
               count(*)::int AS count
        FROM chat_messages
        WHERE role = 'user'
          AND content_type = 'text'
          AND btrim(content) <> ''
        GROUP BY content
        ORDER BY count(*) DESC
        LIMIT 20
    ) s
),
recent_eval_runs AS (
    SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY e.run_at DESC), '[]'::jsonb) AS payload
    FROM (
        SELECT *
        FROM eval_runs
        ORDER BY run_at DESC
        LIMIT 10
    ) e
)
SELECT jsonb_build_object(
    'totals', totals.payload,
    'language_split', language_split.payload,
    'county_query_volume', county_query_volume.payload,
    'feedback_distribution', feedback_distribution.payload,
    'human_eval_summary', human_eval_summary.payload,
    'top_user_queries', top_user_queries.payload,
    'recent_eval_runs', recent_eval_runs.payload
)
FROM totals, language_split, county_query_volume, feedback_distribution,
     human_eval_summary, top_user_queries, recent_eval_runs;
$$;
