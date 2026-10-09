import sharp from 'sharp';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * AWS-1/AWS-2: guardar una captura es idempotente por capture_id, el recorte se
 * guarda y se devuelve, y la consulta da cada captura con su URL firmada.
 */

const findEdgeCaptureByCaptureId = vi.fn();
const createEdgeCaptureRow = vi.fn();
const putEdgeCaptureObject = vi.fn();
const listEdgeCaptureRows = vi.fn();
const countEdgeCaptures = vi.fn();
const getEdgeCaptureImageUrl = vi.fn(async (key: string) => `https://s3.example/${key}?firmada`);

type Service = typeof import('../src/logic/edge-capture.service.js');
let saveEdgeCapture: Service['saveEdgeCapture'];
let listEdgeCaptures: Service['listEdgeCaptures'];
let getEdgeCapture: Service['getEdgeCapture'];
let checkEdgeDeviceKey: Service['checkEdgeDeviceKey'];
let ValidationError: typeof import('../src/logic/errors.js').ValidationError;
let NotFoundError: typeof import('../src/logic/errors.js').NotFoundError;
let jpeg: Buffer;
let png: Buffer;

const DEVICE_KEY = 'clave-de-prueba-0123456789abcdef';

beforeAll(async () => {
  process.env.DATABASE_URL = 'mysql://root:ci@127.0.0.1:3306/image_repo';
  process.env.MINIO_ENDPOINT = '127.0.0.1';
  process.env.MINIO_ACCESS_KEY = 'ci';
  process.env.MINIO_SECRET_KEY = 'ci';
  process.env.MINIO_BUCKET = 'image-annotations';
  process.env.EDGE_DEVICE_KEY = DEVICE_KEY;
  vi.doMock('../src/data/index.js', () => ({
    countEdgeCaptures,
    createEdgeCaptureRow,
    findEdgeCaptureByCaptureId,
    getEdgeCaptureImageUrl,
    listEdgeCaptureRows,
    putEdgeCaptureObject,
  }));
  ({ saveEdgeCapture, listEdgeCaptures, getEdgeCapture, checkEdgeDeviceKey } = await import(
    '../src/logic/edge-capture.service.js'
  ));
  ({ ValidationError, NotFoundError } = await import('../src/logic/errors.js'));

  // Foto de 64x48, como un fotograma chico de webcam.
  const pixels = { width: 64, height: 48, channels: 3 as const, background: '#808080' };
  jpeg = await sharp({ create: pixels }).jpeg().toBuffer();
  png = await sharp({ create: pixels }).png().toBuffer();
});

beforeEach(() => {
  vi.clearAllMocks();
});

const fields = {
  capture_id: 'cap-0001',
  captured_at: '2026-10-08T15:04:05.000Z',
  device_id: 'laptop-equipo',
  model_version: '1.0.0-int8',
  predicted_class: 'cat',
  confidence: '0.88',
  latency_ms: '35',
};

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    captureId: 'cap-0001',
    capturedAt: new Date('2026-10-08T15:04:05.000Z'),
    deviceId: 'laptop-equipo',
    modelVersion: '1.0.0-int8',
    predictedClass: 'cat',
    confidence: 0.88,
    latencyMs: 35,
    cropX: null,
    cropY: null,
    cropWidth: null,
    cropHeight: null,
    imageKey: 'edge-captures/cap-0001.jpg',
    receivedAt: new Date('2026-10-08T15:04:06.000Z'),
    ...overrides,
  };
}

function image(buffer: Buffer, mimeType = 'image/jpeg') {
  return { mimeType, sizeBytes: buffer.length, buffer };
}

