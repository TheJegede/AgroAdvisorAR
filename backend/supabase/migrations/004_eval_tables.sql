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
    model_version       text
);

CREATE INDEX IF NOT EXISTS eval_runs_recent
    ON public.eval_runs USING btree (run_at DESC);

-- eval_runs is read by admin metrics dashboard; service-role inserts from CI.
ALTER TABLE public.eval_runs ENABLE ROW LEVEL SECURITY;
-- No policies: only service-role (which bypasses RLS) reads/writes. Locked down by default.
