// Utilidad de demo: render estático de un expediente guardado (JSON del contrato v0.1)
// para generar capturas de respaldo. Uso:
//   npx tsx --tsconfig tsconfig.ssr.json ssr-capture.tsx <case.json> <css-abs> <out.html>
//   google-chrome --headless=new --screenshot=<out.png> --window-size=1280,3200 file://<out.html>
import * as React from "react";
import { readFileSync, writeFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { CaseFileView } from "./src/components/CaseFileView";
import type { CaseFile } from "./src/types/caseFile";

const [, , jsonPath, cssHref, outPath] = process.argv;
const caseFile = JSON.parse(readFileSync(jsonPath, "utf8")) as CaseFile;

const body = renderToStaticMarkup(
  <div className="app">
    <header className="app-header">
      <h1 className="app-title">TRAZA</h1>
      <p className="app-tagline">Tú traes la pregunta. TRAZA hace la investigación.</p>
    </header>
    <main className="app-main">
      <CaseFileView caseFile={caseFile} onNewInvestigation={() => {}} />
    </main>
    <footer className="app-footer">
      <p>Datos: fuentes oficiales vía Croma.</p>
      <p>TRAZA no emite veredictos: muestra evidencia y de dónde viene cada pieza.</p>
    </footer>
  </div>,
);

const html = `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><link rel="stylesheet" href="${cssHref}"></head>
<body>${body}</body></html>`;
writeFileSync(outPath, html);
console.log(`escrito: ${outPath}`);
