import express from 'express';
import multer from 'multer';
import { env } from '../config/env.js';
import {
  checkEdgeDeviceKey,
  checkHealth,
  createAnnotationForImage,
  createSettingsService,
  deleteAnnotation,
  deleteImage,
  enqueueInferenceResult,
  exportCocoDataset,
  getAnnotationsForImage,
  getCategories,
  getDashboardSummary,
  getEdgeCapture,
  getImageFile,
  idParamSchema,
  imageSearchSchema,
  initializeApplication,
  listEdgeCaptures,
  NotFoundError,
  saveEdgeCapture,
  searchImages,
  setImageStatus,
  TraceabilityUnavailableError,
  updateAnnotation,
  uploadImage,
  ValidationError,
} from '../logic/index.js';

/**
 * SPEC-VALID-001 — Valida un route param de id (`:imageId`, `:annotationId`)
 * con el mismo esquema que ya cubren los tests de `idParamSchema`: entero
 * positivo, rechaza decimales, negativos, cero y no numéricos.
 */
function parseIdParam(raw: unknown): number | null {
  const result = idParamSchema.safeParse(raw);
  return result.success ? result.data : null;
}

/**
 * SPEC-VALID-001 — Traduce un error de la capa Logic al código HTTP correcto.
 *
 * El mapeo se hace por clase de error, no comparando el texto del mensaje,
 * para que un cambio de redacción no altere la semántica de la respuesta.
 */
function sendError(res: express.Response, error: unknown, fallback: string): void {
  if (error instanceof NotFoundError) {
    res.status(404).json({ error: error.message });
    return;
  }

  if (error instanceof ValidationError) {
    res.status(400).json({ error: error.message });
    return;
  }

  if (error instanceof TraceabilityUnavailableError) {
    res.status(503).json({ error: error.message });
    return;
  }

  console.error(fallback, error);
  res.status(500).json({ error: fallback });
}

/**
 * Punto de entrada de la capa UI.
 *
 * La UI nunca accede directamente a MariaDB ni a MinIO;
 * únicamente se comunica con la capa Logic.
 */
export const app = express();
// Sin la cabecera `X-Powered-By: Express`: no hace falta anunciar el framework ni su versión.
app.disable('x-powered-by');
const port = env.PORT;

app.use(express.json());
const settingsService = createSettingsService(env.PIPELINE_CONFIG_ROOT);

app.get('/settings', async (_req, res) => {
  try {
    res.json(await settingsService.get());
  } catch (error) {
    sendError(res, error, 'No se pudo leer la configuración.');
  }
});

app.put('/settings/quality', async (req, res) => {
  try {
    res.json(await settingsService.saveQuality(req.body));
  } catch (error) {
    sendError(res, error, 'No se pudo guardar la política de calidad.');
  }
});

app.put('/settings/splits', async (req, res) => {
  try {
    res.json(await settingsService.saveSplits(req.body));
  } catch (error) {
    sendError(res, error, 'No se pudo guardar la configuración de splits.');
  }
});

/**
 * Multer mantiene temporalmente la imagen en memoria.
 * El archivo real posteriormente se almacena en MinIO.
 */
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: env.MAX_UPLOAD_SIZE_BYTES,
  },
});

app.get('/', (_req, res) => {
  res.json({
    project: 'image-annotation-repo',
    phase: 2,
    message: 'UI → Logic → Data funcionando.',
  });
});

app.get('/health', async (_req, res) => {
  const health = await checkHealth();

  res.status(health.status === 'ok' ? 200 : 503).json(health);
});

/**
 * Recibe una imagen y delega su procesamiento a Logic.
 */
app.post('/images', upload.single('image'), async (req, res) => {
  if (!req.file) {
    res.status(400).json({
      error: 'Debe enviarse una imagen.',
    });
    return;
  }

  try {
    const image = await uploadImage({
      filename: req.file.originalname,
      mimeType: req.file.mimetype,
      sizeBytes: req.file.size,
      buffer: req.file.buffer,
    });

    // El body va plano (sin wrapper), así coincide con el contrato que
    // espera el frontend (imageUploadResponseSchema): id, filename,
    // storageKey, width, height directamente en la raíz.
    res.status(201).json(image);
  } catch (error) {
    sendError(res, error, 'Error desconocido al cargar la imagen.');
  }
});

/**
 * APP-08 — envía un resultado de Inference a la cola real de anotación.
 *
 * multipart/form-data:
 * - image: archivo PNG/JPEG
 * - metadata: JSON con trazabilidad ML
 */
app.post('/images/from-inference', upload.single('image'), async (req, res) => {
  if (!req.file) {
    res.status(400).json({
      error: 'Debe enviarse una imagen.',
    });
    return;
  }

  let metadata: unknown;

  try {
    metadata = JSON.parse(String(req.body?.metadata ?? ''));
  } catch {
    res.status(400).json({
      error: 'metadata debe ser JSON válido.',
    });
    return;
  }

  try {
    const result = await enqueueInferenceResult({
      image: {
        filename: req.file.originalname,
        mimeType: req.file.mimetype,
        sizeBytes: req.file.size,
        buffer: req.file.buffer,
      },
      metadata: metadata as never,
    });

    res.status(result.created ? 201 : 200).json({
      imageId: result.imageId,
      created: result.created,
      idempotencyKey: result.idempotencyKey,
    });
  } catch (error) {
    sendError(res, error, 'No se pudo enviar la inferencia a la cola de anotación.');
  }
});

