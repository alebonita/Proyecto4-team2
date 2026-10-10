# Pruebas de operación del dispositivo edge (EDG-6)

Tres pruebas manuales que reproducen lo que se mostrará en la demo: **cinco minutos
capturando**, **clasificación sin red** y **captura nueva después de reiniciar el programa**.
Se hacen en la laptop edge, con su teclado y su pantalla (la prueba sin red corta el SSH).
Cada resultado se anota con la hora en la tabla de [Registro de resultados](#registro-de-resultados).

Lo que se usa del programa (`edge/`, ver [`edge/README.md`](../../edge/README.md)):

| Tecla o comando | Qué hace |
|---|---|
| Barra espaciadora | Foto + clasificación + evento + envío a AWS |
| `i` | Activa o detiene la captura cada `capture_interval_s` segundos (10 por defecto) |
| `q` | Cierra el programa |
| `logs/edge.log` | Registro local: arranque, capturas, envíos y errores, con hora |
| `python list_events.py -n 30` | Últimos eventos del historial con ID, hora, clase, confianza y estado |
| `python retry.py --todos` | Reenvía a AWS lo que quedó en error o pendiente, con el mismo `capture_id` |

## Antes de empezar

1. Desde SSH, prender la pantalla (la laptop la apaga al arrancar):
   ```bash
   echo 80 | sudo tee /sys/class/backlight/acpi_video0/brightness
   ```
2. Tener a la mano fotos de **perros y gatos** (impresas o en una tablet o celular) y montar
   la webcam frente a ellas, a unos 25–30 cm, sin reflejos.
3. En la laptop, iniciar sesión y comprobar el modelo y las pruebas automáticas:
   ```bash
   cd Proyecto4-team2/edge
   .venv/bin/python -m unittest discover -s tests -b      # deben pasar todas
   ```
4. Anotar el estado inicial del historial: `.venv/bin/python list_events.py`.

## Prueba 1 — Cinco minutos continuos

Objetivo: el programa captura, clasifica y envía durante cinco minutos sin caerse, sin
crecer en memoria y sin perder eventos. Sirve también para las **20 capturas de la rúbrica**.

1. Arrancar con vista previa: `./run_display.sh`. Anotar la **hora de inicio**.
2. Comprobar en pantalla el recuadro verde y, al arrancar, en `logs/edge.log`, el modelo,
   el SHA-256 y el destino de envío.
3. Presionar `i`: debe aparecer `Intervalo: cada 10 s (i: parar)` en la ventana.
4. Durante **5 minutos**, cambiar la foto frente a la cámara cada 10–20 s, **alternando
   perros y gatos** (al menos 10 de cada uno). Cada captura muestra la clase, la confianza,
   los ms y, en la segunda línea, `AWS: enviado (201) … ms`.
5. Presionar `i` para detener y `q` para salir. Anotar la **hora de fin**.
6. Comprobar:
   ```bash
   .venv/bin/python list_events.py -n 40        # ~30 eventos nuevos, todos "enviado"
   grep -c "ERROR" logs/edge.log                # errores de la sesion (deberian ser 0)
   grep "Estado:" logs/edge.log | tail -6       # memoria cada minuto: no debe crecer
   ```

**Pasa si:** el programa no se cerró solo, hay al menos 20 eventos nuevos repartidos entre
`dog` y `cat`, todos llegaron a AWS (`enviado`) y la memoria de las líneas `Estado:` se
mantiene estable (variaciones de unos pocos MB).

## Prueba 2 — Clasificación con la red apagada

Objetivo: después de cargar el modelo, la captura y la clasificación siguen sin red; los
envíos fallan con un error visible y se recuperan al volver la red.

La laptop no tiene wifi: la red es el adaptador USB-Ethernet. **Desconectarlo corta también
Tailscale, el SSH y el clúster** durante la prueba.

1. Arrancar `./run_display.sh` (con red). Anotar la hora.
2. Hacer una captura con red (espacio): debe llegar a AWS.
3. **Desconectar el adaptador de red.** Anotar la hora.
4. Hacer al menos 4 capturas (2 perros y 2 gatos) con la barra espaciadora. Cada una debe
   mostrar clase, confianza y ms, y la segunda línea **en rojo**:
   `AWS: error - Sin conexion con el servidor …: Network is unreachable`.
5. Salir con `q`. **Reconectar el adaptador.** Anotar la hora.
6. Esperar a que vuelva la red (unos segundos) y reenviar lo que quedó en error:
   ```bash
   .venv/bin/python retry.py --todos    # mismos capture_id: 201 y "En AWS: ..."
   .venv/bin/python list_events.py -n 6
   ```
7. Comprobar en el sistema el intervalo sin red:
   `journalctl -k --since "-15min" | grep -i "usb disconnect\|enx"`.

**Pasa si:** las capturas sin red se clasificaron (clase, confianza y ms en pantalla), su
envío quedó en `error` con el motivo visible, y después de reconectar `retry.py` las envió con
el mismo `capture_id`, sin duplicados.

## Prueba 3 — Reinicio del programa

Objetivo: al cerrar y volver a abrir el programa se conserva el historial y se puede
capturar y clasificar de nuevo.

1. Con el programa cerrado, anotar el total: `.venv/bin/python list_events.py -n 1`
   (última línea: `N eventos en total`).
2. Arrancar `./run_display.sh`. La terminal y `logs/edge.log` deben decir
   `Historial: … (N eventos)` con el mismo N.
3. Hacer una captura (espacio): clase, confianza, ms y `AWS: enviado (201)`.
4. Salir con `q` y comprobar que el total es **N + 1** y que el evento nuevo es el primero de
   `list_events.py`.

**Pasa si:** el historial conserva los N eventos al reabrir y la captura nueva se clasifica,
se registra y se envía.

## Al terminar

```bash
.venv/bin/python export_events.py -o ../evidencias/edg-6/eventos.json
cp logs/edge.log ../evidencias/edg-6/edge.log
sudo systemctl start backlight-off          # apagar la pantalla otra vez
```

## Registro de resultados

| Prueba | Inicio | Fin | Resultado | Notas (eventos, errores, memoria) |
|---|---|---|---|---|
| 1. Cinco minutos continuos | | | | |
| 2. Red apagada | | | | |
| 3. Reinicio del programa | | | | |
