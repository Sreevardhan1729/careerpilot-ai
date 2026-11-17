"""Row Level Security, grants, updated_at triggers, immutability guards (docs/DATABASE_SCHEMA.md §5).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OWNED = [
    "agent_runs", "application_events", "applications", "approvals", "candidate_profile_facts",
    "candidate_profiles", "crawl_runs", "crawl_sources", "idempotency_keys", "job_evidence", "job_people",
    "job_skills", "job_source_records", "jobs", "llm_calls", "notifications", "oauth_connections", "outreach",
    "people", "people_evidence", "resume_chunks", "resume_matches", "resume_versions", "resumes", "search_configs",
]
SHARED = ["companies", "skills"]
SYSTEM_ONLY = ["scheduled_tasks", "oauth_states"]
UPDATED_AT = [
    "agent_runs", "applications", "approvals", "candidate_profile_facts", "candidate_profiles", "companies",
    "crawl_sources", "jobs", "oauth_connections", "outreach", "people", "resumes", "scheduled_tasks",
    "search_configs", "skills", "users",
]
ALL = OWNED + SHARED + SYSTEM_ONLY + ["users", "audit_events"]


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
        """
    )
    for t in UPDATED_AT:
        op.execute(f"CREATE TRIGGER trg_{t}_updated_at BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION public.set_updated_at()")

    # Original resume files are immutable (FR-RES-02): the stored file and its extracted text never change.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.guard_resume_version_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.storage_key IS DISTINCT FROM OLD.storage_key
             OR NEW.file_sha256 IS DISTINCT FROM OLD.file_sha256
             OR (OLD.extracted_text IS NOT NULL AND NEW.extracted_text IS DISTINCT FROM OLD.extracted_text)
             OR NEW.version_number IS DISTINCT FROM OLD.version_number
             OR NEW.resume_id IS DISTINCT FROM OLD.resume_id THEN
            RAISE EXCEPTION 'resume_versions file fields are immutable' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_resume_versions_immutable BEFORE UPDATE ON resume_versions "
        "FOR EACH ROW EXECUTE FUNCTION public.guard_resume_version_immutable()"
    )

    for t in ALL:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {t} FROM anon")
        # The backend login role (whoever runs migrations) keeps full access in system sessions even where
        # it does not have BYPASSRLS. Inside user sessions it has switched to `authenticated`, so this
        # policy does not apply there.
        op.execute(
            f"DO $$ BEGIN EXECUTE format('CREATE POLICY backend_system ON {t} FOR ALL TO %I USING (true) "
            f"WITH CHECK (true)', current_user); END $$"
        )

    for t in OWNED:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO authenticated")
        op.execute(
            f"CREATE POLICY owner_all ON {t} FOR ALL TO authenticated "
            f"USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
        )

    op.execute("GRANT SELECT, INSERT, UPDATE ON users TO authenticated")
    op.execute(
        "CREATE POLICY owner_all ON users FOR ALL TO authenticated USING (id = auth.uid()) WITH CHECK (id = auth.uid())"
    )

    for t in SHARED:
        op.execute(f"GRANT SELECT ON {t} TO authenticated")
        op.execute(f"CREATE POLICY read_all ON {t} FOR SELECT TO authenticated USING (true)")

    # Audit log: users may read and append their own rows; nobody (via the app roles) may change them.
    op.execute("GRANT SELECT, INSERT ON audit_events TO authenticated")
    op.execute("CREATE POLICY owner_read ON audit_events FOR SELECT TO authenticated USING (user_id = auth.uid())")
    op.execute(
        "CREATE POLICY owner_append ON audit_events FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid())"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.guard_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND NEW.user_id IS NULL AND OLD.user_id IS NOT NULL
             AND NEW.action = OLD.action AND NEW.created_at = OLD.created_at THEN
            RETURN NEW;  -- account deletion detaches rows (ON DELETE SET NULL)
          END IF;
          RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = 'insufficient_privilege';
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION public.guard_audit_append_only()"
    )
    # scheduled_tasks / oauth_states: no authenticated grants or policies (system sessions only).


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS public.guard_audit_append_only()")
    for t in ALL:
        for policy in ("backend_system", "owner_all", "read_all", "owner_read", "owner_append"):
            op.execute(f"DROP POLICY IF EXISTS {policy} ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER IF EXISTS trg_resume_versions_immutable ON resume_versions")
    op.execute("DROP FUNCTION IF EXISTS public.guard_resume_version_immutable()")
    for t in UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_updated_at ON {t}")
    op.execute("DROP FUNCTION IF EXISTS public.set_updated_at()")
