PATCH: 010A.1_WORKFORCE_PERSONAL_HISTORY_HOTFIX

INCLUDES:
- app/api/v1/endpoints/employees.py
- README_WORKFORCE_PERSONAL_HISTORY_010A1_HOTFIX.md

DOES NOT TOUCH:
- app/web/client.js
- app/web/client.css
- Admin V2
- Login
- Dockerfile
- docker-compose.yml
- Existing migrations

PURPOSE:
Make Personal History functional and prevent Internal Server Error.
