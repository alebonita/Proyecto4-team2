import sharp from 'sharp';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * AWS-1: guardar una captura es idempotente por capture_id. Un reenvío no crea otro
 * registro ni otra foto y devuelve el registro existente.
 */

const findEdgeCaptureByCaptureId = vi.fn();
const createEdgeCaptureRow = vi.fn();
const putEdgeCaptureObject = vi.fn();

let saveEdgeCapture: typeof import('../src/logic/edge-capture.service.js').saveEdgeCapture;
let ValidationError: typeof import('../src/logic/errors.js').ValidationError;
let jpeg: Buffer;
let png: Buffer;

beforeAll(async () => {
  process.env.DATABASE_URL = 'mysql://root:ci@127.0.0.1:3306/image_repo';
  process.env.MINIO_ENDPOINT = '127.0.0.1';
  process.env.MINIO_ACCESS_KEY = 'ci';
  process.env.MINIO_SECRET_KEY = 'ci';
  process.env.MINIO_BUCKET = 'image-annotations';
  vi.doMock('../src/data/index.js', () => ({
    createEdgeCaptureRow,
    findEdgeCaptureByCaptureId,
    putEdgeCaptureObject,
  }));
  ({ saveEdgeCapture } = await import('../src/logic/edge-capture.service.js'));
  ({ ValidationError } = await import('../src/logic/errors.js'));

  const pixels = { width: 4, height: 4, channels: 3 as const, background: '#808080' };
  jpeg = await sharp({ create: pixels }).jpeg().toBuffer();
  png = await sharp({ create: pixels }).png().toBuffer();
});

beforeEach(() => {
  vi.clearAllMocks();
});

const fields = {
  capture_id: 'cap-0001',
  captured_at: '2026-10-08T15:04:05.000Z',
  device_id: 'pixel-7-equipo',
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
    deviceId: 'pixel-7-equipo',
    modelVersion: '1.0.0-int8',
    predictedClass: 'cat',
    confidence: 0.88,
    latencyMs: 35,
    imageKey: 'edge-captures/cap-0001.jpg',
    receivedAt: new Date('2026-10-08T15:04:06.000Z'),
    ...overrides,
  };
}

function image(buffer: Buffer, mimeType = 'image/jpeg') {
  return { mimeType, sizeBytes: buffer.length, buffer };
}

describe('AWS-1: guardar una captura del celular', () => {
  it('una captura nueva sube la foto a edge-captures/ y crea el registro', async () => {
    findEdgeCaptureByCaptureId.mockResolvedValueOnce(null);
    putEdgeCaptureObject.mockResolvedValueOnce(true);
    createEdgeCaptureRow.mockResolvedValueOnce(row());

    const result = await saveEdgeCapture({ image: image(jpeg), fields });

    expect(result.created).toBe(true);
    expect(putEdgeCaptureObject).toHaveBeenCalledWith('edge-captures/cap-0001.jpg', jpeg);
    expect(createEdgeCaptureRow).toHaveBeenCalledWith(
      expect.objectContaining({
        captureId: 'cap-0001',
        confidence: 0.88,
        latencyMs: 35,
        predictedClass: 'cat',
        imageKey: 'edge-captures/cap-0001.jpg',
      }),
    );
    expect(result.capture).toEqual({
      capture_id: 'cap-0001',
      captured_at: '2026-10-08T15:04:05.000Z',
      device_id: 'pixel-7-equipo',
      model_version: '1.0.0-int8',
      predicted_class: 'cat',
      confidence: 0.88,
      latency_ms: 35,
      received_at: '2026-10-08T15:04:06.000Z',
      image_key: 'edge-captures/cap-0001.jpg',
    });
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