/**
 * AWS-2 — POST /edge-captures exige la clave del dispositivo edge (laptop) en el
 * encabezado `X-Device-Key`, comparada con `EDGE_DEVICE_KEY` del servidor.
 *
 * Va antes de multer: una petición sin clave se rechaza sin leer la foto. Nunca se
 * registra la clave recibida ni la esperada.
 */
function requireEdgeDeviceKey(
  req: express.Request,
  res: express.Response,
  next: express.NextFunction,
): void {
  const result = checkEdgeDeviceKey(req.get('X-Device-Key'));

  if (result === 'not-configured') {
    res.status(503).json({
      error: 'El servidor no tiene configurada la clave de dispositivo (EDGE_DEVICE_KEY).',
    });
    return;
  }

  if (result === 'rejected') {
    res.status(401).json({
      error: 'Clave de dispositivo ausente o incorrecta (encabezado X-Device-Key).',
    });
    return;
  }

  next();
}

/**
 * AWS-1 — recibe la foto y el evento de una captura del dispositivo edge (laptop).
 *
 * Encabezado `X-Device-Key` (AWS-2). multipart/form-data:
 * - image: foto JPEG
 * - capture_id, captured_at, device_id, model_version, predicted_class,
 *   confidence, latency_ms
 * - crop (opcional, AWS-2): JSON {"x","y","width","height"} en píxeles
 *
 * 201 si se guardó; 200 con el registro existente si el capture_id ya estaba.
 * Sin CORS: lo llama un programa en Python, no un navegador de otro origen.
 */
app.post('/edge-captures', requireEdgeDeviceKey, upload.single('image'), async (req, res) => {
  if (!req.file) {
    res.status(400).json({
      error: 'Debe enviarse una imagen.',
    });
    return;
  }

  try {
    const result = await saveEdgeCapture({
      image: {
        mimeType: req.file.mimetype,
        sizeBytes: req.file.size,
        buffer: req.file.buffer,
      },
      fields: req.body,
    });

    res.status(result.created ? 201 : 200).json(result.capture);
  } catch (error) {
    sendError(res, error, 'No se pudo guardar la captura.');
  }
});

/**
 * AWS-2 — capturas para el portal, de la más reciente a la más antigua por
 * captured_at, con una URL temporal firmada por foto. Abierta (sin clave).
 *
 * Query params: page (desde 1), pageSize (1 a 100, 20 por defecto).
 */
app.get('/edge-captures', async (req, res) => {
  try {
    res.status(200).json(await listEdgeCaptures(req.query));
  } catch (error) {
    sendError(res, error, 'No se pudieron consultar las capturas.');
  }
});

/**
 * AWS-2 — una sola captura por su capture_id. Abierta (sin clave).
 */
app.get('/edge-captures/:captureId', async (req, res) => {
  try {
    res.status(200).json(await getEdgeCapture(req.params.captureId));
  } catch (error) {
    sendError(res, error, 'No se pudo consultar la captura.');
  }
});

/**
 * Busca imágenes con filtros combinables y paginación.
 *
 * Query params:
 *  - q:          clases con operadores, ej. "car AND person" (SPEC-SEARCH-001)
 *  - status:     uno o varios separados por coma
 *  - categories: ids de categoría separados por coma
 *  - dateFrom / dateTo: rango sobre created_at (yyyy-mm-dd)
 *  - page / pageSize:   paginación
 *
 * El filtrado se resuelve en SQL, nunca en memoria.
 */
app.get('/images/search', async (req, res) => {
  const parsed = imageSearchSchema.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({
      error: parsed.error.issues[0]?.message ?? 'Parámetros de búsqueda inválidos.',
    });
    return;
  }

  const { q, status, categories, dateFrom, dateTo } = parsed.data;

  // 'yyyy-mm-dd' parsea a medianoche UTC. Sin este ajuste, dateTo excluía
  // cualquier imagen creada ese mismo día (todo lo que no fuera exactamente
  // 00:00:00), dejando el rango de fechas prácticamente inutilizable.
  if (dateTo) dateTo.setUTCHours(23, 59, 59, 999);

  try {
    const result = await searchImages({
      q,
      status,
      categoryIds: categories,
      dateFrom,
      dateTo,
      page: parsed.data.page,
      pageSize: parsed.data.pageSize,
    });

    res.status(200).json(result);
  } catch (error) {
    // Una expresión de búsqueda ambigua (mezclar AND y OR) es un 400.
    sendError(res, error, 'Error al buscar imágenes.');
  }
});

/**
 * Elimina una imagen (registro + archivo en MinIO + sus anotaciones).
 */
