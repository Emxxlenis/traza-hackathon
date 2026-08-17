# TRAZA

> Tú traes la pregunta. TRAZA hace la investigación.

TRAZA es un agente de investigación que convierte preguntas sobre la contratación pública
colombiana en expedientes verificables.

La información pública ya existe. El problema es que investigarla exige saber dónde buscar, cómo
conectar fuentes distintas y cómo distinguir lo que los datos realmente prueban de lo que
inferimos a partir de ellos.

TRAZA está construido para quitar esa barrera.

No acusamos. Investigamos.

## Pruébalo

Demo en vivo: https://traza-6yc3.onrender.com

Haz una pregunta como:

> "¿Por qué esta empresa concentra sus contratos en esta entidad?"

TRAZA identifica la entidad, decide qué investigar a continuación, consulta las fuentes oficiales
colombianas a través de Croma, conecta la evidencia y produce un expediente auditable.

## El problema

Los datos del Estado pueden ser públicos sin ser realmente accesibles.

Un ciudadano que investiga una obra pública puede empezar sin más que el nombre de una empresa.

Desde ahí, responder una pregunta aparentemente simple puede requerir:

```
Nombre de la empresa
        ↓
      RUES
        ↓
NIT / representantes
        ↓
      SECOP
        ↓
Contratos / entidades / montos
        ↓
Procuraduría / Contraloría
        ↓
   Cruce de datos
        ↓
   Interpretación
```

La información existe.

La capa de investigación, no.

Eso crea una brecha entre:

- tener el derecho a acceder a la información pública

y

- tener el conocimiento técnico necesario para investigarla.

TRAZA está diseñado para cerrar esa brecha.

## Qué es TRAZA

TRAZA no es un chatbot que busca en bases de datos del Estado y resume los resultados.

Es un agente de investigación.

Dada una pregunta, TRAZA puede:

- Identificar y desambiguar empresas colombianas.
- Determinar qué fuentes son relevantes para la investigación.
- Seguir entidades descubiertas durante la investigación.
- Consultar múltiples fuentes oficiales del Estado.
- Calcular concentración contractual de forma determinista.
- Distinguir hechos directos de hallazgos derivados.
- Preservar la evidencia detrás de cada hallazgo.
- Explicar qué no permite concluir la evidencia disponible.
- Sugerir próximos pasos concretos para seguir investigando.

El resultado no es simplemente una respuesta.

Es un expediente de investigación.

## Por qué Croma

Croma no es una fuente de datos externa que casualmente usamos.

Croma es parte de la infraestructura que hace posible a TRAZA.

Hoy TRAZA accede a cuatro fuentes oficiales colombianas a través de Croma:

| Fuente | Para qué la usa TRAZA |
|---|---|
| RUES | Identidad de la empresa, estado de matrícula, actividad económica y representantes legales |
| SECOP | Contratos públicos, proveedores, entidades contratantes y valores de contrato |
| Procuraduría | Antecedentes disciplinarios |
| Contraloría | Antecedentes de responsabilidad fiscal |

Sin Croma tendríamos que construir y mantener integraciones separadas para cada fuente antes de
siquiera empezar a construir la experiencia de investigación.

Con Croma:

```
                 TRAZA
                   │
                   ▼
                 CROMA
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
      RUES       SECOP    PROCURADURÍA
                              │
                         CONTRALORÍA
```

Eso nos deja concentrarnos en el problema más difícil:

¿Qué debería investigar un agente una vez que los datos del Estado son accesibles por programa?

Croma resuelve el acceso. TRAZA convierte el acceso en investigación.

## Cómo funciona

```
Pregunta del usuario
      │
      ▼
┌───────────────┐
│    Agente     │
│de investigación│
└───────┬───────┘
        │
        │ decide qué investigar a continuación
        ▼
┌────────────────────────┐
│         CROMA          │
│ RUES · SECOP · ...     │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Reducers deterministas │
│ normalización + cálculo│
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│   Capa de evidencia    │
│    DIRECT / DERIVED    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│     Verificación       │
└───────────┬────────────┘
            │
            ▼
       Expediente
```

El principio arquitectónico importante es:

**El LLM decide dónde investigar. El código decide qué se puede afirmar.**

El modelo no hace la aritmética final ni genera evidencia libremente.

Los hallazgos derivados se calculan de forma determinista y se verifican antes de poder entrar al
expediente final.

