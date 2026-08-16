/**
 * Impresión nativa del expediente (sin librerías): el informe PDF es la misma
 * página con la plantilla @media print de index.css.
 *
 * Para que el papel contenga TODO el expediente —leyenda, capas de auditoría,
 * "Ver detalle técnico", "Ver ruta de la investigación"— se abren todos los
 * <details> antes de imprimir y se restaura el estado exacto que tenía el
 * lector al terminar.
 */
export function printCaseFile(): void {
  const detailsList = Array.from(
    document.querySelectorAll<HTMLDetailsElement>(".case-file details"),
  );
  // Estado previo de cada <details>, apareado con su nodo (no por índice).
  const saved = detailsList.map((d) => [d, d.open] as const);

  let restored = false;
  const restoreOnce = () => {
    if (restored) return;
    restored = true;
    for (const [d, wasOpen] of saved) d.open = wasOpen;
  };

  for (const d of detailsList) d.open = true;

  window.addEventListener("afterprint", restoreOnce, { once: true });
  window.print();
  // Fallback para navegadores sin afterprint: en ellos window.print() es
  // bloqueante, así que restaurar justo después también es correcto. Donde
  // el evento existe, la restauración espera a afterprint (el guard evita
  // restaurar dos veces).
  if (!("onafterprint" in window)) restoreOnce();
}
