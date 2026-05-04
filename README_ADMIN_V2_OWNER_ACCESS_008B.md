# CLONEXA Admin V2 Owner Access 008B

Micro-patch quirúrgico para Admin Console V2.

## Qué cambia

- Cambia el concepto visual de `Usuarios` a `Acceso Maestro`.
- Admin V2 solo muestra y gestiona el usuario dueño/encargado de cada empresa.
- Selecciona el usuario maestro con esta prioridad:
  1. `role = company_admin`
  2. primer usuario activo como fallback visual
- Si hay varios `company_admin`, muestra advertencia.
- Si no existe acceso maestro, muestra formulario `Crear acceso maestro`.
- Regenera clave usando el endpoint existente.
- Permite copiar email y clave temporal.
- Desbloquea y activa/desactiva acceso si el endpoint responde.
- No modifica backend, migraciones, CSS, client, login ni Field Engine.

## Aplicar

```powershell
cd C:\Users\valef\OneDrive\Desktop\CLONEXA\clonexa_backend
unzip clonexa_admin_v2_owner_access_008b.zip -d .
docker compose -p clonexa down
docker compose -p clonexa up --build -d
```

## Validar

Abrir:

```text
http://localhost:8000/admin-v2
```

Revisar:

- Sidebar: `Acceso Maestro`.
- Empresa Voltage: muestra `admin@voltage.com`.
- Texto visible: el personal operativo se gestiona desde el panel de la empresa.
- Botón `Regenerar clave`.
- Botón `Desbloquear acceso`.
- Botón copiar email y copiar clave.
- No hay cambios en `/client`, `/login` ni `/admin`.
