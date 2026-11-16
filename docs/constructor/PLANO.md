# Biblioteca 3D · esquema del plano (`.clonexa.json`)

El plano es el JSON del **prototipo aprobado** (Modo constructor + Personajes). Lo dibuja la MISMA función en el editor,
en la Oficina 3D y en "Negocio en vivo 3D": `app/web/oficina/b3d/room.js::buildRoom`. Lo valida en el servidor
`app/services/constructor_v2.py::clean_plan` (estricto: campos desconocidos, ids repetidos, objetos fuera del catálogo,
una entidad real en dos objetos o una conexión de otro tipo se rechazan).

- Unidades: **metros**. Origen en el **centro** del local; `x` a la derecha, `z` hacia el frente (pared `s`).
- Giro: **grados** (`rotation.y = rot · π/180`).
- Paredes: las 4 del local (`n` fondo, `s` frente, `w` izquierda, `e` derecha), cada una con material y color.
- Límites: 400 KB, 400 objetos, 200 personas, 60 puertas/ventanas.

```json
{
  "name": "Bar",
  "room": {"w": 14, "d": 10, "h": 3.6},
  "floor": {"mat": "madera_oscura", "color": "#5b3a26"},
  "walls": {"n": {"mat": "ladrillo", "color": "#8a4130"}, "s": {"mat": "ladrillo", "color": "#8a4130"},
            "e": {"mat": "ladrillo", "color": "#8a4130"}, "w": {"mat": "ladrillo", "color": "#8a4130"}},
  "openings": [{"id": "a1", "wall": "s", "pos": 0.78, "type": "puerta_vidrio", "width": 1.0, "color": "#111111"}],
  "objects": [{"id": "k3f9a2b", "item": "mesa_redonda", "x": -1.6, "z": -1.6, "rot": 0, "color": "#7c4a2d", "color2": "#f20b6d",
               "conn": "mesa:Mesa 1"},
              {"id": "q81mzzx", "item": "neon", "x": -1.2, "z": -4.88, "rot": 0, "color": "#f20b6d", "text": "Night Bar"},
              {"id": "x2", "item": "tv_pared", "x": 2.2, "z": -4.88, "rot": 0, "screen": "Canciones pedidas", "conn": "pantalla:canciones"}],
  "people": [{"id": "p1", "pid": "a1b2c3d4e5f6", "x": 1.0, "z": 2.0, "rot": 180, "clip": "work"}]
}
```

- Materiales de pared: `pintura, ladrillo, ladrillo_blanco, concreto, madera, panel, azulejo, vidrio, tapiz, piedra`.
- Materiales de piso: `madera_clara, madera_oscura, baldosa, ajedrez, concreto, epoxico, alfombra, negro, deck, cesped`.
- Puertas y ventanas: `puerta, puerta_doble, puerta_vidrio, corrediza, cortina, vaiven, ventana, ventanal, vitrina` (`pos` 0..1 a lo largo de la pared).
- `item`: un objeto del catálogo del prototipo (`b3d/catalog.js`, 65 objetos en 13 carpetas) o un modelo aprobado de la
  Biblioteca (los 9 de Poly Haven CC0 y los subidos), por su id.
- `screen`: `Logo de la empresa, Canciones pedidas, Comandas en cocina, Domicilios, Tablero de producción, Partido / TV`.
- `products` (neveras): `Gaseosas, Cervezas, Agua, Variado`. `clip` (personas): `idle, walk, sit, work, dance`.
- `pid`: huella de la persona (`sha256(id del empleado)[:12]`, la misma de la copia viva); nunca el nombre ni el id real.

## Conexiones (`conn`): entidades REALES de ESA empresa

| Objeto conectable | Clave | Dato real que lo mueve en vivo |
|---|---|---|
| Mesas (redonda, cuadrada, para 2, larga, alta, butacas) | `mesa:<etiqueta>` | Mesa con QR (bombillo verde + clientes sentados cuando está activa) |
| Máquinas, estufa, parrilla, mesa de corte | `puesto:<n>` | Puesto/máquina: la operaria en turno se sienta a trabajar |
| Escritorio con computador | `emp:<huella>` | Esa persona del Personal: aparece trabajando cuando abre turno |
| Caja registradora | `caja:caja-1` / `caja:caja-2` | Quien cobra (cargo de caja) en turno |
| TV de pared, TV con pedestal, tablero | `pantalla:<canciones\|comandas\|domicilios\|produccion\|turno\|logo>` | Contenido real de la pantalla |
| Neveras de bebidas | `inv:<categoría>` | Inventario real: la nevera se ve tan llena como productos sobre su mínimo |
| Cabina DJ | `sonido:canciones` | Canciones pedidas |

## Guardado (por empresa)

- `constructor_planos`: varios diseños por empresa (`diseno_id`, `nombre`); una fila `borrador` por diseño (autoguardado)
  y una fila `publicado` por versión (las últimas 20). La miniatura va al **bucket privado** (`miniatura` = clave), nunca a Postgres.
- En vivo: `oficina_pisos.usa_plano` (interruptor de la empresa, apagado por defecto; "Publicar en vivo" lo enciende)
  y `oficina_pisos.plano_diseno` (qué diseño). Sin plano en vivo, la empresa sigue con su piso de siempre.
- Estilo: `oficina_pisos.estilo_escena` (`humano` = Humano, `caricatura` = Caricatura).
- Personajes: `oficina_personajes.look` = `{toon, human, uniform, custom}` en la fila `persona:<huella>` de la empresa.
- Uniformes: `constructor_uniformes` `{nombre, toon, human}` por empresa.
- Los planos de la fase 1 (formato con `sala`, paredes por segmentos) se convirtieron en la migración `025v_biblioteca3d`
  (`constructor_v2.from_v1`): centro del local, giro, materiales, aberturas por lado, objetos al equivalente del catálogo
  nuevo y conexiones a claves. Las paredes interiores y las zonas no existen en el prototipo.

Importar: el `.clonexa.json` se valida en el servidor; las conexiones y las personas no viajan (son de la empresa de origen).
