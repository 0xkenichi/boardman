-- Guard the two SideQuest feed RPCs against acting as another user.
--
-- public.fn_get_visible_quests(p_user_id) and public.get_ranked_quest_feed(
-- p_user_id, ...) are SECURITY DEFINER and executable by anon, and they trust
-- p_user_id: anyone holding the public anon key could read the feed exactly
-- as any user sees it, private quests included (verify_rls.sql, 2026-10-20).
-- This Supabase project is shared with SideQuest; Boardman does not call them.
--
-- The SideQuest client code is not in this repo, so the function bodies are
-- kept as they are: each original is renamed to <name>__impl (callable by the
-- service role only) and a wrapper with the same name, arguments and result
-- takes its place. The wrapper allows:
--   * p_user_id = the caller's own auth.uid()   (signed-in feed)
--   * p_user_id IS NULL                         (signed-out / public feed)
--   * the service role                          (server jobs)
-- and refuses anything else with 42501 (insufficient_privilege).
--
-- Checked against the live definitions (2026-10-20): both are read-only;
-- fn_get_visible_quests(NULL) returns only is_public quests, and
-- get_ranked_quest_feed(NULL) already raises 'User not found'. With another
-- user's id they leaked that user's private/friends-only quests and their
-- friend graph (friend_score), which the wrapper now refuses.
--
-- Idempotent: a function that already has an __impl twin is skipped.
-- Roll back: DROP FUNCTION <name>(args); ALTER FUNCTION <name>__impl(args) RENAME TO <name>;

DO $$
DECLARE
  target text;
  fn regprocedure;
  impl_name text;
  base_name text;
  args_def text;
  args_call text;
  result_def text;
  is_set boolean;
  body text;
BEGIN
  FOREACH target IN ARRAY ARRAY[
    'public.fn_get_visible_quests(uuid)',
    'public.get_ranked_quest_feed(uuid, double precision, double precision, double precision, text, integer, uuid)'
  ] LOOP
    fn := to_regprocedure(target);
    CONTINUE WHEN fn IS NULL;

    SELECT p.proname INTO base_name FROM pg_proc p WHERE p.oid = fn;
    impl_name := base_name || '__impl';
    CONTINUE WHEN EXISTS (
      SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'public' AND p.proname = impl_name
    );

    SELECT pg_get_function_arguments(p.oid),
           pg_get_function_result(p.oid),
           p.proretset,
           (SELECT string_agg('$' || i, ', ' ORDER BY i) FROM generate_series(1, p.pronargs) AS i)
      INTO args_def, result_def, is_set, args_call
      FROM pg_proc p WHERE p.oid = fn;

    EXECUTE format('ALTER FUNCTION %s RENAME TO %I', fn, impl_name);
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC, anon, authenticated',
                   impl_name, pg_get_function_identity_arguments(fn));
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO service_role',
                   impl_name, pg_get_function_identity_arguments(fn));

    body := format(
      $b$
      BEGIN
        IF p_user_id IS NOT NULL
           AND coalesce(auth.role(), '') <> 'service_role'
           AND p_user_id IS DISTINCT FROM auth.uid() THEN
          RAISE EXCEPTION 'not allowed to read another user''s feed' USING ERRCODE = '42501';
        END IF;
        %s
      END
      $b$,
      CASE WHEN is_set
           THEN format('RETURN QUERY SELECT * FROM public.%I(%s);', impl_name, args_call)
           ELSE format('RETURN public.%I(%s);', impl_name, args_call)
      END
    );

    EXECUTE format(
      'CREATE FUNCTION public.%I(%s) RETURNS %s LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS %L',
      base_name, args_def, result_def, body
    );
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC',
                   base_name, pg_get_function_identity_arguments(to_regprocedure(target)));
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO anon, authenticated, service_role',
                   base_name, pg_get_function_identity_arguments(to_regprocedure(target)));
  END LOOP;
END
$$;