## Evidencia, no acusaciones

TRAZA deliberadamente no produce:

- scores de riesgo,
- probabilidades de corrupción,
- acusaciones,
- conclusiones sin sustento.

En cambio, cada hallazgo pertenece a una de dos categorías.

### HECHO

Algo afirmado directamente por una fuente.

Ejemplo:

> "La empresa está registrada como activa."

El expediente conserva la fuente y el campo exacto.

### INFERENCIA

Algo calculado a partir de uno o más registros de fuente.

Ejemplo:

> "El 79,0% del valor contractual identificado corresponde al Distrito de Cali."

El expediente conserva:

- `calculation` — la fracción cruda que sustenta el porcentaje.
- `sources` — los registros de contratos usados en el cálculo.
- `calculation_steps` — las operaciones deterministas que reproducen el resultado.

Y TRAZA reporta explícitamente:

**QUÉ NO SABEMOS**

Porque la ausencia de evidencia no es evidencia de ausencia, y la concentración contractual no es
prueba de corrupción.

## Ejemplo de investigación

Un usuario puede preguntar:

> "¿Por qué esta empresa concentra sus contratos en el Distrito de Cali?"

TRAZA puede:

1. Identificar la empresa a través de RUES.
2. Recuperar su historial de contratación pública a través de SECOP.
3. Identificar las entidades asociadas a esos contratos.
4. Calcular la concentración contractual.
5. Seguir las entidades relevantes descubiertas durante la investigación.
6. Revisar los antecedentes disciplinarios y fiscales disponibles.
7. Construir un expediente respaldado por evidencia.

En un caso probado:

- 79,0% del valor contractual identificado correspondió al Distrito de Cali.
- Una segunda agregación determinista mostró 74,4% correspondiente específicamente al DATIC.

Son cálculos sobre registros recuperados, no scores de riesgo generados por un LLM.

## En qué se diferencia de un chatbot

| Chatbot tradicional | TRAZA |
|---|---|
| Responde una pregunta | Conduce una investigación |
| Conversación | Ruta de investigación |
| Citas genéricas | Evidencia adjunta a cada hallazgo |
| Puede mezclar hechos e inferencia | HECHO ≠ INFERENCIA |
| Razonamiento generado por el LLM | Verificación determinista |
| Respuesta final | Expediente auditable |
| Suele ocultar la incertidumbre | Limitaciones explícitas |

El objetivo no es una IA que suene segura.

El objetivo es una investigación que se pueda comprobar.

## Estado de producción

TRAZA está desplegado y funcional.

Implementación verificada actual:

- 161 tests automatizados
- 4 fuentes oficiales del Estado colombiano
- 8 consultas máximas por investigación
- 10 entidades máximas
- Profundidad máxima de investigación: 3
- Integración real con la API de Croma
- Desambiguación de entidades
- Cálculos de evidencia deterministas
- Verificación de la evidencia derivada
- Cuentas de usuario para investigar (ver abajo)
- Rate limiting
- Manejo controlado de fuentes caídas
- UI compatible con móvil
- Despliegue single-origin FastAPI + React

El sistema también fue probado contra escenarios reales de falla, incluidas fuentes caídas y
resultados vacíos.

Cuando una fuente falla, TRAZA no rellena el vacío en silencio.

Le dice al usuario que la investigación es parcial y explica la limitación.

## Cuentas

Investigar requiere una cuenta; leer no.

Cada investigación consulta fuentes oficiales y consume tokens de un modelo, así que tiene un
costo real por pregunta. La cuenta es lo que hace que ese costo sea atribuible en vez de
anónimo. Lo que no cuesta nada queda abierto:

| Sin cuenta | Con cuenta |
|---|---|
| Portada, documentación y expediente de ejemplo | Investigaciones reales contra las 4 fuentes |

El registro es abierto: correo y contraseña, sin invitación. Cómo está hecho:

- Contraseñas con **Argon2id** (m=19 MiB, t=2, p=1 — mínimo recomendado por OWASP).
- Sesión en **cookie HttpOnly**: el token nunca queda al alcance de JavaScript, así que un XSS
  no puede robarla. En el servidor se guarda el **hash** del token, no el token.
