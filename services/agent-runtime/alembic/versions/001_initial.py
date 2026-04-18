"""001_initial — create core public schema tables.

Revision ID: 001
Revises: —
Create Date: 2026-04-18

Tables created:
    public.companies
    public.roles
    public.agents
    public.tasks
    public.events
    public.approvals
    metrics.token_usage

Security:
    RLS (Row-Level Security) is enabled on companies, roles, agents, tasks,
    and approvals.  Each policy gates rows on app.current_company_id, which
    the application layer must set via SET LOCAL before executing queries.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── schemas ──────────────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS metrics")

    # ── companies ─────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="provisioning"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "slug", name="uq_companies_org_slug"),
    )
    op.create_index(
        "idx_companies_org_id",
        "companies",
        ["org_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── roles ──────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reports_to_role_id", sa.Text(), nullable=True),
        sa.Column(
            "permissions", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "tool_access", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("max_headcount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("headcount_type", sa.Text(), nullable=False, server_default="agent"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["reports_to_role_id"], ["roles.id"]),
        sa.UniqueConstraint("company_id", "slug", name="uq_roles_company_slug"),
    )

    # ── agents ─────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("role_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("keycloak_client_id", sa.Text(), nullable=True),
        sa.Column(
            "llm_config", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("system_prompt_ref", sa.Text(), nullable=True),
        sa.Column(
            "capabilities", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "tool_permissions", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("token_budget_daily", sa.Integer(), nullable=True),
        sa.Column("token_budget_monthly", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_active_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.UniqueConstraint("company_id", "slug", name="uq_agents_company_slug"),
        sa.UniqueConstraint("keycloak_client_id"),
    )
    op.create_index(
        "idx_agents_company_id",
        "agents",
        ["company_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_agents_status",
        "agents",
        ["status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── tasks ──────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("priority", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("assigned_type", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("parent_task_id", sa.Text(), nullable=True),
        sa.Column(
            "external_refs", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"]),
    )
    op.create_index(
        "idx_tasks_company_id",
        "tasks",
        ["company_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_tasks_assigned_to",
        "tasks",
        ["assigned_to", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── events ─────────────────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.Text(), nullable=True),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("source", sa.Text(), nullable=False, server_default="agent-runtime"),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_events_company_timestamp",
        "events",
        ["company_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_events_type",
        "events",
        ["type", sa.text("timestamp DESC")],
    )

    # ── metrics.token_usage ────────────────────────────────────────────────────
    op.create_table(
        "token_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        schema="metrics",
    )
    op.create_index(
        "idx_token_usage_org_time",
        "token_usage",
        ["org_id", sa.text("recorded_at DESC")],
        schema="metrics",
    )
    op.create_index(
        "idx_token_usage_agent_time",
        "token_usage",
        ["agent_id", sa.text("recorded_at DESC")],
        schema="metrics",
    )

    # ── approvals ──────────────────────────────────────────────────────────────
    # Stores human-in-the-loop approval requests raised by agents before they
    # execute sensitive actions.  Kept in the public schema so RLS applies.
    op.create_table(
        "approvals",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
    )
    op.create_index(
        "idx_approvals_company_status",
        "approvals",
        ["company_id", "status"],
    )
    op.create_index(
        "idx_approvals_agent_id",
        "approvals",
        ["agent_id"],
    )

    # ── Row-Level Security ─────────────────────────────────────────────────────
    # RLS ensures every query is automatically scoped to the caller's company.
    # The application layer sets app.current_company_id at connection time via
    # SET LOCAL so the policy predicate resolves to the correct tenant.
    #
    # companies: a row is visible only when its own id matches the session variable.
    # roles / agents / tasks / approvals: visible only when company_id matches.
    #
    # BYPASSRLS is granted to the migration superuser so Alembic itself is not
    # blocked; the application role must NOT have BYPASSRLS.
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON companies
        USING (id = current_setting('app.current_company_id', true)::text)
    """)

    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON roles
        USING (company_id = current_setting('app.current_company_id', true)::text)
    """)

    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON agents
        USING (company_id = current_setting('app.current_company_id', true)::text)
    """)

    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON tasks
        USING (company_id = current_setting('app.current_company_id', true)::text)
    """)

    op.execute("ALTER TABLE approvals ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY company_isolation ON approvals
        USING (company_id = current_setting('app.current_company_id', true)::text)
    """)


def downgrade() -> None:
    # ── Remove RLS policies before dropping tables ─────────────────────────────
    op.execute("DROP POLICY IF EXISTS company_isolation ON approvals")
    op.execute("ALTER TABLE approvals DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS company_isolation ON tasks")
    op.execute("ALTER TABLE tasks DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS company_isolation ON agents")
    op.execute("ALTER TABLE agents DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS company_isolation ON roles")
    op.execute("ALTER TABLE roles DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS company_isolation ON companies")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")

    op.drop_table("approvals")
    op.drop_table("token_usage", schema="metrics")
    op.execute("DROP SCHEMA IF EXISTS metrics CASCADE")
    op.drop_table("events")
    op.drop_table("tasks")
    op.drop_table("agents")
    op.drop_table("roles")
    op.drop_table("companies")
