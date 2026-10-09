import { beforeAll, describe, expect, it } from 'vitest';

/**
 * AWS-2: el orden de GET /edge-captures lo decide el SQL. Se revisa la consulta que
 * genera Drizzle (`toSQL`), sin conectarse a MariaDB.
 */

let buildEdgeCaptureListQuery: typeof import('../src/data/repositories/edge-capture.repository.js').buildEdgeCaptureListQuery;

beforeAll(async () => {
  process.env.DATABASE_URL = 'mysql://root:ci@127.0.0.1:3306/image_repo';
  ({ buildEdgeCaptureListQuery } = await import(
    '../src/data/repositories/edge-capture.repository.js'
  ));
});

describe('AWS-2: consulta de capturas', () => {
  it('ordena de la más reciente a la más antigua por captured_at, con id de desempate', () => {
    const { sql } = buildEdgeCaptureListQuery({ limit: 20, offset: 0 }).toSQL();

    expect(sql).toMatch(
      /order by `edge_captures`\.`captured_at` desc, `edge_captures`\.`id` desc limit \?/,
    );
  });

  it('pagina con limit y offset', () => {
    const { sql, params } = buildEdgeCaptureListQuery({ limit: 10, offset: 30 }).toSQL();

    expect(sql).toMatch(/limit \? offset \?$/);
    expect(params).toEqual([10, 30]);
  });

  it('devuelve las columnas del recorte', () => {
    const { sql } = buildEdgeCaptureListQuery({ limit: 1, offset: 0 }).toSQL();

    for (const column of ['crop_x', 'crop_y', 'crop_width', 'crop_height']) {
      expect(sql).toContain(`\`${column}\``);
    }
  });
});
