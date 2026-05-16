-- chat_sessions: one row per conversation thread
-- chat_messages: one row per user/assistant turn
-- Schema captured from live Supabase project on 2026-05-16.

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    preview         text NOT NULL DEFAULT '',
    message_count   integer NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_message_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_sessions_user_last
    ON public.chat_sessions USING btree (user_id, last_message_at DESC);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    uuid NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    user_id       uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role          text NOT NULL,
    content       text NOT NULL,
    content_type  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_session_order
    ON public.chat_messages USING btree (session_id, created_at);

-- RLS: owners read/write their own rows. Backend uses service-role key
-- which bypasses RLS, so services/session.py manually filters by user_id.
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner_all_sessions"
    ON public.chat_sessions FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "owner_all_messages"
    ON public.chat_messages FOR ALL
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());
