-- response_feedback: thumbs up/down + optional comment per assistant message.
-- Append-only history: re-rating creates a new row. Latest row wins in queries.
-- Admin human-eval queue joins this against chat_messages WHERE rating = -1.

CREATE TABLE IF NOT EXISTS public.response_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id  uuid NOT NULL REFERENCES public.chat_messages(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rating      smallint NOT NULL CHECK (rating IN (-1, 1)),
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS response_feedback_message
    ON public.response_feedback USING btree (message_id, created_at DESC);

CREATE INDEX IF NOT EXISTS response_feedback_user_recent
    ON public.response_feedback USING btree (user_id, created_at DESC);

-- Used by the admin human-eval queue to surface thumbs-down messages quickly.
CREATE INDEX IF NOT EXISTS response_feedback_negative
    ON public.response_feedback USING btree (created_at DESC)
    WHERE rating = -1;

ALTER TABLE public.response_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner_all_feedback"
    ON public.response_feedback FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
