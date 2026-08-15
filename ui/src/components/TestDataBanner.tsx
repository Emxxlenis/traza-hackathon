import { USE_MOCK } from "../api/client";

/** Banner shown ONLY in mock mode: everything on screen comes from fixtures. */
export function TestDataBanner() {
  if (!USE_MOCK) return null;
  return (
    <div className="test-banner" role="status">
      <strong>DATOS DE PRUEBA</strong>
      <span> — pendiente de integrar contra datos reales de Croma. Todas las entidades son ficticias.</span>
    </div>
  );
}
