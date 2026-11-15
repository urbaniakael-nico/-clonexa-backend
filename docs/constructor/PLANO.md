# Modo constructor · esquema del plano (`.clonexa.json`)

El plano describe el local de UNA empresa a escala real. Lo valida `app/services/constructor_plano.py::clean_plan`
(estricto: campos desconocidos, ids repetidos, modelos fuera del catálogo o conexiones duplicadas se rechazan).

- Unidades: **metros**. Origen arriba a la izquierda de la sala; `x` hacia la derecha, `z` hacia abajo (como el plano 2D).
- Rotación: **grados**, sentido horario visto desde arriba. En 3D la escena va centrada (`x - ancho/2`, `z - fondo/2`).
- Tamaño máximo: 400 KB, 400 objetos, 160 paredes, 80 aberturas, 60 pisos, 40 zonas, 48 puntos por polígono.

```json
{
  "formato": "clonexa.plano",
  "version_esquema": 1,
  "sala": {"ancho": 22, "fondo": 14, "alto": 3.4},
  "paredes": [{"id": "w1", "x1": 0, "z1": 0, "x2": 22, "z2": 0, "grosor": 0.15, "alto": 3.4, "color": "#9a3b2e", "material": "ladrillo"}],
  "aberturas": [{"id": "a1", "pared": "w3", "tipo": "puerta_doble", "pos": 11, "ancho": 1.6, "alto": 2.2, "base": 0}],
  "pisos": [{"id": "psalon", "zona": "salon", "puntos": [[0, 0], [22, 0], [22, 14], [0, 14]], "material": "madera_oscura", "color": "#4a2c1d"}],
  "zonas": [{"id": "salon", "nombre": "Salón", "tipo": "salon", "puntos": [[0, 0], [22, 0], [22, 14], [0, 14]]}],
  "objetos": [{"id": "o7", "asset": "mesa_redonda_4", "x": 7.2, "z": 3.4, "rot": 45, "escala": 1, "color": "#c47a3a", "variante": null,
               "capa": "muebles", "conexion": {"tipo": "mesa", "id": "Mesa 4"}, "texto": null}]
}
```

| Parte | Campos | Notas |
|---|---|---|
| `sala` | `ancho`, `fondo` (3–60 m), `alto` (2,2–8 m) | |
| `paredes[]` | `id`, `x1,z1,x2,z2`, `grosor` (0,05–0,6), `alto`, `color` (#rrggbb), `material` | Materiales: `pintura, ladrillo, ladrillo_blanco, concreto, listones, panel_negro, azulejo, vidrio, papel_tapiz, piedra` (cualquier color tiñe la textura). |
| `aberturas[]` | `id`, `pared`, `tipo`, `pos` (m desde el inicio de la pared, centro), `ancho`, `alto`, `base` | Puertas: `puerta, puerta_doble, puerta_vidrio, corrediza, cortina_metalica, vaiven` (base 0). Ventanas: `ventana, ventanal, vitrina`. Deben caber en su pared. |
| `pisos[]` | `id`, `zona` (opcional), `puntos` (polígono), `material`, `color` | `madera_clara, madera_oscura, baldosa_blanca, ajedrez, concreto_pulido, epoxico, alfombra, negro_brillante, deck, cesped`. |
| `zonas[]` | `id`, `nombre`, `tipo`, `puntos` | `salon, barra, cocina, caja, bodega, oficina, terraza, banos, pista, produccion, recepcion, otra`. |
| `objetos[]` | `id`, `asset` (id del catálogo), `x`, `z`, `y?`, `rot`, `escala` (0,2–5), `color?`, `variante?`, `capa`, `conexion?`, `texto?` | Capas: `piso, muebles, decoracion, techo, pared` (solo `muebles` cuenta para los avisos de cruces y puertas tapadas). |
| `conexion` | `tipo` + `id` real | `mesa` (mesas con QR: "Mesa N"), `puesto` (`puesto-N`), `escritorio` (id del empleado; al motor 3D llega solo su huella), `caja` (`caja-1`, `caja-2`), `pantalla` (`canciones, comandas, domicilios, produccion, turno, logo, texto`). Una entidad real se conecta a **un solo** objeto. |

Decoración especial: `logo_pared` (logo del Estudio de marca), `neon` (letrero con `texto` editable) y las pantallas
(`tv_pared`, `tv_grande`, `tv_pedestal`, `pantalla_cocina`) que muestran lo que diga su conexión `pantalla`.

## Versiones y en vivo

- Tabla `constructor_planos`: una fila `borrador` por empresa (autoguardado) y una fila `publicado` por versión (1, 2, 3…;
  se guardan las últimas 40). "Restaurar" copia una versión al borrador.
- El piso en vivo (Oficina 3D y Negocio en vivo 3D) usa la **última versión publicada** solo si el interruptor de la
  empresa `oficina_pisos.usa_plano` está encendido (apagado por defecto; se enciende al publicar marcando la casilla).
  El borrador nunca se ve en vivo. Sin plano en vivo, la empresa sigue con su piso de siempre.
- Estilo de la escena por empresa: `oficina_pisos.estilo_escena` = `humano` (por defecto) o `caricatura`. El mismo plano
  se dibuja en los dos; el estilo nunca cambia posiciones ni conexiones.

## Exportar / importar

`GET .../empresas/{id}/exportar` descarga `{formato, version_esquema, exportado_de, version, plano}`.
`POST .../empresas/{id}/importar` valida el archivo completo y lo carga como **borrador** de la otra empresa; las
conexiones se quitan (las entidades reales son de la empresa de origen).
