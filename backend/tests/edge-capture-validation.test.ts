import { describe, expect, it } from 'vitest';

import {
  buildEdgeCaptureKey,
  edgeCaptureFieldsSchema,
  edgeCaptureListQuerySchema,
} from '../src/logic/edge-capture.validation.js';

/**
 * AWS-1/AWS-2: los campos llegan como texto en multipart/form-data, tal como los manda
 * el dispositivo edge (laptop) con su programa en Python.
 */
const fields = {
  capture_id: '7f3c2a10-9b1e-4c6d-8e2f-0a1b2c3d4e5f',
  captured_at: '2026-10-08T15:04:05.123-06:00',
  device_id: 'laptop-equipo',
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

describe('AWS-2: campo opcional crop', () => {
  it('sin crop (o vacío) la captura es válida y no lleva recorte', () => {
    expect(edgeCaptureFieldsSchema.parse(fields).crop).toBeUndefined();
    expect(edgeCaptureFieldsSchema.parse({ ...fields, crop: '  ' }).crop).toBeUndefined();
  });

  it('acepta el recorte como texto JSON', () => {
    const parsed = edgeCaptureFieldsSchema.parse({
      ...fields,
      crop: '{"x":10,"y":20.5,"width":100,"height":80}',
    });

    expect(parsed.crop).toEqual({ x: 10, y: 20.5, width: 100, height: 80 });
  });

  it.each([
    ['JSON mal formado', '{"x":10,'],
    ['un número en vez de un objeto', '42'],
    ['x negativa', '{"x":-1,"y":0,"width":10,"height":10}'],
    ['ancho cero', '{"x":0,"y":0,"width":0,"height":10}'],
    ['alto negativo', '{"x":0,"y":0,"width":10,"height":-5}'],
    ['una coordenada faltante', '{"x":0,"y":0,"width":10}'],
    ['una coordenada como texto', '{"x":"0","y":0,"width":10,"height":10}'],
    ['campos de más', '{"x":0,"y":0,"width":10,"height":10,"z":1}'],
  ])('rechaza un crop con %s', (_label, crop) => {
    expect(edgeCaptureFieldsSchema.safeParse({ ...fields, crop }).success).toBe(false);
  });
});

describe('AWS-2: paginación de la consulta', () => {
  it('usa page=1 y pageSize=20 si no se indican', () => {
    expect(edgeCaptureListQuerySchema.parse({})).toEqual({ page: 1, pageSize: 20 });
  });

  it('convierte los query params', () => {
    expect(edgeCaptureListQuerySchema.parse({ page: '3', pageSize: '50' })).toEqual({
      page: 3,
      pageSize: 50,
    });
  });

  it.each([
    ['page 0', { page: '0' }],
    ['page decimal', { page: '1.5' }],
    ['pageSize mayor que 100', { pageSize: '101' }],
    ['pageSize no numérico', { pageSize: 'muchos' }],
  ])('rechaza %s', (_label, query) => {
    expect(edgeCaptureListQuerySchema.safeParse(query).success).toBe(false);
  });
});