describe('AWS-1: guardar una captura del dispositivo edge', () => {
  it('una captura nueva sube la foto a edge-captures/ y crea el registro', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockResolvedValueOnce(row());

    const result = await saveEdgeCapture({ image: image(jpeg), fields });

    expect(result.created).toBe(true);
    expect(putEdgeCaptureObject).toHaveBeenCalledWith(
      'edge-captures/cap-0001.jpg',
      jpeg,
      expect.any(Object),
    );
    expect(createEdgeCaptureRow).toHaveBeenCalledWith(
      expect.objectContaining({
        captureId: 'cap-0001',
        confidence: 0.88,
        latencyMs: 35,
        predictedClass: 'cat',
        imageKey: 'edge-captures/cap-0001.jpg',
        cropX: null,
      }),
    );
    expect(result.capture).toEqual({
      capture_id: 'cap-0001',
      captured_at: '2026-10-08T15:04:05.000Z',
      received_at: '2026-10-08T15:04:06.000Z',
      device_id: 'laptop-equipo',
      model_version: '1.0.0-int8',
      predicted_class: 'cat',
      confidence: 0.88,
      latency_ms: 35,
      crop: null,
      image_key: 'edge-captures/cap-0001.jpg',
    });
  });

  it('copia el registro en los metadatos del objeto de S3, con el mismo received_at', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockResolvedValueOnce(row());

    await saveEdgeCapture({ image: image(jpeg), fields });

    const metadata = putEdgeCaptureObject.mock.calls[0]?.[2];
    const inserted = createEdgeCaptureRow.mock.calls[0]?.[0];
    expect(metadata).toMatchObject({
      'capture-id': 'cap-0001',
      'captured-at': '2026-10-08T15:04:05.000Z',
      'device-id': 'laptop-equipo',
      'model-version': '1.0.0-int8',
      'predicted-class': 'cat',
      confidence: '0.88',
      'latency-ms': '35',
    });
    expect(metadata['received-at']).toBe(inserted.receivedAt.toISOString());
    expect(inserted.receivedAt.getMilliseconds()).toBe(0);
    expect(metadata).not.toHaveProperty('crop');
  });

  it('un capture_id repetido devuelve el registro existente sin tocar S3 ni la base', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(row());

    const result = await saveEdgeCapture({ image: image(jpeg), fields });

    expect(result.created).toBe(false);
    expect(result.capture.capture_id).toBe('cap-0001');
    expect(putEdgeCaptureObject).not.toHaveBeenCalled();
    expect(createEdgeCaptureRow).not.toHaveBeenCalled();
  });

  it('dos envíos simultáneos: el que pierde el INSERT devuelve el registro ganador', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null).mockResolvedValueOnce(row());
    // La foto ya la subió el otro envío: S3 rechaza la escritura y no se reescribe.
    putEdgeCaptureObject.mockResolvedValueOnce(false);
    createEdgeCaptureRow.mockRejectedValueOnce(new Error("Duplicate entry 'cap-0001'"));

    const result = await saveEdgeCapture({ image: image(jpeg), fields });

    expect(result.created).toBe(false);
    expect(result.capture.capture_id).toBe('cap-0001');
  });

  it('si la foto ya estaba en S3 (intento anterior fallido), solo completa el registro', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(false);
    createEdgeCaptureRow.mockResolvedValueOnce(row());

    const result = await saveEdgeCapture({ image: image(jpeg), fields });

    expect(result.created).toBe(true);
    expect(createEdgeCaptureRow).toHaveBeenCalledTimes(1);
  });

  it('un fallo de la base que no es un duplicado se propaga', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null).mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockRejectedValueOnce(new Error('connection lost'));

    await expect(saveEdgeCapture({ image: image(jpeg), fields })).rejects.toThrow(
      'connection lost',
    );
  });

  it.each([
    ['confidence fuera de rango', { ...fields, confidence: '1.5' }],
    ['una clase que el modelo no predice', { ...fields, predicted_class: 'bird' }],
  ])('rechaza %s como ValidationError, sin subir nada', async (_label, invalid) => {
    await expect(saveEdgeCapture({ image: image(jpeg), fields: invalid })).rejects.toBeInstanceOf(
      ValidationError,
    );
    expect(findEdgeCaptureByCaptureId).not.toHaveBeenCalled();
    expect(putEdgeCaptureObject).not.toHaveBeenCalled();
  });

  it.each([
    ['un PNG declarado como PNG', () => image(png, 'image/png')],
    ['un PNG que dice ser JPEG', () => image(png, 'image/jpeg')],
    ['bytes que no son imagen', () => image(Buffer.from('no soy una foto'))],
  ])('rechaza %s como ValidationError, sin subir nada', async (_label, makeImage) => {
    await expect(saveEdgeCapture({ image: makeImage(), fields })).rejects.toBeInstanceOf(
      ValidationError,
    );
    expect(putEdgeCaptureObject).not.toHaveBeenCalled();
  });
});

