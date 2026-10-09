import { relations } from 'drizzle-orm';
import {
  bigint,
  boolean,
  datetime,
  double,
  index,
  int,
  mysqlEnum,
  mysqlTable,
  timestamp,
  uniqueIndex,
  varchar,
} from 'drizzle-orm/mysql-core';

/**
 * Guarda los metadatos de las imágenes.
 * El archivo real se almacena en MinIO mediante storageKey.
 */

export const images = mysqlTable(
  'images',
  {
    // ID único de la imagen.
    id: bigint('id', {
      mode: 'number',
      unsigned: true,
    })
      .autoincrement()
      .primaryKey(),

    // Nombre original del archivo.
    filename: varchar('filename', {
      length: 255,
    }).notNull(),

    // Ruta o key del archivo dentro de MinIO.
    storageKey: varchar('storage_key', {
      length: 512,
    }).notNull(),

    // Tipo de archivo, por ejemplo image/jpeg.
    mimeType: varchar('mime_type', {
      length: 100,
    }).notNull(),

    // Dimensiones de la imagen en píxeles.
    width: int('width', {
      unsigned: true,
    }).notNull(),

    height: int('height', {
      unsigned: true,
    }).notNull(),

    // Tamaño del archivo en bytes.
    sizeBytes: bigint('size_bytes', {
      mode: 'number',
      unsigned: true,
    }).notNull(),

    // Estado actual del proceso de anotación.
    status: mysqlEnum('status', ['pending', 'in_progress', 'completed'])
      .notNull()
      .default('pending'),

    // Fecha de creación del registro.
    createdAt: timestamp('created_at').notNull().defaultNow(),

    // Fecha de la última actualización.
    updatedAt: timestamp('updated_at').notNull().defaultNow().onUpdateNow(),
  },

  // Índices para mejorar búsquedas y filtros.
  (table) => [
    uniqueIndex('images_storage_key_unique').on(table.storageKey),
    index('images_status_idx').on(table.status),
    index('images_created_at_idx').on(table.createdAt),
    index('images_status_created_at_idx').on(table.status, table.createdAt),
  ],
);
/**
 * categories
 *
 * Categorías/clases usadas para anotar imágenes (equivalente a
 * `categories` en el formato COCO).
 */

export const categories = mysqlTable(
  'categories',
  {
    // ID único de la categoría.
    id: bigint('id', {
      mode: 'number',
      unsigned: true,
    })
      .autoincrement()
      .primaryKey(),

    // Nombre de la categoría, por ejemplo person o car.
    name: varchar('name', {
      length: 150,
    }).notNull(),

    // Color usado para mostrar la bounding box en la interfaz (hexadecimal).
    color: varchar('color', {
      length: 7,
    }).notNull(),

    // Fecha de creación de la categoría.
    createdAt: timestamp('created_at').notNull().defaultNow(),
  },

  // Evita que existan dos categorías con el mismo nombre.
  (table) => [uniqueIndex('categories_name_unique').on(table.name)],
);

/**
 * annotations
 *
 * Bounding box asociado a una imagen y una categoría. Los campos de bbox
 * siguen la convención de COCO (x, y = esquina superior izquierda;
 * width/height = dimensiones de la caja) para que la futura fase de
 * exportación a COCO JSON no requiera cambios de schema.
 */
export const annotations = mysqlTable(
  'annotations',
  {
    // ID único de la anotación.
    id: bigint('id', {
      mode: 'number',
      unsigned: true,
    })
      .autoincrement()
      .primaryKey(),

    // Imagen a la que pertenece la bounding box.
    imageId: bigint('image_id', {
      mode: 'number',
      unsigned: true,
    })
      .notNull()
      .references(() => images.id, {
        onDelete: 'cascade',
      }),

    // Categoría asignada a la bounding box.
    categoryId: bigint('category_id', {
      mode: 'number',
      unsigned: true,
    })
      .notNull()
      .references(() => categories.id, {
        onDelete: 'restrict',
      }),

    // Posición y tamaño de la caja en píxeles.
    bboxX: double('bbox_x').notNull(),
    bboxY: double('bbox_y').notNull(),
    bboxWidth: double('bbox_width').notNull(),
    bboxHeight: double('bbox_height').notNull(),

    // Área de la bounding box para la exportación COCO.
    area: double('area').notNull(),

    // Campo requerido por el formato COCO.
    isCrowd: boolean('iscrowd').notNull().default(false),

    // Fecha de creación de la anotación.
    createdAt: timestamp('created_at').notNull().defaultNow(),

    // Fecha de la última modificación.
    updatedAt: timestamp('updated_at').notNull().defaultNow().onUpdateNow(),
  },

  // Índices para buscar anotaciones por imagen y categoría.
  (table) => [
    index('annotations_image_id_idx').on(table.imageId),
    index('annotations_category_id_idx').on(table.categoryId),
    index('annotations_image_category_idx').on(table.imageId, table.categoryId),
  ],
);

/**
 * Relación: una imagen puede tener muchas anotaciones.
 */
export const imagesRelations = relations(images, ({ many }) => ({
  annotations: many(annotations),
}));

/**
 * Relación: una categoría puede pertenecer a muchas anotaciones.
 */
