# Guion de la demostración: dispositivo edge (10–15 min)

Recorrido de la parte edge que pide el prompt de evaluación (Fase 4 B): dispositivo, modelo,
clasificación local, red desconectada, AWS, portal, fallo y reintento, reinicio y reproducción
de entradas conocidas. Cada paso dice qué mostrar, el comando y qué debe verse. Los pasos de la
laptop se hacen con su teclado y pantalla (el paso sin red corta el SSH).

Referencias: instalación y uso en [`edge/README.md`](../../edge/README.md); pruebas de operación
ya hechas en [`pruebas-operacion.md`](pruebas-operacion.md); evidencias en `evidencias/edg-1` a
`evidencias/edg-6`.

## Antes de que llegue el evaluador

- [ ] Laptop conectada a la corriente y a la red (adaptador USB-Ethernet).
- [ ] Pantalla prendida, desde SSH: `echo 80 | sudo tee /sys/class/backlight/acpi_video0/brightness`.
- [ ] Webcam frente a una tablet o fotos impresas de **perros y gatos**, a 25–30 cm, sin reflejos.
- [ ] En la laptop: `cd Proyecto4-team2/edge && .venv/bin/python -m unittest discover -s tests -b`
      (todas deben pasar).
- [ ] Una computadora con el **perfil de AWS del equipo** para la consulta de solo lectura
      (paso 5) y el portal abierto: `http://18.216.36.30` → sección **Capturas Edge**.

## 1. Dispositivo, cámara, modelo de origen, variante y runtime

```bash
.venv/bin/python device_info.py              # MacBook Air 6,1, i5-4260U, 3.3 GiB, Ubuntu 26.04, Python 3.14
lsusb | grep -i camera                       # webcam USB 13d3:784b (Acteck HD)
sha256sum models/dog-cat-resnet18-1.0.0-int8-rr.onnx
grep int8-rr ../evidencias/mod-03/model/SHA256SUMS   # el mismo SHA-256: 1d4a85fa…
```

Origen del modelo (para M1 y 1.1): `best.pt` del Proyecto 3 → ONNX fp32 (MOD-2) → INT8
`reduce_range` (MOD-3); hashes y registros en `evidencias/mod-01`, `mod-02` y `mod-03`.

Arrancar: `./run_display.sh`. Al abrir, la terminal y `logs/edge.log` muestran el archivo, el
SHA-256, la versión, onnxruntime 1.30.0 y `CPUExecutionProvider`.

## 2. Objetos elegidos por el evaluador

El evaluador escoge las fotos y su orden. Con cada una dentro del recuadro verde, **barra
espaciadora**: la ventana muestra clase, confianza y ms (preprocesamiento + inferencia), y en la
segunda línea `AWS: enviado (201) … ms`. La predicción cambia entre perros y gatos. Si una sale
mal, se anota: la calidad cuantitativa está en MOD-4 (126/128 en esta laptop).

## 3. Red desconectada: sigue capturando y clasificando

1. **Desconectar el adaptador USB-Ethernet** (es la única red; no hay wifi).
2. Tomar 2–4 fotos: clase, confianza y ms siguen apareciendo; la segunda línea sale **en rojo**,
   `AWS: error - Sin conexion con el servidor 18.216.36.30: Network is unreachable`.
3. `q` para salir y **reconectar** el adaptador.

## 4. Tras reconectar: captura nueva y envío

1. Esperar unos segundos a que vuelva la red y `./run_display.sh` otra vez.
2. Una captura nueva: `AWS: enviado (201)`.
3. Opcional (no lo exige la rúbrica): enviar las de sin red con `.venv/bin/python retry.py --todos`.

## 5. Seguir la captura hasta AWS y el portal

En la laptop, el ID y los datos locales de la última captura:

```bash
.venv/bin/python list_events.py -n 3         # capture_id, hora con zona, clase, confianza, estado
.venv/bin/python export_events.py -o /tmp/eventos.json   # todos los campos, incluido image_key
```

