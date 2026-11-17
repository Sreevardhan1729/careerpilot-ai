"""Review fixes: deleted-user tombstones (I-10); resumes deletable after use in an application (I-11).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deleted_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute("ALTER TABLE deleted_users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE deleted_users FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON deleted_users FROM anon")
    op.execute("DO $$ BEGIN EXECUTE format('CREATE POLICY backend_system ON deleted_users FOR ALL TO %I USING (true) "
               "WITH CHECK (true)', current_user); END $$")
    op.drop_constraint("fk_applications_resume_version_id_resume_versions", "applications", type_="foreignkey")
    op.create_foreign_key("fk_applications_resume_version_id_resume_versions", "applications", "resume_versions",
                          ["resume_version_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_applications_resume_version_id_resume_versions", "applications", type_="foreignkey")
    op.create_foreign_key("fk_applications_resume_version_id_resume_versions", "applications", "resume_versions",
                          ["resume_version_id"], ["id"], ondelete="RESTRICT")
    op.drop_table("deleted_users")
