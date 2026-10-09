import type { Server } from 'node:http';

import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

/**
 * AWS-1/AWS-2: /edge-captures por HTTP. El envío exige la clave del dispositivo edge
 * (laptop); las consultas quedan abiertas para el portal. Sin CORS.
 */

class MockValidationError extends Error {}
class MockNotFoundError extends Error {}

const DEVICE_KEY = 'clave-de-prueba-0123456789abcdef';

const capture = {
  capture_id: 'cap-0001',
  captured_at: '2026-10-08T15:04:05.000Z',
  received_at: '2026-10-08T15:04:06.000Z',
  device_id: 'laptop-equipo',
  model_version: '1.0.0-int8',
  predicted_class: 'dog',
  confidence: 0.93,
  latency_ms: 41.7,
  crop: { x: 8, y: 4, width: 40, height: 30 },
  image_key: 'edge-captures/cap-0001.jpg',
};

const saveEdgeCaptureMock = vi.fn();
const listEdgeCapturesMock = vi.fn();
const getEdgeCaptureMock = vi.fn();
const checkEdgeDeviceKeyMock = vi.fn((provided: string | undefined) =>
  provided === DEVICE_KEY ? 'ok' : 'rejected',
);

let server: Server | undefined;
let baseUrl: string;

beforeAll(async () => {
  process.env.NODE_ENV = 'test';
  process.env.DATABASE_URL = 'mysql://root:ci@127.0.0.1:3306/image_repo';
  process.env.MINIO_ENDPOINT = '127.0.0.1';
  process.env.MINIO_ACCESS_KEY = 'ci';
  process.env.MINIO_SECRET_KEY = 'ci';
  process.env.MINIO_BUCKET = 'image-annotations';

  vi.doMock('../src/logic/index.js', () => ({
    checkEdgeDeviceKey: checkEdgeDeviceKeyMock,
    checkHealth: vi.fn(),
    createAnnotationForImage: vi.fn(),
    createSettingsService: vi.fn(() => ({
      get: vi.fn(),
      saveQuality: vi.fn(),
      saveSplits: vi.fn(),
    })),
    deleteAnnotation: vi.fn(),
    deleteImage: vi.fn(),
    enqueueInferenceResult: vi.fn(),
    exportCocoDataset: vi.fn(),
    getAnnotationsForImage: vi.fn(),
    getCategories: vi.fn(),
    getDashboardSummary: vi.fn(),
    getEdgeCapture: getEdgeCaptureMock,
    getImageFile: vi.fn(),
    idParamSchema: z.coerce.number().int().positive(),
    imageSearchSchema: z.object({}).passthrough(),
    initializeApplication: vi.fn(),
    listEdgeCaptures: listEdgeCapturesMock,
    NotFoundError: MockNotFoundError,
    saveEdgeCapture: saveEdgeCaptureMock,
    searchImages: vi.fn(),
    setImageStatus: vi.fn(),
    TraceabilityUnavailableError: class MockTraceabilityUnavailableError extends Error {},
    updateAnnotation: vi.fn(),
    uploadImage: vi.fn(),
    ValidationError: MockValidationError,
  }));

  const { app } = await import('../src/ui/server.js');

  await new Promise<void>((resolve) => {
    server = app.listen(0, '127.0.0.1', resolve);
  });

  const address = server?.address();

  if (address === null || address === undefined || typeof address === 'string') {
    throw new Error('No se pudo obtener el puerto HTTP del test.');
  }

  baseUrl = `http://127.0.0.1:${address.port}`;
});

afterAll(async () => {
  vi.doUnmock('../src/logic/index.js');

  if (server === undefined) return;

  await new Promise<void>((resolve, reject) => {
    server?.close((error) => {
      if (error) reject(error);
      else resolve();
    });
  });
});

beforeEach(() => {
  saveEdgeCaptureMock.mockReset();
  listEdgeCapturesMock.mockReset();
  getEdgeCaptureMock.mockReset();
  checkEdgeDeviceKeyMock.mockClear();
});

function captureForm(withImage = true): FormData {
  const form = new FormData();
  if (withImage) {
    form.append(
      'image',
      new Blob([new Uint8Array([0xff, 0xd8, 0xff])], { type: 'image/jpeg' }),
      'c.jpg',
    );
  }
  form.append('capture_id', capture.capture_id);
  form.append('captured_at', capture.captured_at);
  form.append('device_id', capture.device_id);
  form.append('model_version', capture.model_version);
  form.append('predicted_class', capture.predicted_class);
  form.append('confidence', String(capture.confidence));
  form.append('latency_ms', String(capture.latency_ms));
  form.append('crop', JSON.stringify(capture.crop));
  return form;
}

function post(headers: Record<string, string> = { 'X-Device-Key': DEVICE_KEY }, withImage = true) {
  return fetch(`${baseUrl}/edge-captures`, {
    method: 'POST',
    headers,
    body: captureForm(withImage),
  });
}

