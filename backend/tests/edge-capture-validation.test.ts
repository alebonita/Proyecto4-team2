import { describe, expect, it } from 'vitest';

import {
  buildEdgeCaptureKey,
  edgeCaptureFieldsSchema,
} from '../src/logic/edge-capture.validation.js';

/**
 * AWS-1: los campos llegan como texto en multipart/form-data, tal como los manda
 * el celular.
 */
const fields = {
  capture_id: '7f3c2a10-9b1e-4c6d-8e2f-0a1b2c3d4e5f',
  captured_at: '2026-10-08T15:04:05.123-06:00',
  device_id: 'pixel-7-equipo',
  model_version: '1.0.0-int8',
  predicted_class: 'dog',
  confidence: '0.93',
  latency_ms: '41.7',
};

describe('AWS-1: validación de los campos de una captura', () => {
  it('acepta una captura válida y convierte números y fecha', () => {
    const parsed = edgeCaptureFieldsSchema.parse(fields);

    expect(parsed.confidence).toBe(0.93);
    expect(parsed.latency_ms).toBe(41.7);
    expect(parsed.captured_at.toISOString()).toBe('2026-10-08T21:04:05.123Z');
  });

  it.each([
    ['0', 0],
    ['1', 1],
  ])('acepta confidence en el límite (%s)', (value, expected) => {
    expect(edgeCaptureFieldsSchema.parse({ ...fields, confidence: value }).confidence).toBe(
      expected,
    );
  });

  it.each([
    ['confidence mayor que 1', { confidence: '1.01' }],
    ['confidence negativa', { confidence: '-0.1' }],
    ['confidence vacía (no debe valer 0)', { confidence: '' }],
    ['confidence que no es número', { confidence: 'alta' }],
    ['una clase que el modelo no predice', { predicted_class: 'bird' }],
    ['latency_ms negativa', { latency_ms: '-1' }],
    ['captured_at sin zona horaria', { captured_at: '2026-10-08 15:04:05' }],
    ['capture_id con barras (no es una key segura)', { capture_id: '../otra/key' }],
    ['capture_id de más de 64 caracteres', { capture_id: 'a'.repeat(65) }],
    ['device_id vacío', { device_id: '   ' }],
    ['model_version vacío', { model_version: '' }],
  ])('rechaza %s', (_label, changes) => {
    expect(edgeCaptureFieldsSchema.safeParse({ ...fields, ...changes }).success).toBe(false);
  });

  it.each(['capture_id', 'captured_at', 'device_id', 'model_version', 'predicted_class'])(
    'rechaza una captura sin %s',
    (field) => {
      const { [field as keyof typeof fields]: _omitted, ...rest } = fields;
      expect(edgeCaptureFieldsSchema.safeParse(rest).success).toBe(false);
    },
  );

  it('la key de la foto es fija por capture_id y queda bajo edge-captures/', () => {
    expect(buildEdgeCaptureKey('abc-123')).toBe('edge-captures/abc-123.jpg');
  });
});
