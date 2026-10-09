/**
 * Punto de entrada de la capa LOGIC.
 *
 * Responsabilidad: reglas de negocio, validaciones y (en fases
 * posteriores) procesamiento de imágenes/anotaciones.
 *
 * Regla de arquitectura: es la única capa que puede importar de `data`.
 * No debe contener código específico de UI (Express, HTTP, etc.).
 */

export type { AnnotationBoxInput } from './annotation.service.js';
export {
  createAnnotationForImage,
  deleteAnnotation,
  getAnnotationsForImage,
  updateAnnotation,
} from './annotation.service.js';
// Esquemas de la frontera HTTP (SPEC-VALID-001): la UI los usa para validar
// route params y query params antes de invocar a los servicios de arriba.
export type { ImageSearchInput } from './annotation.validation.js';
export { idParamSchema, imageSearchSchema } from './annotation.validation.js';
export { getCategories } from './category.service.js';
// Exportación COCO (SPEC-COCO-001)
export type {
  CocoAnnotation,
  CocoCategory,
  CocoDataset,
  CocoImage,
  CocoSourceData,
} from './coco-export.builder.js';
export { buildCocoDataset } from './coco-export.builder.js';
export { exportCocoDataset } from './coco-export.service.js';
// Dashboard (SPEC-DASH-001)
export type {
  AnnotationProgress,
  DashboardSourceData,
  DashboardSummary,
  ObjectPerClass,
  RecentUpload,
} from './dashboard.builder.js';
export { buildDashboardSummary, buildThumbnailUrl } from './dashboard.builder.js';
export { getDashboardSummary } from './dashboard.service.js';
// Capturas Edge (AWS-1, AWS-2)
export type {
  EdgeCaptureRecord,
  EdgeCaptureView,
  ListEdgeCapturesResult,
  SaveEdgeCaptureInput,
  SaveEdgeCaptureResult,
} from './edge-capture.service.js';
export {
  checkEdgeDeviceKey,
  EDGE_CAPTURE_URL_TTL_SECONDS,
  getEdgeCapture,
  listEdgeCaptures,
  saveEdgeCapture,
} from './edge-capture.service.js';
export type {
  EdgeCaptureCrop,
  EdgeCaptureFields,
  EdgeCaptureListQuery,
} from './edge-capture.validation.js';
export {
  buildEdgeCaptureKey,
  captureIdSchema,
  EDGE_CAPTURES_PREFIX,
  EDGE_MODEL_CLASSES,
  edgeCaptureCropSchema,
  edgeCaptureFieldsSchema,
  edgeCaptureListQuerySchema,
} from './edge-capture.validation.js';
// Errores tipados: la capa UI los mapea a códigos HTTP (SPEC-VALID-001).
export { NotFoundError, TraceabilityUnavailableError, ValidationError } from './errors.js';
export type { HealthStatus } from './health.service.js';
export { checkHealth } from './health.service.js';
export type { ImageFile } from './image-file.service.js';
export { getImageFile } from './image-file.service.js';
export type {
  ImageSearchItem,
  SearchImagesInput,
  SearchImagesResult,
  SearchResultCategory,
} from './image-search.service.js';
export { searchImages } from './image-search.service.js';
export { setImageStatus } from './image-status.service.js';
export { deleteImage, uploadImage } from './image-upload.service.js';
export type {
  EnqueueInferenceInput,
  EnqueueInferenceResult,
} from './inference-queue.service.js';
export { enqueueInferenceResult } from './inference-queue.service.js';
export type { InferenceQueueMetadata } from './inference-queue.validation.js';
export {
  buildInferenceQueueKey,
  inferenceQueueMetadataSchema,
} from './inference-queue.validation.js';
// Parser de operadores de búsqueda (SPEC-SEARCH-001)
export type { ParsedSearchQuery, SearchOperator } from './search-query.parser.js';
export { parseSearchQuery } from './search-query.parser.js';
export { createSettingsService } from './settings.service.js';
export { initializeApplication } from './startup.service.js';