describe('AWS-2 - clave del dispositivo en POST /edge-captures', () => {
  it('sin clave responde 401 y no procesa la captura', async () => {
    const response = await post({});

    expect(response.status).toBe(401);
    expect(saveEdgeCaptureMock).not.toHaveBeenCalled();
  });

  it('con clave incorrecta responde 401 y no procesa la captura', async () => {
    const response = await post({ 'X-Device-Key': 'clave-equivocada' });

    expect(response.status).toBe(401);
    expect(saveEdgeCaptureMock).not.toHaveBeenCalled();
  });

  it('si el servidor no tiene clave configurada responde 503, no queda abierto', async () => {
    checkEdgeDeviceKeyMock.mockReturnValueOnce('not-configured');

    const response = await post();

    expect(response.status).toBe(503);
    expect(saveEdgeCaptureMock).not.toHaveBeenCalled();
  });

  it('la respuesta de error no repite la clave recibida', async () => {
    const response = await post({ 'X-Device-Key': 'clave-secreta-que-no-debe-salir' });

    expect(await response.text()).not.toContain('clave-secreta-que-no-debe-salir');
  });
});

describe('AWS-1 - POST /edge-captures', () => {
  it('una captura nueva responde 201 con el registro y entrega los campos a Logic', async () => {
    saveEdgeCaptureMock.mockResolvedValueOnce({ created: true, capture });

    const response = await post();

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(capture);

    const input = saveEdgeCaptureMock.mock.calls[0]?.[0];
    expect(input.image.mimeType).toBe('image/jpeg');
    expect(input.fields).toMatchObject({
      capture_id: 'cap-0001',
      confidence: '0.93',
      crop: '{"x":8,"y":4,"width":40,"height":30}',
    });
  });

  it('un capture_id repetido responde 200 con el registro existente', async () => {
    saveEdgeCaptureMock.mockResolvedValueOnce({ created: false, capture });

    const response = await post();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(capture);
  });

  it('sin imagen responde 400 sin llamar a Logic', async () => {
    const response = await post(undefined, false);

    expect(response.status).toBe(400);
    expect(saveEdgeCaptureMock).not.toHaveBeenCalled();
  });

  it('una captura inválida (ValidationError) responde 400', async () => {
    saveEdgeCaptureMock.mockRejectedValueOnce(new MockValidationError('confidence fuera de rango'));

    const response = await post();

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: 'confidence fuera de rango' });
  });

  it('no responde con cabeceras CORS: lo llama un programa, no una página de otro origen', async () => {
    saveEdgeCaptureMock.mockResolvedValueOnce({ created: true, capture });

    const response = await post({
      'X-Device-Key': DEVICE_KEY,
      Origin: 'https://cualquier-sitio.example.com',
    });

    expect(response.headers.get('access-control-allow-origin')).toBeNull();
  });
});

describe('AWS-2 - GET /edge-captures (abierto para el portal)', () => {
  it('devuelve las capturas tal como las ordena Logic, sin pedir clave', async () => {
    const page = {
      items: [
        { ...capture, capture_id: 'nueva', image_url: 'https://s3.example/nueva' },
        { ...capture, capture_id: 'vieja', image_url: 'https://s3.example/vieja' },
      ],
      page: 1,
      pageSize: 20,
      total: 2,
    };
    listEdgeCapturesMock.mockResolvedValueOnce(page);

    const response = await fetch(`${baseUrl}/edge-captures?page=1&pageSize=20`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(page);
    expect(listEdgeCapturesMock.mock.calls[0]?.[0]).toMatchObject({ page: '1', pageSize: '20' });
    expect(checkEdgeDeviceKeyMock).not.toHaveBeenCalled();
  });

  it('sin capturas responde 200 con la lista vacía', async () => {
    listEdgeCapturesMock.mockResolvedValueOnce({ items: [], page: 1, pageSize: 20, total: 0 });

    const response = await fetch(`${baseUrl}/edge-captures`);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ items: [], page: 1, pageSize: 20, total: 0 });
  });

  it('una paginación inválida responde 400', async () => {
    listEdgeCapturesMock.mockRejectedValueOnce(new MockValidationError('pageSize fuera de rango'));

    const response = await fetch(`${baseUrl}/edge-captures?pageSize=500`);

    expect(response.status).toBe(400);
  });

  it('GET /edge-captures/:id devuelve una captura', async () => {
    getEdgeCaptureMock.mockResolvedValueOnce({ ...capture, image_url: 'https://s3.example/x' });

    const response = await fetch(`${baseUrl}/edge-captures/cap-0001`);

    expect(response.status).toBe(200);
    expect((await response.json()).crop).toEqual(capture.crop);
    expect(getEdgeCaptureMock).toHaveBeenCalledWith('cap-0001');
  });

  it('GET /edge-captures/:id de una captura que no existe responde 404', async () => {
    getEdgeCaptureMock.mockRejectedValueOnce(new MockNotFoundError('Captura no encontrada.'));

    const response = await fetch(`${baseUrl}/edge-captures/no-existe`);

    expect(response.status).toBe(404);
  });
});
