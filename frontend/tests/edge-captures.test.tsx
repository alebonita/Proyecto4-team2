import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { EdgeCapturesPage, sortNewestFirst } from "../src/edge/pages/EdgeCaptures";
import type { EdgeCapture } from "../src/edge/types";

/** Respuesta con la forma real de GET /edge-captures (AWS-2). */
function capture(id: string, capturedAt: string, extra: Partial<EdgeCapture> = {}): EdgeCapture {
  return {
    capture_id: id,
    captured_at: capturedAt,
    received_at: capturedAt,
    device_id: "laptop-edge-01",
    model_version: "dog-cat-resnet18-1.0.0-int8",
    predicted_class: "dog",
    confidence: 0.973,
    latency_ms: 9.4,
    crop: null,
    image_key: `edge-captures/${id}.jpg`,
    image_url: `https://bucket.s3.amazonaws.com/edge-captures/${id}.jpg?X-Amz-Signature=v1`,
    ...extra,
  };
}

const OLDER = capture("cap-0001", "2026-10-11T18:40:02.000Z", {
  predicted_class: "cat",
  confidence: 0.912,
  crop: { x: 160, y: 120, width: 320, height: 240 },
});
const NEWER = capture("cap-0002", "2026-10-11T18:47:55.000Z");

function page(items: EdgeCapture[], total = items.length) {
  return { items, page: 1, pageSize: 100, total };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function serve(...responses: Array<Response | (() => Response)>) {
  const queue = [...responses];
  const fetcher = vi.fn(async (_url: string, _init?: RequestInit) => {
    const next = queue.length > 1 ? queue.shift() : queue[0];
    if (!next) throw new Error("sin respuesta");
    return typeof next === "function" ? next() : next.clone();
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const edgeCalls = (fetcher: ReturnType<typeof serve>) =>
  fetcher.mock.calls.filter(([url]) => String(url).includes("/edge-captures"));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("POR-2: Capturas Edge se abre desde la navegación y pide las capturas reales a la API", async () => {
  const fetcher = serve(() =>
    json(page([OLDER, NEWER]))
  );
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <App />
    </MemoryRouter>
  );

  const link = screen.getByRole("link", { name: "Capturas Edge" });
  expect(link).toHaveAttribute("href", "/edge/captures");
  fireEvent.click(link);

  expect(await screen.findByRole("heading", { name: "Capturas Edge" })).toBeInTheDocument();
  expect(await screen.findAllByRole("article")).toHaveLength(2);
  expect(edgeCalls(fetcher).map(([url]) => url)).toContain(
    "/api/edge-captures?page=1&pageSize=100"
  );
});

it("POR-2: sin datos de ejemplo; cada tarjeta muestra foto, clase, confianza, fecha, ID, dispositivo y versión", async () => {
  serve(json(page([OLDER, NEWER])));
  render(<EdgeCapturesPage />);

  const cards = await screen.findAllByRole("article");
  expect(screen.queryByText(/datos de prueba/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("note")).not.toBeInTheDocument();

  // Más reciente primero.
  expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual([
    "Captura cap-0002",
    "Captura cap-0001",
  ]);
  const [, olderCard] = cards;
  if (!olderCard) throw new Error("falta la tarjeta");
  const card = within(olderCard);
  expect(card.getByRole("img")).toHaveAttribute("src", OLDER.image_url);
  expect(card.getByText("cat")).toBeInTheDocument();
  expect(card.getByText("91.2 %")).toBeInTheDocument();
  expect(card.getByText("cap-0001")).toBeInTheDocument();
  expect(card.getByText("laptop-edge-01")).toBeInTheDocument();
  expect(card.getByText("dog-cat-resnet18-1.0.0-int8")).toBeInTheDocument();
  expect(olderCard.querySelector("time")).toHaveAttribute("datetime", OLDER.captured_at);
  expect(card.getByText("320×240 en (160, 120)")).toBeInTheDocument();
});

it("POR-2: el orden no depende del orden en que llegan", () => {
  const sorted = sortNewestFirst([OLDER, NEWER]);
  expect(sorted.map((c) => c.capture_id)).toEqual(["cap-0002", "cap-0001"]);
});

it("POR-2: mensaje de carga mientras responde la API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {}))
  );
  render(<EdgeCapturesPage />);
  expect(screen.getByRole("status", { name: "Cargando capturas" })).toBeInTheDocument();
});

it("POR-2: lista vacía con mensaje útil", async () => {
  serve(json(page([])));
  render(<EdgeCapturesPage />);
  expect(await screen.findByText("Todavía no hay capturas")).toBeInTheDocument();
});

it("POR-2: error del servidor con mensaje, y Reintentar vuelve a pedir", async () => {
  const fetcher = serve(json({ error: "x" }, 500), json(page([NEWER])));
  render(<EdgeCapturesPage />);

  expect(await screen.findByText("No se pudieron cargar las capturas.")).toBeInTheDocument();
  expect(screen.getByText("El servidor respondió con un error (500).")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findAllByRole("article")).toHaveLength(1);
  expect(edgeCalls(fetcher)).toHaveLength(2);
});

it("POR-2: una respuesta con otro formato se muestra como error, no se pinta", async () => {
  serve(json({ items: [{ capture_id: "x" }], page: 1, pageSize: 100, total: 1 }));
  render(<EdgeCapturesPage />);
  expect(
    await screen.findByText("La respuesta del servidor no coincide con el formato esperado.")
  ).toBeInTheDocument();
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});

it("POR-2: Actualizar vuelve a pedir las capturas y usa las URL de foto nuevas", async () => {
  const renewed = { ...NEWER, image_url: NEWER.image_url.replace("v1", "v2") };
  const fetcher = serve(json(page([NEWER])), json(page([renewed])));
  render(<EdgeCapturesPage />);
  expect(await screen.findByRole("img")).toHaveAttribute("src", NEWER.image_url);

  fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
  await screen.findByRole("img");
  expect(await screen.findByRole("img")).toHaveAttribute("src", renewed.image_url);
  expect(edgeCalls(fetcher)).toHaveLength(2);
});

it("POR-2: renueva las URL antes de que caduquen sin quitar las tarjetas", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const renewed = { ...NEWER, image_url: NEWER.image_url.replace("v1", "v2") };
  const fetcher = serve(json(page([NEWER])), json(page([renewed])));
  render(<EdgeCapturesPage autoRenewMs={14 * 60 * 1000} />);
  expect(await screen.findByRole("img")).toHaveAttribute("src", NEWER.image_url);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(14 * 60 * 1000);
  });
  expect(screen.getAllByRole("article")).toHaveLength(1);
  expect(screen.queryByRole("status", { name: "Cargando capturas" })).not.toBeInTheDocument();
  expect(await screen.findByRole("img")).toHaveAttribute("src", renewed.image_url);
  expect(edgeCalls(fetcher)).toHaveLength(2);
});

it("POR-2: si una foto no carga (enlace caducado) la tarjeta lo dice, y Actualizar la recupera", async () => {
  const renewed = { ...NEWER, image_url: NEWER.image_url.replace("v1", "v2") };
  serve(json(page([NEWER])), json(page([renewed])));
  render(<EdgeCapturesPage />);

  fireEvent.error(await screen.findByRole("img"));
  expect(screen.getByText("No se pudo cargar la foto")).toBeInTheDocument();
  expect(screen.getByText(/caduca a los 15 minutos/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
  expect(await screen.findByRole("img", { name: /clasificada como dog/ })).toHaveAttribute(
    "src",
    renewed.image_url
  );
  expect(screen.queryByText("No se pudo cargar la foto")).not.toBeInTheDocument();
});

it("POR-2: si hay más capturas que las que caben en la página, lo dice", async () => {
  serve(json(page([NEWER, OLDER], 250)));
  render(<EdgeCapturesPage />);
  expect(await screen.findByText("Las 2 más recientes de 250 capturas")).toBeInTheDocument();
});
