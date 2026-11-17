"""Supabase compatibility: extensions, roles, auth.uid() (created only if missing).

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gen_random_uuid() is built into PostgreSQL 13+; pgcrypto only if the server ships it.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pgcrypto') "
        "THEN CREATE EXTENSION IF NOT EXISTS pgcrypto; END IF; END $$"
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            CREATE ROLE authenticated NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            CREATE ROLE anon NOLOGIN;
          END IF;
        END $$;
        """
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute(
        """
        DO $$ BEGIN
          IF to_regprocedure('auth.uid()') IS NULL THEN
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
            $f$ SELECT nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'sub', '')::uuid $f$;
          END IF;
        END $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA auth TO authenticated")
    op.execute("GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated")
    op.execute("GRANT USAGE ON SCHEMA public TO authenticated")
    # Let the backend login role switch into `authenticated` per transaction (RLS enforcement).
    op.execute(
        """
        DO $$ BEGIN
          IF NOT pg_has_role(current_user, 'authenticated', 'MEMBER') THEN
            EXECUTE format('GRANT authenticated TO %I', current_user);
          END IF;
        END $$;
        """
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    op.execute("REVOKE ALL ON SCHEMA langgraph FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
