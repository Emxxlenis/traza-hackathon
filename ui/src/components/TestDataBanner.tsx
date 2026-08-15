import { useEffect } from "react";
import { USE_MOCK } from "../api/client";

/** Banner shown ONLY in mock mode: everything on screen comes from fixtures. */
export function TestDataBanner() {
  // El título estático de index.html es neutro; el sufijo de prueba solo existe en mock.
  useEffect(() => {
    if (USE_MOCK) document.title = "TRAZA — expediente de investigación (datos de prueba)";
  }, []);
  if (!USE_MOCK) return null;
  return (
    <div className="test-banner" role="status">
      <strong>DATOS DE PRUEBA</strong>
      <span> — pendiente de integrar contra datos reales de Croma. Todas las entidades son ficticias.</span>
    </div>
  );
}
