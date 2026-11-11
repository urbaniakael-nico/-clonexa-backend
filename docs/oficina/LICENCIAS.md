# Oficina 3D · licencias de los recursos

Todo lo que sirve el piso realista sale de fuentes con licencia clara que permite uso comercial dentro de un producto que se vende.
Los archivos se sirven solo dentro de la app (con sesión de Admin V2), nunca sueltos ni por CDN.

Se genera con `ops/oficina/preparar_recursos.py`; la prueba `tests/test_oficina_real.py` verifica que cada archivo de
`app/web/oficina/recursos/` aparece aquí.

| Archivo | Recurso | Fuente | Autor | Licencia | Enlace |
|---|---|---|---|---|---|
| `hdri/warm_bar_1k.hdr` | Warm Bar | Poly Haven | Greg Zaal, Jarod Guest | CC0 1.0 | https://polyhaven.com/a/warm_bar |
| `modelos/barril.glb` | Wine Barrel 01 | Poly Haven | James Ray Cock | CC0 1.0 | https://polyhaven.com/a/wine_barrel_01 |
| `modelos/botellas.glb` | Wine Bottles 01 | Poly Haven | Jurita Burger, Rico Cilliers | CC0 1.0 | https://polyhaven.com/a/wine_bottles_01 |
| `modelos/caja.glb` | Cash Register 01 | Poly Haven | Joe Seabuhr | CC0 1.0 | https://polyhaven.com/a/CashRegister_01 |
| `modelos/lampara.glb` | Hanging Industrial Lamp | Poly Haven | Kuutti Siitonen | CC0 1.0 | https://polyhaven.com/a/hanging_industrial_lamp |
| `modelos/mesa.glb` | Round Wooden Table 01 | Poly Haven | Ulan Cabanilla | CC0 1.0 | https://polyhaven.com/a/round_wooden_table_01 |
| `modelos/planta.glb` | Potted Plant 04 | Poly Haven | James Ray Cock | CC0 1.0 | https://polyhaven.com/a/potted_plant_04 |
| `modelos/silla.glb` | Gallinera Chair | Poly Haven | Ulan Cabanilla | CC0 1.0 | https://polyhaven.com/a/gallinera_chair |
| `modelos/sofa.glb` | Sofa 01 | Poly Haven | Kirill Sannikov | CC0 1.0 | https://polyhaven.com/a/Sofa_01 |
| `modelos/taburete.glb` | Bar Chair Round 01 | Poly Haven | Dairon Sanchez | CC0 1.0 | https://polyhaven.com/a/bar_chair_round_01 |
| `texturas/concreto_arm.webp` | Concrete Floor 02 | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/concrete_floor_02 |
| `texturas/concreto_diff.webp` | Concrete Floor 02 | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/concrete_floor_02 |
| `texturas/concreto_nor_gl.webp` | Concrete Floor 02 | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/concrete_floor_02 |
| `texturas/cuero_arm.webp` | Leather Red 02 | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/leather_red_02 |
| `texturas/cuero_nor_gl.webp` | Leather Red 02 | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/leather_red_02 |
| `texturas/madera_arm.webp` | Wood Table 001 | Poly Haven | Dimitrios Savva, Rico Cilliers | CC0 1.0 | https://polyhaven.com/a/wood_table_001 |
| `texturas/madera_diff.webp` | Wood Table 001 | Poly Haven | Dimitrios Savva, Rico Cilliers | CC0 1.0 | https://polyhaven.com/a/wood_table_001 |
| `texturas/madera_nor_gl.webp` | Wood Table 001 | Poly Haven | Dimitrios Savva, Rico Cilliers | CC0 1.0 | https://polyhaven.com/a/wood_table_001 |
| `texturas/metal_arm.webp` | Metal Plate | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/metal_plate |
| `texturas/metal_diff.webp` | Metal Plate | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/metal_plate |
| `texturas/metal_nor_gl.webp` | Metal Plate | Poly Haven | Rob Tuytel | CC0 1.0 | https://polyhaven.com/a/metal_plate |
| `texturas/pared_arm.webp` | Dark Brick Wall | Poly Haven | Dario Barresi, Dimitrios Savva | CC0 1.0 | https://polyhaven.com/a/dark_brick_wall |
| `texturas/pared_diff.webp` | Dark Brick Wall | Poly Haven | Dario Barresi, Dimitrios Savva | CC0 1.0 | https://polyhaven.com/a/dark_brick_wall |
| `texturas/pared_nor_gl.webp` | Dark Brick Wall | Poly Haven | Dario Barresi, Dimitrios Savva | CC0 1.0 | https://polyhaven.com/a/dark_brick_wall |
| `texturas/piso_arm.webp` | Herringbone Parquet | Poly Haven | Jenelle van Heerden, Sergej Majboroda | CC0 1.0 | https://polyhaven.com/a/herringbone_parquet |
| `texturas/piso_diff.webp` | Herringbone Parquet | Poly Haven | Jenelle van Heerden, Sergej Majboroda | CC0 1.0 | https://polyhaven.com/a/herringbone_parquet |
| `texturas/piso_nor_gl.webp` | Herringbone Parquet | Poly Haven | Jenelle van Heerden, Sergej Majboroda | CC0 1.0 | https://polyhaven.com/a/herringbone_parquet |
| `texturas/tela_arm.webp` | Velour Velvet | Poly Haven | Rico Cilliers, colormass | CC0 1.0 | https://polyhaven.com/a/velour_velvet |
| `texturas/tela_diff.webp` | Velour Velvet | Poly Haven | Rico Cilliers, colormass | CC0 1.0 | https://polyhaven.com/a/velour_velvet |
| `texturas/tela_nor_gl.webp` | Velour Velvet | Poly Haven | Rico Cilliers, colormass | CC0 1.0 | https://polyhaven.com/a/velour_velvet |

