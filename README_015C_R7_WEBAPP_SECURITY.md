# CLONEXA 015C-R7 — Web App Security + PUBLIC_BASE_URL

## Incluye
- PUBLIC_BASE_URL configurable para el botón Telegram Web App.
- Validación de `initData` de Telegram Web App en backend.
- Validación de empleado por Telegram ID.
- Validación de rol permitido: admin, admin_empresa, supervisor, inventario.
- Validación de módulos activos: materials + inventory.
- Bloqueo de creación de órdenes si el usuario no está autorizado.
- Confirmación por Telegram al crear orden MAT.
- No toca Inventario, Devoluciones, CRM, Nómina ni Admin V2.

## Variable recomendada
En `.env`:

```env
PUBLIC_BASE_URL=https://reported-papers-catalogue-vii.trycloudflare.com
```

Cuando tengas dominio:

```env
PUBLIC_BASE_URL=https://app.tudominio.com
```
