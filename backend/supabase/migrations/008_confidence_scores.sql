-- backend/supabase/migrations/008_confidence_scores.sql
-- F2 Citation Guard v2: NLI-based claim verification confidence scores.
ALTER TABLE public.chat_messages
  ADD COLUMN IF NOT EXISTS confidence_score numeric(3,2) CHECK (confidence_score BETWEEN 0 AND 1),
  ADD COLUMN IF NOT EXISTS escalated bool NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS chat_messages_escalated
  ON public.chat_messages (escalated, created_at DESC);

CREATE INDEX IF NOT EXISTS chat_messages_confidence_score
  ON public.chat_messages (confidence_score DESC);

ALTER TABLE public.eval_runs
  ADD COLUMN IF NOT EXISTS answer_confidence_mean numeric(3,2) CHECK (answer_confidence_mean BETWEEN 0 AND 1);