## Código

| Archivo | Fuente | Licencia |
|---|---|---|
| `app/web/vendor/three-0.160.0/**` (incluye postprocessing, RGBELoader, meshopt_decoder) | three.js r160 · https://github.com/mrdoob/three.js | MIT (ver LICENSE en la carpeta) |

## Personajes del bar aprobado (The Time Machine): Mixamo

| Recurso | Fuente | Licencia | Dónde viven |
|---|---|---|---|
| Personajes Remy, Ch01, Ch06, Ch07, Ch17, Ch21, Ch22, Ch42 (`personajes/*.glb`) | Mixamo (Adobe) · https://www.mixamo.com | Uso permitido dentro del producto (comercial incluido). **No redistribuible**: prohibido publicar o compartir los archivos sueltos. | Bucket privado de Clonexa (`oficina/bar/v1/`) |
| 13 animaciones solo movimiento (`animaciones/*.glb`: Bartending, Walking, Waving, Sitting…, Rumba_Dancing, Silly_Dancing, Talking, Drinking, Idle) | Mixamo (Adobe) | Igual: uso dentro del producto, no redistribuible. | Bucket privado de Clonexa (`oficina/bar/v1/`) |

Reglas:
- **Nunca en el repositorio** (es público). `.gitignore` excluye `clonexa-assets/`, `*.fbx` y los nombres de Mixamo, y
  `tests/test_oficina_bar.py` falla si un archivo de Mixamo (huesos `mixamorig`, animación `mixamo.com` o `.fbx`) entra a git.
- Se suben con `ops/oficina/subir_recursos_bar.py` (lee la carpeta `procesados`, fuera del repo) y el backend los sirve
  solo con sesión de Admin V2 (`/admin-v2plus/oficina/bar/...`, 401 sin sesión), con lista blanca y huella sha256.
- Se convirtieron a glTF con FBX2glTF, meshopt y texturas WebP de 1024 px (solo cambia el formato).

## Personajes de Quaternius (retirados)

Los cuerpos base de Quaternius (CC0) se retiraron del repositorio el 2026-11-11: se veían sin ropa. Ningún piso los usa;
el piso "realista" vuelve a sus personas hechas en código si se enciende para otra empresa.
