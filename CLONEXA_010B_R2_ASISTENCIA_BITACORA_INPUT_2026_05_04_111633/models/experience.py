from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExperienceTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CompanyBranding(Base, ExperienceTimestampMixin):
    __tablename__ = "company_branding"
    __table_args__ = (UniqueConstraint("company_id", name="uq_company_branding_company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_palette_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    primary_color: Mapped[str] = mapped_column(String(32), default="#ef233c", server_default="#ef233c", nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(32), default="#ff2bd6", server_default="#ff2bd6", nullable=False)
    background_color: Mapped[str] = mapped_column(String(32), default="#050505", server_default="#050505", nullable=False)
    card_color: Mapped[str] = mapped_column(String(32), default="#18181b", server_default="#18181b", nullable=False)
    text_color: Mapped[str] = mapped_column(String(32), default="#f8fafc", server_default="#f8fafc", nullable=False)
    success_color: Mapped[str] = mapped_column(String(32), default="#00ff88", server_default="#00ff88", nullable=False)
    button_color: Mapped[str] = mapped_column(String(32), default="#ef233c", server_default="#ef233c", nullable=False)
    status_color: Mapped[str] = mapped_column(String(32), default="#00ff88", server_default="#00ff88", nullable=False)
    theme_mode: Mapped[str] = mapped_column(String(24), default="dark", server_default="dark", nullable=False)
    industry_theme: Mapped[str] = mapped_column(String(48), default="default", server_default="default", nullable=False)
    visual_preset: Mapped[str] = mapped_column(String(80), default="clonexa_default", server_default="clonexa_default", nullable=False)
    font_family: Mapped[str | None] = mapped_column(String(120), nullable=True)
    custom_css_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyLocalization(Base, ExperienceTimestampMixin):
    __tablename__ = "company_localization"
    __table_args__ = (UniqueConstraint("company_id", name="uq_company_localization_company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    default_language: Mapped[str] = mapped_column(String(8), default="es", server_default="es", nullable=False)
    enabled_languages: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["es", "en", "fr"],
        server_default=text("'[\"es\",\"en\",\"fr\"]'::jsonb"),
        nullable=False,
    )
    labels_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmLayout(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_layout"
    __table_args__ = (UniqueConstraint("company_id", name="uq_company_crm_layout_company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    layout_name: Mapped[str] = mapped_column(String(80), default="default", server_default="default", nullable=False)
    sidebar_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    topbar_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    density: Mapped[str] = mapped_column(String(32), default="comfortable", server_default="comfortable", nullable=False)
    home_view: Mapped[str] = mapped_column(String(80), default="launchpad", server_default="launchpad", nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmLaunchpadCard(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_launchpad_cards"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "card_code", name="uq_company_crm_launchpad_company_module_card"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    card_code: Mapped[str] = mapped_column(String(120), nullable=False)
    title_key: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle_key: Mapped[str | None] = mapped_column(String(220), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    route_path: Mapped[str | None] = mapped_column(String(240), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    size: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium", nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), default="navigate", server_default="navigate", nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmWidget(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_widgets"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "widget_code", name="uq_company_crm_widgets_company_module_widget"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    widget_code: Mapped[str] = mapped_column(String(120), nullable=False)
    title_key: Mapped[str] = mapped_column(String(160), nullable=False)
    metric_source: Mapped[str | None] = mapped_column(String(220), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    size: Mapped[str] = mapped_column(String(32), default="medium", server_default="medium", nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmSection(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_sections"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "section_code", name="uq_company_crm_sections_company_module_section"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    section_code: Mapped[str] = mapped_column(String(120), nullable=False)
    title_key: Mapped[str] = mapped_column(String(160), nullable=False)
    route_path: Mapped[str | None] = mapped_column(String(240), nullable=True)
    section_type: Mapped[str] = mapped_column(String(40), default="page", server_default="page", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmAction(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_actions"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "action_code", name="uq_company_crm_actions_company_module_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action_code: Mapped[str] = mapped_column(String(120), nullable=False)
    title_key: Mapped[str] = mapped_column(String(160), nullable=False)
    target: Mapped[str | None] = mapped_column(String(240), nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), default="navigate", server_default="navigate", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyCrmFieldConfig(Base, ExperienceTimestampMixin):
    __tablename__ = "company_crm_field_configs"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "entity_code", "field_code", name="uq_company_crm_field_configs_company_module_entity_field"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_code: Mapped[str] = mapped_column(String(120), nullable=False)
    field_code: Mapped[str] = mapped_column(String(120), nullable=False)
    label_key: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[str] = mapped_column(String(40), default="text", server_default="text", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    options_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)


class CompanyAlertRule(Base, ExperienceTimestampMixin):
    __tablename__ = "company_alert_rules"
    __table_args__ = (
        UniqueConstraint("company_id", "module_code", "rule_code", name="uq_company_alert_rules_company_module_rule"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    display_type: Mapped[str] = mapped_column(String(40), default="toast", server_default="toast", nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="info", server_default="info", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    message_key: Mapped[str] = mapped_column(String(160), nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
