# PATCH MANIFEST — 015C-R8 MATERIALS OPERATION RULES

## Files
- app/api/v1/endpoints/materials.py
- app/web/client.js
- README_MATERIALS_OPERATION_RULES_015C_R8.md
- PATCH_MANIFEST.md

## DB changes applied safely by ensure_materials_storage()
ALTER TABLE IF NOT EXISTS:
- material_requests.consigned_at
- material_requests.archived_at
- material_requests.exported_at
- material_requests.closed_at
- material_requests.operation_notes
- material_order_units.consigned_at
- material_order_units.consigned_observation

No hard reset. No data delete.
