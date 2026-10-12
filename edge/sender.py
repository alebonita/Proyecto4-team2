"""EDG-4: envio de un evento y su foto al endpoint de Capturas Edge (AWS-1/AWS-2).

POST multipart/form-data a api_url con la foto JPEG en el campo "image", los campos del
evento y "crop" como texto JSON, y la clave del dispositivo en un encabezado
(X-Device-Key). Respuestas del servidor:

- 201: captura nueva guardada. 200: ese capture_id ya existia (un reintento que llego).
  Las dos devuelven el registro con received_at e image_key.
- 400 (dato invalido) y 401 (clave ausente o incorrecta): no se arreglan reintentando.
- Red caida, tiempo de espera o 5xx: se pueden reintentar con retry.py.

La clave nunca va en el codigo ni en config.yaml: sale de la variable de entorno
EDGE_DEVICE_KEY o del archivo key_file (una linea EDGE_DEVICE_KEY=...).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

# Para --simular-fallo: el puerto 9 (discard) de la propia laptop, donde nada escucha.
# La conexion se rechaza al instante y no se toca el servidor real.
SIMULATED_FAILURE_URL = "http://127.0.0.1:9/api/edge-captures"
PERMANENT_STATUSES = (400, 401)


@dataclass(frozen=True)
class UploadConfig:
    api_url: str
    key_header: str
    key_env: str
    key_file: Path | None
    timeout_s: float
    auto_send: bool


@dataclass(frozen=True)
class SendResult:
    ok: bool
    http_status: int | None
    send_ms: float
    received_at: str | None = None
    image_key: str | None = None
    error: str | None = None

    @property
    def permanent(self) -> bool:
        """400 y 401 no se arreglan reintentando el mismo evento."""
        return self.http_status in PERMANENT_STATUSES


def parse_upload_config(raw: object) -> UploadConfig:
    """Valida la seccion upload de config.yaml. EDGE_API_URL y EDGE_KEY_HEADER la pisan."""
    if not isinstance(raw, dict):
        raise ValueError("falta la seccion upload (api_url, key_header, ...).")
    api_url = os.environ.get("EDGE_API_URL") or raw.get("api_url")
    if not isinstance(api_url, str) or not api_url.startswith(("http://", "https://")):
        raise ValueError("upload.api_url debe ser una URL http(s).")
    key_header = os.environ.get("EDGE_KEY_HEADER") or raw.get("key_header", "X-Device-Key")
    if not isinstance(key_header, str) or not key_header.strip():
        raise ValueError("upload.key_header debe ser el nombre del encabezado de la clave.")
    key_env = raw.get("key_env", "EDGE_DEVICE_KEY")
    if not isinstance(key_env, str) or not key_env.strip():
        raise ValueError("upload.key_env debe ser el nombre de una variable de entorno.")
    key_file = raw.get("key_file")
    if key_file is not None and not isinstance(key_file, str):
        raise ValueError("upload.key_file debe ser una ruta o quedar vacio.")
    timeout = raw.get("timeout_s", 10)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("upload.timeout_s debe ser un numero de segundos mayor que 0.")
    auto_send = raw.get("auto_send", True)
    if not isinstance(auto_send, bool):
        raise ValueError("upload.auto_send debe ser true o false.")
    return UploadConfig(
        api_url=api_url.rstrip("/"),
        key_header=key_header.strip(),
        key_env=key_env.strip(),
        key_file=Path(key_file).expanduser() if key_file else None,
        timeout_s=float(timeout),
        auto_send=auto_send,
    )


def read_device_key(cfg: UploadConfig) -> str | None:
    """La clave de la variable de entorno o, si no esta, del archivo key_file."""
    value = os.environ.get(cfg.key_env, "").strip()
    if value:
        return value
    if cfg.key_file is None or not cfg.key_file.is_file():
        return None
    for line in cfg.key_file.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == cfg.key_env and value.strip():
            return value.strip()
    return None


def describe_key_source(cfg: UploadConfig) -> str:
    """De donde sale la clave, sin mostrarla."""
    if os.environ.get(cfg.key_env, "").strip():
        return f"variable de entorno {cfg.key_env}"
    if read_device_key(cfg):
        return str(cfg.key_file)
    return f"NO ENCONTRADA (define {cfg.key_env} o upload.key_file)"


def event_fields(event) -> dict[str, str]:
    """Campos del formulario multipart, en el formato del contrato del endpoint."""
    x, y, width, height = event.crop
    return {
        "capture_id": event.capture_id,
        "captured_at": event.captured_at,
        "device_id": event.device_id,
        "model_version": event.model_version,
        "predicted_class": event.predicted_class,
        "confidence": repr(event.confidence),
        "latency_ms": repr(event.latency_ms),
        "crop": json.dumps({"x": x, "y": y, "width": width, "height": height}),
    }


def send_event(event, photo: Path, cfg: UploadConfig, key: str | None) -> SendResult:
    """Un intento de envio. Nunca lanza excepciones: el resultado dice si llego o por que no."""
    import requests

    start = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - start) * 1000

    if not key:
        return SendResult(
            False, None, elapsed(), error=f"Falta la clave de dispositivo ({cfg.key_env})."
        )
    try:
        image = photo.read_bytes()
    except OSError as exc:
        return SendResult(False, None, elapsed(), error=f"No se pudo leer la foto {photo}: {exc}")

    try:
        response = requests.post(
            cfg.api_url,
            headers={cfg.key_header: key},
            data=event_fields(event),
            files={"image": (photo.name, image, "image/jpeg")},
            timeout=cfg.timeout_s,
        )
    except requests.Timeout:
        return SendResult(
            False, None, elapsed(), error=f"Tiempo de espera agotado ({cfg.timeout_s:g} s)."
        )
    except requests.ConnectionError as exc:
        return SendResult(False, None, elapsed(), error=f"Sin conexion con el servidor: {exc}")
    except requests.RequestException as exc:
        return SendResult(False, None, elapsed(), error=f"Error de red: {exc}")
    send_ms = elapsed()

    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code in (200, 201):
        return SendResult(
            True,
            response.status_code,
            send_ms,
            received_at=body.get("received_at"),
            image_key=body.get("image_key"),
        )
    reason = body.get("error") if isinstance(body, dict) else None
    reason = reason or response.text.strip()[:200] or response.reason
    return SendResult(False, response.status_code, send_ms, error=reason)


def describe(result: SendResult) -> str:
    """Una linea para la terminal y la ventana."""
    if result.ok:
        meaning = "nuevo" if result.http_status == 201 else "ya existia"
        return f"enviado (HTTP {result.http_status}, {meaning}, {result.send_ms:.0f} ms)"
    status = f"HTTP {result.http_status}: " if result.http_status else ""
    hint = " No se reintenta solo." if result.permanent else " Reintenta con retry.py."
    return f"error: {status}{result.error}{hint}"


def short_status(result: SendResult) -> str:
    """Version corta para la ventana."""
    if result.ok:
        return f"AWS: enviado ({result.http_status}) {result.send_ms:.0f} ms"
    status = f"{result.http_status} " if result.http_status else ""
    return f"AWS: error {status}- {result.error}"[:70]


def send_and_record(store, event, cfg: UploadConfig, key: str | None, base_dir: Path):
    """Envia el evento con su mismo capture_id y guarda el resultado en el historial."""
    photo = Path(event.photo_path)
    result = send_event(event, photo if photo.is_absolute() else base_dir / photo, cfg, key)
    if result.ok:
        store.mark_sent(
            event.capture_id,
            result.received_at,
            result.image_key,
            result.http_status,
            result.send_ms,
        )
    else:
        store.mark_error(event.capture_id, result.error, result.http_status, result.send_ms)
    return result