describe('AWS-2: campo crop', () => {
  const crop = '{"x":8,"y":4,"width":40,"height":30}';

  it('guarda el recorte en sus columnas, en los metadatos de S3 y lo devuelve', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockResolvedValueOnce(
      row({ cropX: 8, cropY: 4, cropWidth: 40, cropHeight: 30 }),
    );

    const result = await saveEdgeCapture({ image: image(jpeg), fields: { ...fields, crop } });

    expect(createEdgeCaptureRow).toHaveBeenCalledWith(
      expect.objectContaining({ cropX: 8, cropY: 4, cropWidth: 40, cropHeight: 30 }),
    );
    expect(putEdgeCaptureObject.mock.calls[0]?.[2].crop).toBe(
      '{"x":8,"y":4,"width":40,"height":30}',
    );
    expect(result.capture.crop).toEqual({ x: 8, y: 4, width: 40, height: 30 });
  });

  it.each([
    ['se sale por la derecha', '{"x":30,"y":0,"width":40,"height":10}'],
    ['se sale por abajo', '{"x":0,"y":20,"width":10,"height":30}'],
  ])('rechaza un recorte que %s de la foto (64x48), sin subir nada', async (_label, outside) => {
    await expect(
      saveEdgeCapture({ image: image(jpeg), fields: { ...fields, crop: outside } }),
    ).rejects.toBeInstanceOf(ValidationError);
    expect(putEdgeCaptureObject).not.toHaveBeenCalled();
  });

  it('acepta un recorte que ocupa la foto completa', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockResolvedValueOnce(row());

    await expect(
      saveEdgeCapture({
        image: image(jpeg),
        fields: { ...fields, crop: '{"x":0,"y":0,"width":64,"height":48}' },
      }),
    ).resolves.toMatchObject({ created: true });
  });
});

describe('AWS-2: consulta de capturas', () => {
  it('devuelve cada captura con su URL firmada, en el orden de la base', async () => {
    listEdgeCaptureRows.mockResolvedValueOnce([
      row({ id: 2, captureId: 'nueva', imageKey: 'edge-captures/nueva.jpg' }),
      row({ id: 1, captureId: 'vieja', imageKey: 'edge-captures/vieja.jpg' }),
    ]);
    countEdgeCaptures.mockResolvedValueOnce(2);

    const result = await listEdgeCaptures({});

    expect(result.items.map((item) => item.capture_id)).toEqual(['nueva', 'vieja']);
    expect(result.items[0]?.image_url).toBe('https://s3.example/edge-captures/nueva.jpg?firmada');
    expect(getEdgeCaptureImageUrl).toHaveBeenCalledWith('edge-captures/nueva.jpg', 900);
    expect(result).toMatchObject({ page: 1, pageSize: 20, total: 2 });
  });

  it('pagina con offset = (page - 1) * pageSize', async () => {
    listEdgeCaptureRows.mockResolvedValueOnce([]);
    countEdgeCaptures.mockResolvedValueOnce(45);

    await listEdgeCaptures({ page: '3', pageSize: '10' });

    expect(listEdgeCaptureRows).toHaveBeenCalledWith({ limit: 10, offset: 20 });
  });

  it('sin capturas devuelve una lista vacía, sin firmar nada', async () => {
    listEdgeCaptureRows.mockResolvedValueOnce([]);
    countEdgeCaptures.mockResolvedValueOnce(0);

    expect(await listEdgeCaptures({})).toEqual({ items: [], page: 1, pageSize: 20, total: 0 });
    expect(getEdgeCaptureImageUrl).not.toHaveBeenCalled();
  });

  it('una paginación inválida es ValidationError', async () => {
    await expect(listEdgeCaptures({ pageSize: '500' })).rejects.toBeInstanceOf(ValidationError);
    expect(listEdgeCaptureRows).not.toHaveBeenCalled();
  });

  it('una sola captura incluye su URL firmada y su recorte', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(
      row({ cropX: 1, cropY: 2, cropWidth: 3, cropHeight: 4 }),
    );

    const capture = await getEdgeCapture('cap-0001');

    expect(capture.image_url).toBe('https://s3.example/edge-captures/cap-0001.jpg?firmada');
    expect(capture.crop).toEqual({ x: 1, y: 2, width: 3, height: 4 });
  });

  it('una captura que no existe es NotFoundError', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);

    await expect(getEdgeCapture('no-existe')).rejects.toBeInstanceOf(NotFoundError);
  });

  it('un capture_id inválido es ValidationError, sin consultar la base', async () => {
    await expect(getEdgeCapture('../x')).rejects.toBeInstanceOf(ValidationError);
    expect(findEdgeCaptureByCaptureId).not.toHaveBeenCalled();
  });
});

describe('AWS-2: clave del dispositivo edge', () => {
  it('acepta la clave correcta', () => {
    expect(checkEdgeDeviceKey(DEVICE_KEY)).toBe('ok');
  });

  it.each([
    ['sin clave', undefined],
    ['con clave vacía', ''],
    ['con otra clave', 'clave-equivocada-0123456789abcdef'],
    ['con un prefijo de la clave', DEVICE_KEY.slice(0, 10)],
  ])('rechaza %s', (_label, provided) => {
    expect(checkEdgeDeviceKey(provided)).toBe('rejected');
  });
});
