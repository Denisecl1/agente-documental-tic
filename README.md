# 2.3 Agente documental con Google Drive — Archivo TIC IA

Proyecto académico de **Inteligencia artificial aplicada a las TIC**, Tecnológico Nacional de México, Instituto Tecnológico de Pachuca. Continuación de **2.2 Agente investigador**: se reemplaza la búsqueda pública Web Search por recuperación documental de **Google Drive**, **OpenAI Vector Stores** y **File Search (RAG)**.

- **Autora:** Diana Denise Campos Lozano
- **Carrera:** Ingeniería en Tecnologías de la Información y Comunicaciones
- **Sitio desplegado en Vercel:** [https://agente-documental-tic-lime.vercel.app](https://agente-documental-tic-lime.vercel.app)

---

## Propósito pedagógico

El alumno comprenderá que una organización necesita consultar documentos propios y autorizados, no solamente Internet. Identificará el papel de OAuth, Google Drive API, sincronización, indexación semántica, recuperación de contexto, respuestas sustentadas y trazabilidad mediante fuentes. Comparará respuestas **sin** y **con** acceso documental, observará qué sucede al modificar una fuente y realizará todas las pruebas iniciales en **localhost**. El despliegue a Vercel es un **reto autónomo**, no una configuración lista para producción.

## Arquitectura

- `app/main.py`: FastAPI, endpoints REST, frontend estático y protección local/serverless de sincronización.
- `app/core/config.py`: configuración y secretos cargados desde `.env` o variables de entorno del servidor.
- `app/models/documento.py`: modelos de solicitud y respuesta (`AskRequest`, `Source`, `AskResponse`).
- `app/services/drive_service.py`: OAuth Desktop en local y lectura de credenciales autorizadas por entorno en Serverless, listado limitado a una carpeta y descarga/exportación de archivos.
- `app/services/sync_service.py`: Vector Store, manifiesto de archivos, persistencia de metadatos en atributos de OpenAI, altas, cambios y bajas.
- `app/services/agent_service.py`: Responses API + File Search y fuentes verificadas por anotaciones de archivo (`file_citation`).
- `index.html` y `assets/`: interfaz Bootstrap 5 personalizada y módulos JavaScript.
- `data/manifest.json`: estado local del índice (no se publica).
- `vercel.json`: configuración de enrutamiento y construcción serverless (`@vercel/python`).

## 1. Requisitos

Python 3.11+, VS Code, Git, cuentas de Google Cloud y OpenAI API con créditos, navegador y documentos de prueba autorizados. **Las claves y los archivos de Drive no se incluyen en el ZIP ni en el repositorio.**

## 2. Configuración Google Drive

1. En [Google Cloud Console](https://console.cloud.google.com/), crea un proyecto y habilita **Google Drive API**.
2. Configura **Google Auth Platform**, pantalla de consentimiento y usuarios de prueba si corresponde.
3. Crea credenciales OAuth 2.0 de tipo **Desktop app** y descarga el archivo a la raíz del proyecto como `credentials.json`.
4. Crea una carpeta de Google Drive con **al menos cinco** documentos autorizados. Admite PDF, TXT y Google Docs nativos. Extrae el ID de su URL `/folders/ID`.
5. Este ejercicio utiliza el alcance `drive.readonly` para lectura; puede exigir validaciones adicionales al distribuir una app real. Usa una cuenta y una carpeta de laboratorio sin datos personales.

## 3. Preparar proyecto en Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env`: define `OPENAI_API_KEY`, un `OPENAI_MODEL` compatible con File Search y `GOOGLE_DRIVE_FOLDER_ID`. `VECTOR_STORE_ID` se deja vacío la primera vez: el sistema lo guardará en el manifiesto. No insertes claves en el código ni en el navegador.

## 4. Ejecutar localmente

```powershell
python app.py
```

Abre <http://127.0.0.1:5000>. Usa **Sincronizar desde Drive** para autenticar Google, descargar/exportar los archivos autorizados e indexarlos. La primera ejecución abre el navegador OAuth en la computadora donde está corriendo Python. Después escribe preguntas sobre el contenido. Para ensayar recuperación, desactiva **File Search (RAG)** y repite exactamente la misma pregunta.

**Importante:** la sincronización usa una solicitud HTTP en localhost. Si estableces `LOCAL_ADMIN_KEY`, proporciona la cabecera `X-Admin-Key` mediante Thunder Client para `/api/sync` (el botón web no envía claves administrativas). Ejecuta el backend en `127.0.0.1`, no en `0.0.0.0`.

## 5. Endpoints

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/health` | Comprueba configuración y servidor. |
| GET | `/api/documents` | Documentos ya indexados (manifiesto local o reconstruido desde Vector Store). |
| POST | `/api/sync` | Indexa cambios desde Google Drive hacia OpenAI Vector Store. |
| POST | `/api/ask` | Pregunta con `question` y `use_search`. |

Ejemplo JSON para Thunder Client:

```json
{"question": "¿Qué documentos tratan sobre AWS RDS?", "use_search": true}
```

## 6. Experimentos y Comparación de Resultados (Con vs. Sin File Search)

1. Ejecuta una pregunta muy específica presente en los archivos **sin File Search**.
2. Repite **con File Search**: inspecciona contenido y fuentes (anotaciones verificadas).
3. Prueba temas ausentes: el agente debe declarar insuficiencia de información.
4. Agrega un documento con un dato singular, sincroniza y vuelve a preguntar.
5. Modifica un documento, vuelve a sincronizar y verifica que no se duplican registros en el manifiesto.
6. Elimina un documento de prueba del Drive autorizado, sincroniza y comprueba que desaparece del manifiesto.

| Criterio | Experimento A: Sin File Search (`use_search=false`) | Experimento B: Con File Search (`use_search=true` - RAG) |
|---|---|---|
| **Evidencia** | Nula respecto al repositorio privado; responde solo con conocimiento general preentrenado. | Alta; fundamenta la respuesta en los fragmentos recuperados del Vector Store indexado desde Google Drive. |
| **Pertinencia** | Baja para consultas internas; desconoce el contenido específico de las prácticas de la carpeta. | Alta; responde directamente al contexto académico contenido en los documentos autorizados. |
| **Precisión** | Da definiciones teóricas generales o declara no tener acceso a los archivos mencionados. | Precisa; extrae parámetros, motores, objetivos y diferencias exactas de los documentos indexados. |
| **Referencias / Fuentes** | `sources: []` (0 fuentes mostradas, sin enlaces verificables). | Devuelve citas verificables (`file_citation`) con enlaces directos a los archivos originales en Google Drive. |

**Limitaciones:** las búsquedas RAG pueden generar errores; comprueba siempre las respuestas contra las fuentes. La eliminación del índice tiene **consistencia eventual** y puede tardar en reflejarse. Los resultados sin citas explícitas no se presentan como fuentes. La actualización de un mismo archivo puede crear cargos transitorios mientras se reemplaza el anterior.

## 7. Pruebas automáticas

```powershell
python -m pytest -q
```

Las pruebas son locales y no requieren claves reales ni consumen OpenAI.

## 8. Git/GitHub y Documentación del Reto Autónomo en Vercel

```powershell
git init
git add .
git commit -m "chore: estructura inicial documental"
```

Para lograr que la aplicación funcione de forma segura en el entorno serverless de **Vercel** sin alterar el funcionamiento local ni exponer credenciales en GitHub, se investigaron y resolvieron los siguientes retos técnicos:

1. **Adaptación de FastAPI a Serverless (`vercel.json`):**
   Se configuró `@vercel/python` en `vercel.json` redirigiendo las rutas hacia `app/main.py` para servir tanto los endpoints `/api/*` como los archivos estáticos (`/assets/*`) y la interfaz principal.
2. **Migración de OAuth local a entorno Serverless (`GOOGLE_TOKEN_JSON`):**
   En `localhost`, `InstalledAppFlow.run_local_server()` abre un navegador local y persiste `token.json` en disco. En Vercel no existe entorno gráfico ni almacenamiento persistente en disco para el flujo de escritorio. Se adaptó `DriveService` para que en entorno serverless reconstruya las credenciales OAuth en memoria a partir de la variable de entorno segura `GOOGLE_TOKEN_JSON` y ejecute `creds.refresh(Request())` automáticamente usando el `refresh_token`.
3. **Solución al sistema de archivos efímero (`data/manifest.json` y OpenAI Vector Store Attributes):**
   En Vercel, el sistema de archivos del proyecto es de solo lectura y el directorio temporal (`/tmp`) es efímero (se destruye cuando la instancia serverless se apaga). Para evitar que el inventario de documentos y los enlaces de las citas (`file_citation`) se pierdan entre ejecuciones:
   - Durante la sincronización (`SyncService.sync`), los metadatos de cada documento (`name`, `modified_time`, `mime_type`, `url`) se almacenan directamente en los **`attributes` del archivo dentro del Vector Store de OpenAI**, además de guardarse en caché dentro de `/tmp/manifest.json`.
   - Cuando una instancia serverless nueva atiende `/api/documents` o `/api/ask`, `SyncService.load_manifest()` reconstruye automáticamente el manifiesto consultando `vector_stores.files.list` en OpenAI.
4. **Variables de entorno configuradas en el servidor de Vercel:**
   `OPENAI_API_KEY`, `OPENAI_MODEL`, `GOOGLE_DRIVE_FOLDER_ID`, `VECTOR_STORE_ID` y `GOOGLE_TOKEN_JSON`. Ninguna clave ni token se expone en el frontend (`index.html` / `assets/js`) ni en el repositorio de GitHub.

## 9. Costos y privacidad

OpenAI cobra por el uso de modelos, búsqueda y almacenamiento según su tarifario vigente. No subas a OpenAI documentos confidenciales, datos personales o material sin permiso del propietario. El material descargado se transmite a OpenAI para indexación. Revoca y rota cualquier credencial filtrada, incluso si ya fue borrada de GitHub.

## 10. Conclusiones Personales

- **Agentes de IA y File Search (RAG):** Implementar RAG mediante OpenAI Vector Stores permite que un agente responda fundamentándose estrictamente en documentos privados autorizados de una organización, evitando depender únicamente de información pública de Internet y proporcionando trazabilidad real mediante citas verificables (`file_citation`).
- **Programación Orientada a Objetos (OOP) y FastAPI:** La separación modular en servicios (`DriveService`, `SyncService`, `AgentService`) y modelos de validación Pydantic en FastAPI facilitó depurar cada etapa del flujo documental (autenticación OAuth, sincronización incremental y consulta semántica) de manera ordenada y comprobable con `pytest`.
- **Git/GitHub, Variables de Entorno y Seguridad:** El control de versiones mediante ramas (`feature/agente-documental` y `main`) combinado con un archivo `.gitignore` estricto y variables de entorno asegura que credenciales críticas (`OPENAI_API_KEY`, `credentials.json`, `token.json`) nunca queden comprometidas en el código fuente público.
- **Despliegue Serverless en Vercel:** Se comprendieron las diferencias arquitectónicas entre un servidor local persistente y una infraestructura serverless efímera, resolviendo la persistencia del índice mediante los atributos nativos del Vector Store y la gestión de credenciales desde el entorno del servidor.