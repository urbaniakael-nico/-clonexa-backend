from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict  # Pydantic v2
except Exception:  # pragma: no cover
    ConfigDict = None


class ClonexaSchema(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(from_attributes=True)

JsonDict = dict[str, Any]

ALLOWED_LANGUAGES = {"es", "en", "fr"}


class CompanyBrandingUpdate(BaseModel):
    logo_url: str | None = None
    logo_palette_json: JsonDict | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    background_color: str | None = None
    card_color: str | None = None
    text_color: str | None = None
    success_color: str | None = None
    button_color: str | None = None
    status_color: str | None = None
    theme_mode: str | None = None
    industry_theme: str | None = None
    visual_preset: str | None = None
    font_family: str | None = None
    custom_css_json: JsonDict | None = None


class CompanyBrandingOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    logo_url: str | None = None
    logo_palette_json: JsonDict = Field(default_factory=dict)
    primary_color: str
    secondary_color: str
    background_color: str
    card_color: str
    text_color: str
    success_color: str
    button_color: str
    status_color: str
    theme_mode: str
    industry_theme: str
    visual_preset: str
    font_family: str | None = None
    custom_css_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyLocalizationUpdate(BaseModel):
    default_language: str | None = None
    enabled_languages: list[str] | None = None
    labels_json: JsonDict | None = None


class CompanyLocalizationOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    default_language: str
    enabled_languages: list[str] = Field(default_factory=list)
    labels_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmLayoutUpdate(BaseModel):
    layout_name: str | None = None
    sidebar_enabled: bool | None = None
    topbar_enabled: bool | None = None
    density: str | None = None
    home_view: str | None = None
    settings_json: JsonDict | None = None


class CompanyCrmLayoutOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    layout_name: str
    sidebar_enabled: bool
    topbar_enabled: bool
    density: str
    home_view: str
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmLaunchpadCardUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    card_code: str | None = None
    title_key: str | None = None
    subtitle_key: str | None = None
    icon: str | None = None
    route_path: str | None = None
    enabled: bool | None = None
    position: int | None = None
    size: str | None = None
    action_type: str | None = None
    settings_json: JsonDict | None = None


class CompanyCrmLaunchpadCardOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    card_code: str
    title_key: str
    subtitle_key: str | None = None
    icon: str | None = None
    route_path: str | None = None
    enabled: bool
    position: int
    size: str
    action_type: str
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmWidgetUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    widget_code: str | None = None
    title_key: str | None = None
    metric_source: str | None = None
    enabled: bool | None = None
    position: int | None = None
    size: str | None = None
    icon: str | None = None
    settings_json: JsonDict | None = None


class CompanyCrmWidgetOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    widget_code: str
    title_key: str
    metric_source: str | None = None
    enabled: bool
    position: int
    size: str
    icon: str | None = None
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmSectionUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    section_code: str | None = None
    title_key: str | None = None
    route_path: str | None = None
    section_type: str | None = None
    enabled: bool | None = None
    position: int | None = None
    icon: str | None = None
    settings_json: JsonDict | None = None


class CompanyCrmSectionOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    section_code: str
    title_key: str
    route_path: str | None = None
    section_type: str
    enabled: bool
    position: int
    icon: str | None = None
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmActionUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    action_code: str | None = None
    title_key: str | None = None
    target: str | None = None
    action_type: str | None = None
    enabled: bool | None = None
    position: int | None = None
    icon: str | None = None
    settings_json: JsonDict | None = None


class CompanyCrmActionOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    action_code: str
    title_key: str
    target: str | None = None
    action_type: str
    enabled: bool
    position: int
    icon: str | None = None
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyCrmFieldConfigUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    entity_code: str | None = None
    field_code: str | None = None
    label_key: str | None = None
    field_type: str | None = None
    required: bool | None = None
    enabled: bool | None = None
    position: int | None = None
    options_json: JsonDict | None = None
    validation_json: JsonDict | None = None
    settings_json: JsonDict | None = None


class CompanyCrmFieldConfigOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    entity_code: str
    field_code: str
    label_key: str
    field_type: str
    required: bool
    enabled: bool
    position: int
    options_json: JsonDict = Field(default_factory=dict)
    validation_json: JsonDict = Field(default_factory=dict)
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyAlertRuleUpdate(BaseModel):
    id: uuid.UUID | None = None
    module_code: str | None = None
    rule_code: str | None = None
    event_type: str | None = None
    condition_json: JsonDict | None = None
    display_type: str | None = None
    severity: str | None = None
    enabled: bool | None = None
    message_key: str | None = None
    settings_json: JsonDict | None = None


class CompanyAlertRuleOut(ClonexaSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    module_code: str
    rule_code: str
    event_type: str | None = None
    condition_json: JsonDict = Field(default_factory=dict)
    display_type: str
    severity: str
    enabled: bool
    message_key: str
    settings_json: JsonDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CompanyExperienceUpdate(BaseModel):
    branding: CompanyBrandingUpdate | None = None
    localization: CompanyLocalizationUpdate | None = None
    layout: CompanyCrmLayoutUpdate | None = None
    launchpad_cards: list[CompanyCrmLaunchpadCardUpdate] | None = None
    widgets: list[CompanyCrmWidgetUpdate] | None = None
    sections: list[CompanyCrmSectionUpdate] | None = None
    actions: list[CompanyCrmActionUpdate] | None = None
    field_configs: list[CompanyCrmFieldConfigUpdate] | None = None
    alert_rules: list[CompanyAlertRuleUpdate] | None = None


class CompanyExperienceOut(ClonexaSchema):
    branding: CompanyBrandingOut
    localization: CompanyLocalizationOut
    layout: CompanyCrmLayoutOut
    launchpad_cards: list[CompanyCrmLaunchpadCardOut]
    widgets: list[CompanyCrmWidgetOut]
    sections: list[CompanyCrmSectionOut]
    actions: list[CompanyCrmActionOut]
    field_configs: list[CompanyCrmFieldConfigOut]
    alert_rules: list[CompanyAlertRuleOut]
