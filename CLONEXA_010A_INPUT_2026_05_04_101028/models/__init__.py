from app.models.base import Base

try:
    from app.models.core import Company
except Exception:
    Company = None

try:
    from app.models.auth import CompanyUser
except Exception:
    CompanyUser = None

try:
    from app.models.saas import (
        CompanyModule,
        CompanyPackageAssignment,
        Module,
        Package,
        PackageModule,
    )
except Exception:
    CompanyModule = CompanyPackageAssignment = Module = Package = PackageModule = None

try:
    from app.models.experience import (
        CompanyAlertRule,
        CompanyBranding,
        CompanyCrmAction,
        CompanyCrmFieldConfig,
        CompanyCrmLaunchpadCard,
        CompanyCrmLayout,
        CompanyCrmSection,
        CompanyCrmWidget,
        CompanyLocalization,
    )
except Exception:
    CompanyAlertRule = CompanyBranding = CompanyCrmAction = CompanyCrmFieldConfig = None
    CompanyCrmLaunchpadCard = CompanyCrmLayout = CompanyCrmSection = CompanyCrmWidget = None
    CompanyLocalization = None

from app.models.field import (
    FieldBillingProject,
    FieldMaterial,
    FieldMaterialMovement,
    FieldMaterialRequest,
    FieldMaterialRequestItem,
    FieldTechnician,
    FieldTechnicianMaterialStock,
)

__all__ = [
    "Base",
    "Company",
    "CompanyUser",
    "Module",
    "Package",
    "PackageModule",
    "CompanyModule",
    "CompanyPackageAssignment",
    "CompanyBranding",
    "CompanyLocalization",
    "CompanyCrmLayout",
    "CompanyCrmLaunchpadCard",
    "CompanyCrmWidget",
    "CompanyCrmSection",
    "CompanyCrmAction",
    "CompanyCrmFieldConfig",
    "CompanyAlertRule",
    "FieldBillingProject",
    "FieldTechnician",
    "FieldMaterial",
    "FieldTechnicianMaterialStock",
    "FieldMaterialRequest",
    "FieldMaterialRequestItem",
    "FieldMaterialMovement",
]