En la computadora con el perfil del equipo, **consulta de solo lectura en AWS** (S3 + registro):

```bash
AWS_PROFILE=<perfil-equipo> PORTAL_URL=http://18.216.36.30 bash scripts/p4/consulta-aws.sh <capture_id>
```

Debe mostrar el objeto `edge-captures/<capture_id>.jpg` en el bucket `mlops-p4-equipo-452857281704`
y el registro con la misma clase, confianza, fecha, dispositivo y versión que el historial local.

## 6. Portal: permanencia y actualización

Abrir **Capturas Edge** desde el menú del portal, refrescar: la captura del paso 4 aparece
primero, con su foto, clase, confianza, fecha, ID, dispositivo (`edge-macbookair-01`) y versión
(`dog-cat-resnet18-1.0.0-int8-rr`).

## 7. Fallo de envío controlado y reintento sin duplicar

```bash
./run_display.sh --simular-fallo             # una captura: "AWS: error - … 127.0.0.1:9: Connection refused"
.venv/bin/python list_events.py -n 1         # su capture_id, estado: error
.venv/bin/python retry.py <capture_id>       # HTTP 201, nuevo, y su registro en AWS
.venv/bin/python retry.py <capture_id>       # HTTP 200, ya existia: mismo received_at
```

`--simular-fallo` manda el envío a una dirección donde nada escucha: no cambia `config.yaml` ni
toca el servidor. Volver a correr `consulta-aws.sh <capture_id>` muestra un solo objeto y un solo
registro.

## 8. Reinicio del programa

`q` y `./run_display.sh` otra vez: la terminal dice `Historial: … (N eventos)` con los de antes;
una captura nueva se clasifica y se envía.

## 9. Reproducción dirigida de la calidad y del benchmark

Entradas conocidas que elija el evaluador (crop_id de `evidencias/mod-01/validation_manifest.csv`):

```bash
.venv/bin/python classify_image.py img131-ann149 img560-ann562 img31-ann38
```

Muestra, por recorte, la clase real, la del original, la que registró MOD-4 en esta laptop y la
que da ahora el programa, con confianza y ms. Las 128 dan la misma clase que MOD-4
(`evidencias/edg-2/predicciones_validacion_edge_int8-rr.csv`).

Benchmark (~10 s), para contrastar con `artifacts/p4/benchmark.csv`:

```bash
.venv/bin/python benchmark.py --salida /tmp/bench    # fp32 p50 ~13.4 ms, int8-rr ~11.3 ms
```

## Al terminar

```bash
sudo systemctl start backlight-off           # apagar la pantalla
```

## Dónde está cada evidencia de la parte edge

| Rúbrica | Evidencia |
|---|---|
| M2, 2.1, 2.3 | `evidencias/edg-2/` (8/8 con y sin red, fotos de la ventana) y `evidencias/edg-6/` |
| 2.2 | `edge/classifier.py`, `evidencias/edg-2/` (Pillow contra OpenCV; 128/128 con MOD-4), `classify_image.py` |
| 2.4 | `evidencias/edg-6/` (5 min, red apagada, reinicio; 41 capturas con fotos) |
| 3.1–3.3 | `artifacts/p4/benchmark.csv`, `benchmark-condiciones.json`, `evidencias/edg-5/` |
| 4.1, 4.2 | `evidencias/edg-6/eventos.json` y `contraste_local_vs_aws.txt` (45/45), `scripts/p4/consulta-aws.sh` |
| 4.3 | `evidencias/edg-4/` (fallo simulado, reintento 201 → 200, un registro) |
| 6.1, 6.3 | `edge/README.md` (ficha, instalación, configuración), `edge/config.example.yaml` |
| 6.2 | `edge/tests/` (27 pruebas), este guion, `pruebas-operacion.md` |
