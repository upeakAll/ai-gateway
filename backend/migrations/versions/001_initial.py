"""Initial schema with all core tables.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""
    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("quota_total", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("quota_used", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("billing_mode", sa.String(50), nullable=False, server_default="prepaid"),
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("routing_strategy", sa.String(50), nullable=False, server_default="weighted_round_robin"),
        sa.Column("fixed_channel_id", sa.String(36), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_is_active", "tenants", ["is_active"])

    # Create channels table
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("api_key", sa.String(512), nullable=False),
        sa.Column("api_base", sa.String(512), nullable=True),
        sa.Column("api_version", sa.String(50), nullable=True),
        sa.Column("aws_region", sa.String(50), nullable=True),
        sa.Column("aws_access_key_id", sa.String(128), nullable=True),
        sa.Column("aws_secret_access_key", sa.String(128), nullable=True),
        sa.Column("weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("health_status", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("health_check_url", sa.String(512), nullable=True),
        sa.Column("last_health_check", sa.String(50), nullable=True),
        sa.Column("avg_response_time", sa.Float, nullable=True),
        sa.Column("success_rate", sa.Float, nullable=True),
        sa.Column("total_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("circuit_breaker_open", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("circuit_breaker_opened_at", sa.String(50), nullable=True),
        sa.Column("rpm_limit", sa.Integer, nullable=True),
        sa.Column("tpm_limit", sa.Integer, nullable=True),
        sa.Column("default_input_price", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("default_output_price", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_channels_name", "channels", ["name"])
    op.create_index("ix_channels_provider", "channels", ["provider"])
    op.create_index("ix_channels_tenant_id", "channels", ["tenant_id"])
    op.create_index("ix_channels_status", "channels", ["status"])

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("quota_total", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("quota_used", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("rpm_limit", sa.Integer, nullable=True),
        sa.Column("tpm_limit", sa.Integer, nullable=True),
        sa.Column("allowed_models", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("denied_models", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_key", "api_keys", ["key"], unique=True)
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_status", "api_keys", ["status"])

    # Create sub_keys table
    op.create_table(
        "sub_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_key_id", sa.String(36), sa.ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(68), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("quota_total", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("quota_used", sa.Numeric(precision=12, scale=4), nullable=False, server_default="0"),
        sa.Column("rpm_limit", sa.Integer, nullable=True),
        sa.Column("tpm_limit", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_sub_keys_parent_key_id", "sub_keys", ["parent_key_id"])
    op.create_index("ix_sub_keys_key", "sub_keys", ["key"], unique=True)
    op.create_index("ix_sub_keys_status", "sub_keys", ["status"])

    # Create model_configs table
    op.create_table(
        "model_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("real_model_name", sa.String(255), nullable=False),
        sa.Column("input_price", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0.001"),
        sa.Column("output_price", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0.002"),
        sa.Column("rpm_limit", sa.Integer, nullable=True),
        sa.Column("tpm_limit", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("supports_streaming", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("supports_functions", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("supports_vision", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("max_context_tokens", sa.Integer, nullable=True),
        sa.Column("max_output_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_model_configs_channel_id", "model_configs", ["channel_id"])
    op.create_index("ix_model_configs_model_name", "model_configs", ["model_name"])
    op.create_index("ix_model_configs_is_active", "model_configs", ["is_active"])

    # Create usage_logs table
    op.create_table(
        "usage_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_key_id", sa.String(36), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_id", sa.String(50), nullable=False, unique=True),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("real_model_name", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_cost", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0"),
        sa.Column("output_cost", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float, nullable=True),
        sa.Column("time_to_first_token_ms", sa.Float, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="success"),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("request_metadata", postgresql.JSONB, nullable=True),
        sa.Column("response_metadata", postgresql.JSONB, nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("is_streaming", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_usage_logs_created_at", "usage_logs", ["created_at"])
    op.create_index("ix_usage_logs_tenant_id", "usage_logs", ["tenant_id"])
    op.create_index("ix_usage_logs_api_key_id", "usage_logs", ["api_key_id"])
    op.create_index("ix_usage_logs_channel_id", "usage_logs", ["channel_id"])
    op.create_index("ix_usage_logs_request_id", "usage_logs", ["request_id"], unique=True)
    op.create_index("ix_usage_logs_model_name", "usage_logs", ["model_name"])
    op.create_index("ix_usage_logs_status", "usage_logs", ["status"])
    # Composite indexes
    op.create_index("ix_usage_logs_tenant_created", "usage_logs", ["tenant_id", "created_at"])
    op.create_index("ix_usage_logs_api_key_created", "usage_logs", ["api_key_id", "created_at"])
    op.create_index("ix_usage_logs_channel_created", "usage_logs", ["channel_id", "created_at"])
    op.create_index("ix_usage_logs_model_created", "usage_logs", ["model_name", "created_at"])
    op.create_index("ix_usage_logs_status_created", "usage_logs", ["status", "created_at"])

    # Create mcp_servers table
    op.create_table(
        "mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("server_type", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("transport", sa.String(50), nullable=False, server_default="sse"),
        sa.Column("openapi_url", sa.String(1024), nullable=True),
        sa.Column("openapi_spec", postgresql.JSONB, nullable=True),
        sa.Column("base_url", sa.String(1024), nullable=True),
        sa.Column("sse_url", sa.String(1024), nullable=True),
        sa.Column("http_url", sa.String(1024), nullable=True),
        sa.Column("auth_type", sa.String(50), nullable=True),
        sa.Column("auth_config", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_error_at", sa.String(50), nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column("protocol_version", sa.String(50), nullable=True),
        sa.Column("server_info", postgresql.JSONB, nullable=True),
        sa.Column("capabilities", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_mcp_servers_name", "mcp_servers", ["name"])
    op.create_index("ix_mcp_servers_tenant_id", "mcp_servers", ["tenant_id"])
    op.create_index("ix_mcp_servers_status", "mcp_servers", ["status"])
    op.create_index("ix_mcp_servers_is_active", "mcp_servers", ["is_active"])

    # Create mcp_tools table
    op.create_table(
        "mcp_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("server_id", sa.String(36), sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("input_schema", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("openapi_operation_id", sa.String(255), nullable=True),
        sa.Column("openapi_path", sa.String(512), nullable=True),
        sa.Column("openapi_method", sa.String(10), nullable=True),
        sa.Column("execution_config", postgresql.JSONB, nullable=True),
        sa.Column("required_permission", sa.String(100), nullable=True),
        sa.Column("allowed_roles", postgresql.JSONB, nullable=True),
        sa.Column("allowed_tenant_ids", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_dangerous", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_confirmation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("rate_limit_per_minute", sa.Integer, nullable=True),
        sa.Column("total_invocations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_invocations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_mcp_tools_server_id", "mcp_tools", ["server_id"])
    op.create_index("ix_mcp_tools_name", "mcp_tools", ["name"])
    op.create_index("ix_mcp_tools_status", "mcp_tools", ["status"])
    op.create_index("ix_mcp_tools_is_active", "mcp_tools", ["is_active"])

    # Create users table (for admin access)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_id", sa.String(255), nullable=True),
        sa.Column("last_login_at", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])

    # Create roles table
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("role_type", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("permissions", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    # Create permissions table
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_permissions_name", "permissions", ["name"], unique=True)
    op.create_index("ix_permissions_resource", "permissions", ["resource"])

    # Create user_roles table
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_index("ix_user_roles_tenant_id", "user_roles", ["tenant_id"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("user_roles")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("mcp_tools")
    op.drop_table("mcp_servers")
    op.drop_table("usage_logs")
    op.drop_table("model_configs")
    op.drop_table("sub_keys")
    op.drop_table("api_keys")
    op.drop_table("channels")
    op.drop_table("tenants")
