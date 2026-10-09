import type { Server } from 'node:http';

import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

/**
 * AWS-1: POST /edge-captures por HTTP, con CORS para la página del celular.
 */

class MockValidationError extends Error {}

const capture = {
  capture_id: 'cap-0001',
  captured_at: '2026-10-08T15:04:05.000Z',
  device_id: 'pixel-7-equipo',
  model_version: '1.0.0-int8',
  predicted_class: 'dog',
  confidence: 0.93,
  latency_ms: 41.7,
  received_at: '2026-10-08T15:04:06.000Z',
  image_key: 'edge-captures/cap-0001.jpg',
};

const saveEdgeCaptureMock = vi.fn();

let server: Server | undefined;
let baseUrl: string;

beforeAll(async () => {
  process.env.NODE_ENV = 'test';
  process.env.DATABASE_URL = 'mysql://root:ci@127.0.0.1:3306/image_repo';
  process.env.MINIO_ENDPOINT = '127.0.0.1';
  process.env.MINIO_ACCESS_KEY = 'ci';
  process.env.MINIO_SECRET_KEY = 'ci';
  process.env.MINIO_BUCKET = 'image-annotations';
  process.env.EDGE_CAPTURES_ALLOWED_ORIGINS = 'https://celular.example.com';

  vi.doMock('../src/logic/index.js', () => ({
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
    getImageFile: vi.fn(),
    idParamSchema: z.coerce.number().int().positive(),
    imageSearchSchema: z.object({}).passthrough(),
    initializeApplication: vi.fn(),
    NotFoundError: class MockNotFoundError extends Error {},
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
  delete process.env.EDGE_CAPTURES_ALLOWED_ORIGINS;

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
  return form;
}

describe('AWS-1 - POST /edge-captures', () => {
  it('una captura nueva responde 201 con el registro y entrega los campos a Logic', async () => {
    saveEdgeCaptureMock.mockResolvedValueOnce({ created: true, capture });

    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'POST',
      body: captureForm(),
    });

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(capture);

    const input = saveEdgeCaptureMock.mock.calls[0]?.[0];
    expect(input.image.mimeType).toBe('image/jpeg');
    expect(input.fields).toMatchObject({ capture_id: 'cap-0001', confidence: '0.93' });
  });

  it('un capture_id repetido responde 200 con el registro existente', async () => {
    saveEdgeCaptureMock.mockResolvedValueOnce({ created: false, capture });

    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'POST',
      body: captureForm(),
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(capture);
  });

  it('sin imagen responde 400 sin llamar a Logic', async () => {
    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'POST',
      body: captureForm(false),
    });

    expect(response.status).toBe(400);
    expect(saveEdgeCaptureMock).not.toHaveBeenCalled();
  });

  it('una captura inválida (ValidationError) responde 400', async () => {
    saveEdgeCaptureMock.mockRejectedValueOnce(new MockValidationError('confidence fuera de rango'));

    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'POST',
      body: captureForm(),
    });

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: 'confidence fuera de rango' });
  });
});

describe('AWS-1 - CORS de /edge-captures', () => {
  it('responde la preflight de un origen permitido', async () => {
    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'https://celular.example.com',
        'Access-Control-Request-Method': 'POST',
      },
    });

    expect(response.status).toBe(204);
    expect(response.headers.get('access-control-allow-origin')).toBe('https://celular.example.com');
    expect(response.headers.get('access-control-allow-methods')).toContain('POST');
  });

  it('agrega la cabecera también a la respuesta del POST (y a los errores)', async () => {
    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'POST',
      headers: { Origin: 'https://celular.example.com' },
      body: captureForm(false),
    });

    expect(response.status).toBe(400);
    expect(response.headers.get('access-control-allow-origin')).toBe('https://celular.example.com');
  });

  it('no permite un origen que no está en la lista', async () => {
    const response = await fetch(`${baseUrl}/edge-captures`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'https://otro-sitio.example.com',
        'Access-Control-Request-Method': 'POST',
      },
    });

    expect(response.headers.get('access-control-allow-origin')).toBeNull();
  });

  it('el resto de la API no expone CORS', async () => {
    const response = await fetch(`${baseUrl}/`, {
      headers: { Origin: 'https://celular.example.com' },
    });

    expect(response.headers.get('access-control-allow-origin')).toBeNull();
  });
});
