# CLONEXA 015B — Inventario Base

## Objetivo
Dejar funcional el módulo `/client → Inventario` sin mezclarlo con Materiales.

## Incluye
- `app/api/v1/endpoints/inventory.py`
- `app/api/v1/router.py`
- `app/web/client.js`

## Funcionalidad
Inventario tiene solo 3 opciones:
1. Crear material / producto
2. Modificar material con lupa / buscador
3. CSV

## Crear material / producto
Campos:
- Nombre / referencia
- Tamaño
- Color
- Cantidad inicial
- Stock mínimo para alerta

## Modificar material
Permite:
- Buscar material
- Modificar nombre / referencia
- Modificar tamaño
- Modificar color
- Ingresar cantidad como movimiento de entrada
- Configurar mínimo de alerta
- Deshabilitar material

## Regla protegida
El cliente NO edita `stock actual` directamente.
El stock actual se mueve por:
- cantidad inicial
- entradas manuales desde Inventario
- entregas desde Materiales en integración futura
- devoluciones desde Materiales en integración futura

## Pendiente siguiente
015C — Materiales conectado a Inventario:
- Bot consulta inventario activo
- Solo permite solicitar materiales existentes
- Entregar descuenta stock
- Devolver suma stock
