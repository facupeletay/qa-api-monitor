import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import sampleHistoryRaw from "../../sample-history.json";
import { App } from "../App";

describe("App component states", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("muestra el estado de carga inicialmente", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}),
    );

    render(<App historyUrl="/test/history.json" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(
      screen.getByText(/Cargando historial de monitoreo/i),
    ).toBeInTheDocument();
  });

  it("muestra el estado de error cuando falla el fetch de history.json", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as Response);

    render(<App historyUrl="/test/history.json" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Error al cargar los datos/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Error HTTP 500/i)).toBeInTheDocument();
  });

  it("muestra 'todavía no hay datos' cuando history.json está vacío o devuelve 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({}),
    } as Response);

    render(<App historyUrl="/test/history.json" />);

    await waitFor(() => {
      expect(
        screen.getByText(/Todavía no hay datos disponibles en el historial/i),
      ).toBeInTheDocument();
    });
  });

  it("renderiza métricas, selector de ventana e incidentes usando cache: 'no-store'", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sampleHistoryRaw,
    } as Response);

    render(<App historyUrl="/test/history.json" />);

    await waitFor(() => {
      expect(screen.getByText("Todo OK")).toBeInTheDocument();
    });

    expect(fetchSpy).toHaveBeenCalledWith("/test/history.json", {
      cache: "no-store",
    });

    // Verifica que las tarjetas de los dos monitores estén visibles
    expect(
      screen.getAllByText("DolarApi - Dolar Oficial").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Open-Meteo - Clima CABA").length,
    ).toBeGreaterThan(0);

    // En la ventana por defecto (7d) hay 4 incidentes
    expect(screen.getByText("4 incidentes")).toBeInTheDocument();

    // Al cambiar a 24 h, se actualiza a 1 incidente
    const btn24h = screen.getByRole("button", { name: "24 h" });
    fireEvent.click(btn24h);
    expect(screen.getByText("1 incidente")).toBeInTheDocument();

    // Al cambiar a 30 días, se actualiza a 5 incidentes
    const btn30d = screen.getByRole("button", { name: "30 días" });
    fireEvent.click(btn30d);
    expect(screen.getByText("5 incidentes")).toBeInTheDocument();
  });
});