- Cerrar sesión **revoca de verdad**: borra la fila, no solo la cookie.
- Login y registro con límite de intentos por IP (fuerza bruta).
- Un request sin sesión sale con 401 **sin gastar cupo** del rate limit de investigaciones.
- El correo no se verifica (no hay servidor de correo): la cuenta acota el uso, no comprueba
  la identidad de quien se registra.

Las cuentas viven en Postgres, configurado con `DATABASE_URL`. Sin esa variable el backend usa
SQLite local, que sirve para desarrollar pero **no** para producción: en un contenedor efímero
(Render free) las cuentas se borrarían en cada redeploy y en cada arranque tras el spin-down.
`GET /health` publica `accounts_persistent` para verificar desde afuera cuál de los dos está
activo.

## Stack técnico

**Backend**

- Python
- FastAPI
- Pydantic
- SQLAlchemy + Postgres (cuentas)
- Cliente HTTP para Croma
- Tool-calling de LLM

**Frontend**

- React
- TypeScript
- UI responsive

**Infraestructura**

- Docker
- Render
- Despliegue single-origin

**IA**

El loop de investigación usa un LLM a través de una abstracción de proveedor, de modo que la
arquitectura de investigación no queda acoplada a un único proveedor de modelos.

## Estructura del repositorio

```
traza-hackathon/
│
├── backend/
│   ├── agent/           loop, tools, reducers, providers
│   ├── croma_client/    transporte hacia la API de Croma
│   ├── evidence/        modelos de evidencia y verificación
│   ├── auth/            cuentas: modelos, sesiones y endpoints
│   ├── app/             API HTTP (FastAPI)
│   └── tests/
│
├── ui/                  React + Vite
│
├── docs/                contratos de datos y notas técnicas
│
├── Dockerfile
└── README.md
```

La arquitectura está separada intencionalmente en torno al ciclo de vida de la investigación:

```
planear → recuperar → reducir → verificar → presentar
```

## Correr localmente

Backend (requiere Python 3.12+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env   # completar claves
uvicorn app.main:app --reload
```

UI:

```bash
cd ui
npm install
npm run dev
```

Configuración vía `.env` en la raíz — ver `.env.example`.

Notas:

- Las cuentas usan SQLite local (`traza-auth.db`, ignorado por git) mientras no definas
  `DATABASE_URL`. No hace falta instalar Postgres para desarrollar.

- La UI llama al backend en `http://localhost:8000` por defecto; se cambia con `VITE_API_URL`
  (por ejemplo en `ui/.env.local`) si ese puerto está ocupado — correr entonces
  `uvicorn app.main:app --port 8010`.
- `VITE_USE_MOCK=1` corre la UI contra fixtures ficticios (sin backend), con banner de
  "DATOS DE PRUEBA" visible.

## Alcance

El MVP actual se enfoca en investigar empresas colombianas en el contexto de la contratación
pública.

Las fuentes actuales vía Croma son:

- RUES
- SECOP
- Procuraduría
- Contraloría

Iteraciones futuras podrían incorporar fuentes adicionales como registros judiciales y de
supervisión societaria, además de otros países soportados por la infraestructura de datos
subyacente.

## Roadmap

**Siguiente**

- Más fuentes del Estado.
- Investigaciones persistentes.
- Compartir y exportar expedientes.
- Grafos de evidencia más ricos.
- Rutas de investigación más avanzadas.

**Largo plazo**

TRAZA podría evolucionar de:

investigar una empresa

hacia:

investigar relaciones a través de la información pública.

La interacción de fondo sigue siendo la misma:

```
Pregunta
   ↓
Investigación
   ↓
Evidencia
   ↓
Expediente
```

## Filosofía

Los datos públicos no deberían solo estar disponibles.

Deberían ser investigables.

TRAZA está construido sobre un principio simple:

**No acusamos. Investigamos.**

## Construido para el Croma GOV-TECH AI Hackathon

TRAZA fue construido para el Croma GOV-TECH AI Hackathon, enfocado en convertir datos del Estado
en productos útiles.

Croma provee la infraestructura que le permite a TRAZA acceder a múltiples fuentes del Estado por
programa.

TRAZA construye encima la capa de investigación.

## Enlaces

- Producto en vivo: https://traza-6yc3.onrender.com
- Repositorio: https://github.com/Emxxlenis/traza-hackathon
- Croma: https://usecroma.com/

---

**TRAZA**

Tú traes la pregunta. TRAZA hace la investigación.
