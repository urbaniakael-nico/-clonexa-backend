"""create company experience client panel builder

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def jsonb_default_object() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "company_branding",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("logo_palette_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("primary_color", sa.String(length=32), nullable=False, server_default=sa.text("'#ef233c'")),
        sa.Column("secondary_color", sa.String(length=32), nullable=False, server_default=sa.text("'#ff2bd6'")),
        sa.Column("background_color", sa.String(length=32), nullable=False, server_default=sa.text("'#050505'")),
        sa.Column("card_color", sa.String(length=32), nullable=False, server_default=sa.text("'#18181b'")),
        sa.Column("text_color", sa.String(length=32), nullable=False, server_default=sa.text("'#f8fafc'")),
        sa.Column("success_color", sa.String(length=32), nullable=False, server_default=sa.text("'#00ff88'")),
        sa.Column("button_color", sa.String(length=32), nullable=False, server_default=sa.text("'#ef233c'")),
        sa.Column("status_color", sa.String(length=32), nullable=False, server_default=sa.text("'#00ff88'")),
        sa.Column("theme_mode", sa.String(length=24), nullable=False, server_default=sa.text("'dark'")),
        sa.Column("industry_theme", sa.String(length=48), nullable=False, server_default=sa.text("'default'")),
        sa.Column("visual_preset", sa.String(length=80), nullable=False, server_default=sa.text("'clonexa_default'")),
        sa.Column("font_family", sa.String(length=120), nullable=True),
        sa.Column("custom_css_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", name="uq_company_branding_company_id"),
        sa.CheckConstraint(
            "industry_theme IN ('default','field','hospitality','retail','production')",
            name="ck_company_branding_industry_theme",
        ),
        sa.CheckConstraint(
            "visual_preset IN ('clonexa_default','field_ops_dark','hospitality_night_ops','retail_pastel_performance','production_neon')",
            name="ck_company_branding_visual_preset",
        ),
        sa.CheckConstraint("theme_mode IN ('dark','light')", name="ck_company_branding_theme_mode"),
    )
    op.create_index("ix_company_branding_company_id", "company_branding", ["company_id"])

    op.create_table(
        "company_localization",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("default_language", sa.String(length=8), nullable=False, server_default=sa.text("'es'")),
        sa.Column("enabled_languages", JSONB, nullable=False, server_default=sa.text("'[\"es\",\"en\",\"fr\"]'::jsonb")),
        sa.Column("labels_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", name="uq_company_localization_company_id"),
        sa.CheckConstraint("default_language IN ('es','en','fr')", name="ck_company_localization_default_language"),
    )
    op.create_index("ix_company_localization_company_id", "company_localization", ["company_id"])

    op.create_table(
        "company_crm_layout",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layout_name", sa.String(length=80), nullable=False, server_default=sa.text("'default'")),
        sa.Column("sidebar_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("topbar_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("density", sa.String(length=32), nullable=False, server_default=sa.text("'comfortable'")),
        sa.Column("home_view", sa.String(length=80), nullable=False, server_default=sa.text("'launchpad'")),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", name="uq_company_crm_layout_company_id"),
        sa.CheckConstraint("density IN ('compact','comfortable','spacious')", name="ck_company_crm_layout_density"),
    )
    op.create_index("ix_company_crm_layout_company_id", "company_crm_layout", ["company_id"])

    op.create_table(
        "company_crm_launchpad_cards",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("card_code", sa.String(length=120), nullable=False),
        sa.Column("title_key", sa.String(length=160), nullable=False),
        sa.Column("subtitle_key", sa.String(length=220), nullable=True),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("route_path", sa.String(length=240), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("size", sa.String(length=32), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("action_type", sa.String(length=40), nullable=False, server_default=sa.text("'navigate'")),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "card_code", name="uq_company_crm_launchpad_company_module_card"),
        sa.CheckConstraint("action_type IN ('navigate','modal','api','export','external')", name="ck_company_crm_launchpad_action_type"),
        sa.CheckConstraint("size IN ('small','medium','large','wide')", name="ck_company_crm_launchpad_size"),
    )
    op.create_index("ix_company_crm_launchpad_company_id", "company_crm_launchpad_cards", ["company_id"])
    op.create_index("ix_company_crm_launchpad_module_code", "company_crm_launchpad_cards", ["module_code"])

    op.create_table(
        "company_crm_widgets",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("widget_code", sa.String(length=120), nullable=False),
        sa.Column("title_key", sa.String(length=160), nullable=False),
        sa.Column("metric_source", sa.String(length=220), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("size", sa.String(length=32), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "widget_code", name="uq_company_crm_widgets_company_module_widget"),
        sa.CheckConstraint("size IN ('small','medium','large','wide')", name="ck_company_crm_widgets_size"),
    )
    op.create_index("ix_company_crm_widgets_company_id", "company_crm_widgets", ["company_id"])
    op.create_index("ix_company_crm_widgets_module_code", "company_crm_widgets", ["module_code"])

    op.create_table(
        "company_crm_sections",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("section_code", sa.String(length=120), nullable=False),
        sa.Column("title_key", sa.String(length=160), nullable=False),
        sa.Column("route_path", sa.String(length=240), nullable=True),
        sa.Column("section_type", sa.String(length=40), nullable=False, server_default=sa.text("'page'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "section_code", name="uq_company_crm_sections_company_module_section"),
        sa.CheckConstraint("section_type IN ('page','table','kanban','chart','form','report','config')", name="ck_company_crm_sections_type"),
    )
    op.create_index("ix_company_crm_sections_company_id", "company_crm_sections", ["company_id"])
    op.create_index("ix_company_crm_sections_module_code", "company_crm_sections", ["module_code"])

    op.create_table(
        "company_crm_actions",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("action_code", sa.String(length=120), nullable=False),
        sa.Column("title_key", sa.String(length=160), nullable=False),
        sa.Column("target", sa.String(length=240), nullable=True),
        sa.Column("action_type", sa.String(length=40), nullable=False, server_default=sa.text("'navigate'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "action_code", name="uq_company_crm_actions_company_module_action"),
        sa.CheckConstraint("action_type IN ('navigate','modal','api','export','external')", name="ck_company_crm_actions_type"),
    )
    op.create_index("ix_company_crm_actions_company_id", "company_crm_actions", ["company_id"])
    op.create_index("ix_company_crm_actions_module_code", "company_crm_actions", ["module_code"])

    op.create_table(
        "company_crm_field_configs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("entity_code", sa.String(length=120), nullable=False),
        sa.Column("field_code", sa.String(length=120), nullable=False),
        sa.Column("label_key", sa.String(length=160), nullable=False),
        sa.Column("field_type", sa.String(length=40), nullable=False, server_default=sa.text("'text'")),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("options_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("validation_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "entity_code", "field_code", name="uq_company_crm_field_configs_company_module_entity_field"),
        sa.CheckConstraint(
            "field_type IN ('text','number','money','select','boolean','date','datetime','phone','email','textarea')",
            name="ck_company_crm_field_configs_type",
        ),
    )
    op.create_index("ix_company_crm_field_configs_company_id", "company_crm_field_configs", ["company_id"])
    op.create_index("ix_company_crm_field_configs_module_code", "company_crm_field_configs", ["module_code"])

    op.create_table(
        "company_alert_rules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("condition_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("display_type", sa.String(length=40), nullable=False, server_default=sa.text("'toast'")),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default=sa.text("'info'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("message_key", sa.String(length=160), nullable=False),
        sa.Column("settings_json", JSONB, nullable=False, server_default=jsonb_default_object()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "module_code", "rule_code", name="uq_company_alert_rules_company_module_rule"),
        sa.CheckConstraint("display_type IN ('toast','modal','banner','badge','card_alert')", name="ck_company_alert_rules_display_type"),
        sa.CheckConstraint("severity IN ('info','success','warning','danger')", name="ck_company_alert_rules_severity"),
    )
    op.create_index("ix_company_alert_rules_company_id", "company_alert_rules", ["company_id"])
    op.create_index("ix_company_alert_rules_module_code", "company_alert_rules", ["module_code"])


def downgrade() -> None:
    op.drop_index("ix_company_alert_rules_module_code", table_name="company_alert_rules")
    op.drop_index("ix_company_alert_rules_company_id", table_name="company_alert_rules")
    op.drop_table("company_alert_rules")

    op.drop_index("ix_company_crm_field_configs_module_code", table_name="company_crm_field_configs")
    op.drop_index("ix_company_crm_field_configs_company_id", table_name="company_crm_field_configs")
    op.drop_table("company_crm_field_configs")

    op.drop_index("ix_company_crm_actions_module_code", table_name="company_crm_actions")
    op.drop_index("ix_company_crm_actions_company_id", table_name="company_crm_actions")
    op.drop_table("company_crm_actions")

    op.drop_index("ix_company_crm_sections_module_code", table_name="company_crm_sections")
    op.drop_index("ix_company_crm_sections_company_id", table_name="company_crm_sections")
    op.drop_table("company_crm_sections")

    op.drop_index("ix_company_crm_widgets_module_code", table_name="company_crm_widgets")
    op.drop_index("ix_company_crm_widgets_company_id", table_name="company_crm_widgets")
    op.drop_table("company_crm_widgets")

    op.drop_index("ix_company_crm_launchpad_module_code", table_name="company_crm_launchpad_cards")
    op.drop_index("ix_company_crm_launchpad_company_id", table_name="company_crm_launchpad_cards")
    op.drop_table("company_crm_launchpad_cards")

    op.drop_index("ix_company_crm_layout_company_id", table_name="company_crm_layout")
    op.drop_table("company_crm_layout")

    op.drop_index("ix_company_localization_company_id", table_name="company_localization")
    op.drop_table("company_localization")

    op.drop_index("ix_company_branding_company_id", table_name="company_branding")
    op.drop_table("company_branding")