export const categoriesRelations = relations(categories, ({ many }) => ({
  annotations: many(annotations),
}));

/**
 * Cada anotación pertenece a una imagen y a una categoría.
 */
export const annotationsRelations = relations(annotations, ({ one }) => ({
  image: one(images, {
    fields: [annotations.imageId],
    references: [images.id],
  }),

  category: one(categories, {
    fields: [annotations.categoryId],
    references: [categories.id],
  }),
}));

/**
 * APP-08 — vínculo entre una inferencia y la imagen real que entra
 * a la cola existente de anotación.
 *
 * La imagen sigue viviendo en `images` y por eso aparece en el flujo
 * pending/in_progress normal. Esta tabla conserva su procedencia ML.
 */
export const inferenceQueueEntries = mysqlTable(
  'inference_queue_entries',
  {
    id: bigint('id', {
      mode: 'number',
      unsigned: true,
    })
      .autoincrement()
      .primaryKey(),

    imageId: bigint('image_id', {
      mode: 'number',
      unsigned: true,
    })
      .notNull()
      .references(() => images.id, {
        onDelete: 'cascade',
      }),

    idempotencyKey: varchar('idempotency_key', {
      length: 64,
    }).notNull(),

    sourceKind: mysqlEnum('source_kind', ['upload', 'crop']).notNull(),

    sourceRef: varchar('source_ref', {
      length: 255,
    }).notNull(),

    modelName: varchar('model_name', {
      length: 255,
    }).notNull(),

    modelVersion: varchar('model_version', {
      length: 32,
    }).notNull(),

    runId: varchar('run_id', {
      length: 64,
    }).notNull(),

    checkpointSha256: varchar('checkpoint_sha256', {
      length: 64,
    }).notNull(),

    predictedClass: varchar('predicted_class', {
      length: 150,
    }).notNull(),

    probabilityDog: double('probability_dog').notNull(),
    probabilityCat: double('probability_cat').notNull(),

    createdAt: timestamp('created_at').notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex('inference_queue_idempotency_key_unique').on(table.idempotencyKey),
    uniqueIndex('inference_queue_image_id_unique').on(table.imageId),
    index('inference_queue_created_at_idx').on(table.createdAt),
  ],
);

/**
 * AWS-1 — fotos que el dispositivo edge (laptop) clasificó con el modelo optimizado
 * (Capturas Edge).
 *
 * La foto vive en S3 (`imageKey`, prefijo edge-captures/) y aquí queda el evento.
 * `captureId` lo genera el dispositivo: el índice único hace que un reenvío del mismo
 * evento no cree un segundo registro.
 */
export const edgeCaptures = mysqlTable(
  'edge_captures',
  {
    id: bigint('id', {
      mode: 'number',
      unsigned: true,
    })
      .autoincrement()
      .primaryKey(),

    captureId: varchar('capture_id', {
      length: 64,
    }).notNull(),

    // Momento en que el dispositivo edge tomó la foto (lo reporta el dispositivo).
    capturedAt: datetime('captured_at', {
      mode: 'date',
      fsp: 3,
    }).notNull(),

    deviceId: varchar('device_id', {
      length: 128,
    }).notNull(),

    modelVersion: varchar('model_version', {
      length: 64,
    }).notNull(),

    predictedClass: varchar('predicted_class', {
      length: 150,
    }).notNull(),

    confidence: double('confidence').notNull(),

    latencyMs: double('latency_ms').notNull(),

    // AWS-2: recorte clasificado dentro de la foto, en píxeles (opcional: o vienen
    // los cuatro o ninguno).
    cropX: double('crop_x'),
    cropY: double('crop_y'),
    cropWidth: double('crop_width'),
    cropHeight: double('crop_height'),

    // Key del objeto en S3 (edge-captures/<captureId>.jpg).
    imageKey: varchar('image_key', {
      length: 512,
    }).notNull(),

    // Momento en que el backend recibió el evento.
    receivedAt: timestamp('received_at').notNull().defaultNow(),
  },
  (table) => [
    uniqueIndex('edge_captures_capture_id_unique').on(table.captureId),
    // AWS-2: la consulta del portal ordena por captured_at (desempate por id).
    index('edge_captures_captured_at_id_idx').on(table.capturedAt, table.id),
    index('edge_captures_received_at_idx').on(table.receivedAt),
    index('edge_captures_device_id_idx').on(table.deviceId),
  ],
);

/**
 * Tipos TypeScript generados automáticamente desde el esquema.
 */
export type Image = typeof images.$inferSelect;
export type NewImage = typeof images.$inferInsert;

export type Category = typeof categories.$inferSelect;
export type NewCategory = typeof categories.$inferInsert;

export type Annotation = typeof annotations.$inferSelect;
export type NewAnnotation = typeof annotations.$inferInsert;

export type InferenceQueueEntry = typeof inferenceQueueEntries.$inferSelect;
export type NewInferenceQueueEntry = typeof inferenceQueueEntries.$inferInsert;

export type EdgeCapture = typeof edgeCaptures.$inferSelect;
export type NewEdgeCapture = typeof edgeCaptures.$inferInsert;
