import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { MOCK_EDGE_CAPTURES } from "../src/edge/mockCaptures";
import { EdgeCapturesPage, sortNewestFirst } from "../src/edge/pages/EdgeCaptures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("POR-1: Capturas Edge se abre desde la navegación del portal", async () => {
  // El tablero de inicio hace fetch; aquí no importa su respuesta.
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <App />
    </MemoryRouter>,
  );

  const link = screen.getByRole("link", { name: "Capturas Edge" });
  expect(link).toHaveAttribute("href", "/edge/captures");
  fireEvent.click(link);

  expect(await screen.findByRole("heading", { name: "Capturas Edge" })).toBeInTheDocument();
  expect(await screen.findAllByRole("article")).toHaveLength(MOCK_EDGE_CAPTURES.length);
  expect(screen.getByRole("link", { name: "Capturas Edge" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

it("POR-1: muestra tarjetas con datos de prueba, de la más reciente a la más antigua", async () => {
  render(<EdgeCapturesPage />);

  expect(await screen.findByRole("note")).toHaveTextContent("Datos de prueba");
  const cards = await screen.findAllByRole("article");
  const expected = sortNewestFirst(MOCK_EDGE_CAPTURES).map((c) => `Captura ${c.capture_id}`);
  expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual(expected);

  const [firstCard] = cards;
  const [newest] = sortNewestFirst(MOCK_EDGE_CAPTURES);
  if (!firstCard || !newest) throw new Error("Faltan capturas de prueba");
  const first = within(firstCard);
  expect(first.getByText(newest.capture_id)).toBeInTheDocument();
  expect(first.getByText(newest.device_id)).toBeInTheDocument();
  expect(first.getByText(newest.model_version)).toBeInTheDocument();
  expect(first.getByText(newest.predicted_class)).toBeInTheDocument();
  expect(first.getByText(`${(newest.confidence * 100).toFixed(1)} %`)).toBeInTheDocument();
  expect(first.getByRole("img")).toHaveAttribute("src", newest.image_url);
});

it("POR-1: el orden no depende del orden de llegada", () => {
  const sorted = sortNewestFirst(MOCK_EDGE_CAPTURES);
  const times = sorted.map((c) => new Date(c.captured_at).getTime());
  expect(times).toEqual([...times].sort((a, b) => b - a));
});

it("POR-1: lista vacía con mensaje útil", async () => {
  render(<EdgeCapturesPage load={() => Promise.resolve([])} isMock={false} />);
  expect(await screen.findByText("Todavía no hay capturas")).toBeInTheDocument();
  expect(screen.queryByRole("note")).not.toBeInTheDocument();
});

it("POR-1: error con mensaje y Reintentar vuelve a consultar", async () => {
  const load = vi
    .fn()
    .mockRejectedValueOnce(new Error("Sin conexión con el portal."))
    .mockResolvedValueOnce(MOCK_EDGE_CAPTURES);
  render(<EdgeCapturesPage load={load} isMock={false} />);

  expect(await screen.findByText("No se pudieron cargar las capturas.")).toBeInTheDocument();
  expect(screen.getByText("Sin conexión con el portal.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findAllByRole("article")).toHaveLength(MOCK_EDGE_CAPTURES.length);
  expect(load).toHaveBeenCalledTimes(2);
});

it("POR-1: Actualizar vuelve a pedir las capturas", async () => {
  const load = vi.fn(() => Promise.resolve(MOCK_EDGE_CAPTURES));
  render(<EdgeCapturesPage load={load} isMock={false} />);
  await screen.findAllByRole("article");

  fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
  await screen.findAllByRole("article");
  expect(load).toHaveBeenCalledTimes(2);
});