app.delete('/images/:imageId', async (req, res) => {
  const imageId = parseIdParam(req.params.imageId);
  if (imageId === null) {
    res.status(400).json({ error: 'ID de imagen inválido.' });
    return;
  }

  try {
    await deleteImage(imageId);
    res.status(204).end();
  } catch (error) {
    sendError(res, error, 'No se pudo eliminar la imagen.');
  }
});

/**
 * Sirve el binario de una imagen desde MinIO.
 */
app.get('/images/:imageId/file', async (req, res) => {
  const imageId = parseIdParam(req.params.imageId);
  if (imageId === null) {
    res.status(400).json({ error: 'ID de imagen inválido.' });
    return;
  }

  const file = await getImageFile(imageId);
  if (!file) {
    res.status(404).json({ error: 'Imagen no encontrada.' });
    return;
  }

  res.setHeader('Content-Type', file.mimeType);
  file.stream.on('error', () => res.destroy());
  file.stream.pipe(res);
});

/**
 * Cambia el status de una imagen.
 */
app.patch('/images/:imageId/status', async (req, res) => {
  const imageId = parseIdParam(req.params.imageId);

  if (imageId === null) {
    res.status(400).json({ error: 'ID de imagen inválido.' });
    return;
  }

  try {
    // El status se valida con Zod dentro del servicio.
    await setImageStatus(imageId, req.body?.status);
    res.status(204).end();
  } catch (error) {
    sendError(res, error, 'Error al actualizar el status.');
  }
});

/**
 * Lista/crea anotaciones de una imagen.
 */
app.get('/images/:imageId/annotations', async (req, res) => {
  const imageId = parseIdParam(req.params.imageId);
  if (imageId === null) {
    res.status(400).json({ error: 'ID de imagen inválido.' });
    return;
  }

  try {
    const annotations = await getAnnotationsForImage(imageId);
    res.status(200).json(annotations);
  } catch (error) {
    sendError(res, error, 'Error al obtener las anotaciones.');
  }
});

app.post('/images/:imageId/annotations', async (req, res) => {
  const imageId = parseIdParam(req.params.imageId);
  if (imageId === null) {
    res.status(400).json({ error: 'ID de imagen inválido.' });
    return;
  }

  try {
    const created = await createAnnotationForImage(imageId, req.body);
    res.status(201).json(created);
  } catch (error) {
    sendError(res, error, 'No se pudo crear la anotación.');
  }
});

/**
 * Actualiza o elimina una anotación existente.
 */
app.patch('/annotations/:annotationId', async (req, res) => {
  const annotationId = parseIdParam(req.params.annotationId);
  if (annotationId === null) {
    res.status(400).json({ error: 'ID de anotación inválido.' });
    return;
  }

  try {
    const updated = await updateAnnotation(annotationId, req.body);
    res.status(200).json(updated);
  } catch (error) {
    sendError(res, error, 'No se pudo actualizar la anotación.');
  }
});

app.delete('/annotations/:annotationId', async (req, res) => {
  const annotationId = parseIdParam(req.params.annotationId);
  if (annotationId === null) {
    res.status(400).json({ error: 'ID de anotación inválido.' });
    return;
  }

  try {
    await deleteAnnotation(annotationId);
    res.status(204).end();
  } catch (error) {
    sendError(res, error, 'No se pudo eliminar la anotación.');
  }
});

/**
 * Lista las categorías disponibles.
 */
app.get('/categories', async (_req, res) => {
  const categories = await getCategories();
  res.status(200).json(categories);
});

/**
 * Métricas del dashboard, calculadas en SQL: totales, objetos por clase,
 * progreso de anotación y actividad reciente (SPEC-DASH-001).
 */
app.get('/dashboard/summary', async (_req, res) => {
  try {
    const summary = await getDashboardSummary();
    res.status(200).json(summary);
  } catch (error) {
    sendError(res, error, 'Error al calcular las métricas del dashboard.');
  }
});

/**
 * Exporta el dataset completo en formato COCO como archivo descargable
 * (SPEC-COCO-001).
 */
app.get('/export/coco', async (_req, res) => {
  try {
    const dataset = await exportCocoDataset();
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Content-Disposition', 'attachment; filename="coco-dataset.json"');
    res.send(JSON.stringify(dataset, null, 2));
  } catch (error) {
    sendError(res, error, 'Error al exportar el dataset.');
  }
});

/**
 * Maneja errores generados por Multer.
 */
app.use(
  (error: unknown, _req: express.Request, res: express.Response, next: express.NextFunction) => {
    if (error instanceof multer.MulterError) {
      if (error.code === 'LIMIT_FILE_SIZE') {
        res.status(413).json({
          error: 'La imagen excede el tamaño máximo permitido.',
        });
        return;
      }

      res.status(400).json({
        error: 'No se pudo procesar el archivo.',
      });
      return;
    }

    next(error);
  },
);

/**
 * Inicializa los servicios necesarios antes de levantar el servidor.
 */
async function startServer(): Promise<void> {
  await initializeApplication();

  app.listen(port, () => {
    console.log(`Servidor escuchando en http://localhost:${port}`);
  });
}

if (process.env.NODE_ENV !== 'test') {
  startServer().catch((error: unknown) => {
    console.error('Error al iniciar la aplicación:', error);
    process.exit(1);
  });
}
