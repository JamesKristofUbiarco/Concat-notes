# 📘 Gestor Inteligente de Apuntes: Next.js, FastAPI & LangGraph

Bienvenido al **Gestor Inteligente de Apuntes y Código**. Esta es una aplicación de nivel empresarial y full-stack diseñada en **Mayo de 2026** para tomar notas de cursos, capturar transcripciones de audio, snippets de código y comandos de shell, y procesarlos de manera autónoma utilizando un **Agente cognitivo basado en LangGraph y Google Gemini 3.5 Flash**, con persistencia relacional e indexación semántica en **PostgreSQL con pgvector**.

---

## 🚀 Arquitectura del Proyecto

El ecosistema se compone de cuatro módulos integrados:

1. **Frontend (Next.js + Tailwind CSS + Zod)**:
   - Una interfaz oscura de diseño prémium y ultra-reactiva que permite registrar apuntes interactivos, controlar una cola activa de estudio con drag-and-drop (@dnd-kit) y visualizar fichas sintetizadas en Markdown con resaltado sintáctico. Incluye widgets interactivos para subir imágenes de apoyo y copiar placeholders.
2. **Backend (FastAPI + SQLAlchemy + Pydantic)**:
   - API REST robusta que expone operaciones CRUD, gestiona la subida de imágenes y el almacenamiento local en MinIO, orquesta el agente de IA y ejecuta un **worker automático en segundo plano** que procesa notas pendientes mediante un disparador híbrido (por umbral de acumulación o timeout).
3. **Agente IA (LangGraph + Gemini 3.5 Flash + pgvector)**:
   - Un agente cognitivo representado como un grafo de estados cíclicos (`StateGraph`) con 4 nodos que implementa:
     - **Preprocesamiento**: Escaneo de la transcripción para buscar placeholders `&"codigo:X"`, `&"comando:X"` o `&"imagen:X"` y reemplazarlos por su bloque correspondiente antes de llamar al LLM (con fallback de seguridad si falla).
     - **Contexto (RAG)**: Multi-Query Expansion con Gemini Flash Lite + recuperación vectorial por coseno en `pgvector` con deduplicación.
     - **Herramientas**: Optimizador de código y validador sintáctico de shell CLI (determinístico).
     - **Síntesis (con Chain-of-Thought integrado)**: Planeación, razonamiento pedagógico y redacción final en una sola llamada al LLM usando Structured Output (`AgentOutput`).
     - **Validación Mermaid**: Compilación de diagramas con `mmdc` y bucle de autocorrección (hasta 3 reintentos).
4. **Almacenamiento de Objetos (MinIO / S3)**:
   - Servidor compatible con la API de Amazon S3 que almacena físicamente las imágenes subidas por los usuarios. Las imágenes se analizan con Gemini 3.5 Flash estándar (en memoria) para generar descripciones que alimentan el RAG y la síntesis.

---

## 🛠️ Requisitos e Instalación de Herramientas

Para levantar este proyecto, necesitarás instalar **Docker**, **Node.js** y el gestor de paquetes de Python **`uv`**. A continuación se detalla la instalación por sistema operativo:

### 1. Instalar Docker y Docker Compose
Docker es indispensable para levantar nuestra base de datos relacional PostgreSQL cargada con la extensión de indexación vectorial `pgvector`.

*   **Windows**:
    1. Descarga e instala [Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/).
    2. Asegúrate de habilitar la integración con **WSL 2** (Windows Subsystem for Linux) durante la instalación.
    3. Inicia la aplicación de Docker Desktop para activar el demonio de Docker.
*   **macOS**:
    1. Descarga e instala [Docker Desktop para Mac](https://www.docker.com/products/docker-desktop/) (elige la versión Apple Silicon o Intel según tu chip).
    2. Inicia Docker desde tu Launchpad.
*   **Linux (Ubuntu/Debian)**:
    1. Ejecuta en terminal:
       ```bash
       sudo apt update
       sudo apt install -y docker.io docker-compose-v2
       sudo systemctl enable --now docker
       sudo usermod -aG docker $USER
       ```
    2. Cierra e inicia sesión de nuevo para aplicar los permisos del grupo `docker`.

### 2. Instalar Node.js y npm (Frontend)
Requerido para compilar y servir el dashboard interactivo de Next.js.

*   **Windows**:
    - Descarga el instalador `.msi` de la versión LTS desde [Node.js Official Website](https://nodejs.org/) y sigue el asistente.
*   **macOS / Linux**:
    - Recomendamos usar `nvm` (Node Version Manager) para una gestión óptima:
      ```bash
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
      # Reinicia la terminal
      nvm install --lts
      ```

### 3. Instalar `uv` (Gestor de Paquetes Python para el Backend)
`uv` es el gestor de paquetes de Python ultra-rápido diseñado por Astral que reemplaza a `pip`, `poetry` y `pipenv`.

*   **Windows (PowerShell)**:
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
*   **macOS / Linux**:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

---

## 🐳 Orquestación con Docker Compose (Recomendado)

El orquestador de Docker Compose te permite levantar la infraestructura completa del proyecto (Base de Datos + Backend + Frontend) con un solo comando y sin tener que abrir múltiples terminales.

### 1. Requisitos Previos
Asegúrate de tener el archivo `.env` configurado en la carpeta `backend/` (que contenga tus llaves API de Gemini y Voyage, si deseas utilizarlas).

### 2. Iniciar el Proyecto
Desde la raíz del proyecto, ejecuta el siguiente comando:
```bash
docker compose up --build -d
```

Este comando se encargará de:
1.  Descargar y configurar la base de datos `db` (PostgreSQL 16 + `pgvector`), inicializando el esquema y cargando automáticamente las notas semilla (`seed_data.sql`).
2.  Levantar el servidor de almacenamiento de objetos `storage` (MinIO) en el puerto `9000` (API) y `9001` (Consola Web) con persistencia en el volumen de Docker `miniodata`.
3.  Construir la imagen del `backend` FastAPI (instalando dependencias con `uv`), inicializar el almacenamiento del bucket `notes-images` e inyectar de forma segura tu archivo `backend/.env`.
4.  Construir e iniciar el `frontend` de Next.js en su versión de producción `standalone` en el puerto `3000`.

El sistema estará listo en:
*   **Frontend (Dashboard)**: [http://localhost:3000](http://localhost:3000)
*   **Backend (API & Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
*   **MinIO Console (Almacenamiento)**: [http://localhost:9001](http://localhost:9001) (Credenciales por defecto: `minio_admin` / `minio_password`)

### 3. Comandos de Utilidad
*   **Ver logs**: `docker compose logs -f` (puedes especificar el servicio, ej: `docker compose logs -f backend`)
*   **Apagar servicios**: `docker compose down` (los datos de Postgres y MinIO se conservan en los volúmenes de Docker)
*   **Apagar y limpiar datos**: `docker compose down -v` (elimina el volumen pgdata y miniodata, forzando una inicialización limpia del dump la próxima vez)

---

## ⚙️ Configuración y Puesta en Marcha Manual (Desarrollo)

Sigue estos pasos en orden para levantar la infraestructura completa:

### Paso 1: Levantar la Base de Datos en Docker
1. Abre tu terminal y navega al directorio `db/` del proyecto:
   ```bash
   cd db
   ```
2. Levanta el contenedor de PostgreSQL con la extensión `pgvector`:
   ```bash
   docker compose up -d
   ```
3. Esto levantará una base de datos local en el puerto `5432` con las credenciales por defecto:
   - **Usuario**: `notes_user`
   - **Contraseña**: `notes_password`
   - **Base de Datos**: `notes_db`
   - Las tablas y el índice HNSW se inicializarán de forma autónoma gracias al script `init.sql`.

### Paso 2: Configurar Variables de Entorno del Backend
1. Navega al directorio `backend/`:
   ```bash
   cd ../backend
   ```
2. Copia la plantilla y edita tu archivo `.env`:
   ```bash
   cp .env.template .env
   ```
3. Edita `.env` e ingresa tus API keys:
   ```env
   # URL de conexión de la base de datos PostgreSQL en Docker
   DATABASE_URL=postgresql://notes_user:notes_password@localhost:5432/notes_db
   PORT=8000

   # ==========================================================================
   # INTELIGENCIA ARTIFICIAL (AGENTE LANGGRAPH)
   # ==========================================================================

   # 1. API Key de Google Gemini (Nativo de langchain-google-genai)
   GOOGLE_API_KEY=tu_api_key_aqui

   # 2. Modelo de Gemini a utilizar (Por defecto: gemini-3.5-flash)
   # Alternativa avanzada para razonamiento profundo: gemini-3.1-pro
   GEMINI_MODEL=gemini-3.5-flash

   # 3. API Key de VoyageAI (Opcional, para embeddings reales en pgvector)
   VOYAGE_API_KEY=tu_voyage_api_key_aqui
   ```

### Paso 3: Iniciar el Servidor Backend (FastAPI)
1. Instala automáticamente las dependencias del backend e inicia el servidor con `uv` en un solo paso:
   ```bash
   uv run uvicorn app.main:app --port 8000 --reload
   ```
2. El backend estará corriendo en [http://localhost:8000](http://localhost:8000). Puedes explorar la documentación interactiva en Swagger UI visitando [http://localhost:8000/docs](http://localhost:8000/docs).
3. El **worker automático** se iniciará simultáneamente y procesará notas pendientes cuando se acumulen ≥3 o cuando la más antigua tenga ≥10 minutos.

### Paso 4: Iniciar el Frontend (Next.js)
1. Abre una **nueva ventana de terminal** y navega al directorio `frontend/`:
   ```bash
   cd frontend
   ```
2. Instala los paquetes de Node:
   ```bash
   npm install
   ```
3. Inicia el servidor de desarrollo del frontend:
   ```bash
   npm run dev
   ```
4. Abre tu navegador en [http://localhost:3000](http://localhost:3000) para interactuar con la aplicación.

---

## 🧠 ¿Cómo usar al Agente Inteligente?

La aplicación está diseñada para funcionar en **Modo Dual**, adaptándose dinámicamente a tus credenciales:

### 1. Modo Simulación (Offline / Sin llaves API)
Si **no introduces** un `GOOGLE_API_KEY` en tu `.env` de backend:
*   El agente de **LangGraph** se ejecutará con total normalidad a través de cada uno de sus 4 nodos.
*   Autodetectará de manera interactiva lo que has ingresado en el formulario (ej. si ve código TypeScript, el optimizador corregirá el alcance de variables de `var` a `const` y agregará notas avanzadas; si ve comandos Bash, validará su sintaxis y explicará flags).
*   Esto garantiza un flujo de desarrollo estable e interactivo en local sin costo de red.

### 2. Modo Real (Con llaves API)
Una vez que añades tus API keys al `.env`:
1. **Google Gemini 3.5 Flash** tomará el control completo de la síntesis conceptual, el modelado pedagógico de planeación y la redacción del Markdown. Su inmensa ventana de contexto te permitirá procesar horas enteras de transcripción cruda de clases en un par de segundos.
2. **Gemini 3.1 Flash Lite** generará queries de búsqueda diversas (Multi-Query Expansion) para mejorar la recuperación RAG.
3. **VoyageAI** generará embeddings semánticos reales de alta fidelidad (Voyage-4, 1024 dims) que se indexarán directamente en PostgreSQL empleando la extensión de base de datos `pgvector`.
4. Al pulsar **"Procesar con Agente IA"**, verás las barras de escaneo premium progresar por cada nodo y recibirás una ficha académica estructurada lista para el autoestudio.

### 3. Procesamiento Automático (Worker)
El backend incluye un **worker automático** que se ejecuta en segundo plano y procesa notas pendientes sin intervención manual:
*   **Umbral de volumen**: Se activa cuando hay ≥3 notas pendientes acumuladas.
*   **Timeout**: Se activa cuando la nota pendiente más antigua tiene ≥10 minutos sin procesar.
*   **Lock compartido**: Utiliza un `asyncio.Lock` compartido con el endpoint manual para evitar procesamiento duplicado.

---

## 🔧 Herramientas de Administración

### Script `manage_db.py`
Ubicado en `backend/scripts/`, proporciona tres comandos para gestionar la base de datos:

```bash
# Crear un backup de la base de datos
uv run python scripts/manage_db.py backup

# Restaurar desde un backup
uv run python scripts/manage_db.py restore -f backups/backup_20260601.dump

# Importar notas Markdown desde un directorio de Obsidian
uv run python scripts/manage_db.py import -d /ruta/a/tus/notas

# Importar en modo dry-run (solo muestra qué haría sin modificar la DB)
uv run python scripts/manage_db.py import -d /ruta/a/tus/notas --dry-run
```

### Endpoints de Diagnóstico de Embeddings
*   `GET /api/embeddings/status` — Estado de chunks reales vs. dummy.
*   `POST /api/embeddings/reprocess-dummies` — Re-genera embeddings reales para todos los chunks dummy (requiere `VOYAGE_API_KEY`).

---

## 📁 Estructura del Workspace

```
proyecto-notas/
├── docker-compose.yml           # Orquestación unificada (db, storage, backend, frontend)
├── db/
│   ├── README.md                # Documentación técnica de la base de datos
│   ├── docker-compose.yml       # Contenedor PostgreSQL 16 + pgvector (independiente)
│   ├── init.sql                 # DDL: tablas (incluye logs, settings e images), índices HNSW/B-Tree y triggers
│   ├── seed_data.sql            # Datos semilla de inicialización y apuntes de prueba
│   ├── migrate_images.sql       # Script de migración para añadir soporte de imágenes
│   ├── migrate_study_tracker.sql# Script de migración para añadir logs de estudio y settings
│   ├── backup_pre_images.sql    # Respaldo histórico pre-imágenes
│   └── .env.example             # Variables de entorno para el contenedor de la DB
├── backend/
│   ├── main.py                  # Punto de entrada para desarrollo local (uvicorn)
│   ├── pyproject.toml           # Dependencias Python gestionadas con uv (boto3, google-genai, etc.)
│   ├── Dockerfile               # Receta de construcción del contenedor backend
│   ├── .env.template            # Plantilla con variables de entorno (MinIO, Gemini, Voyage)
│   ├── scripts/
│   │   └── manage_db.py         # CLI de administración: backup, restore e importación de apuntes
│   └── app/
│       ├── __init__.py          # Inicialización del paquete Python
│       ├── main.py              # API REST FastAPI, endpoints, CORS, y lifespan del worker
│       ├── agent.py             # Grafo LangGraph (4 nodos), preprocesador de placeholders, Synapse Scholar
│       ├── worker.py            # Worker asyncio en segundo plano, disparador híbrido y análisis de imágenes
│       ├── storage.py           # Cliente S3 (MinIO) e integración multimodal con Gemini 3.5 Flash (Base64)
│       ├── models.py            # Modelos SQLAlchemy (RawNote, ProcessedNote, NoteChunk, RawNoteImage, StudyLog, UserSetting)
│       ├── schemas.py           # Schemas Pydantic: validaciones e inyecciones de datos
│       ├── crud.py              # CRUD de notas, reordenamiento e integración con borrado físico en MinIO
│       └── database.py          # Configuración de sesión SQLAlchemy + driver psycopg3
├── frontend/
│   ├── package.json             # Dependencias: Next.js 16, React 19, Zod 4, @dnd-kit, lucide-react
│   ├── Dockerfile               # Contenedor Next.js standalone de producción
│   └── app/
│       ├── page.tsx             # Panel principal (dashboard)
│       ├── layout.tsx           # Layout con tipografía Geist y estilos base
│       ├── globals.css          # Estilos globales con Tailwind CSS 4
│       ├── components/
│       │   ├── Sidebar.tsx          # Sidebar: cola de apuntes, archivado y listados agrupados por curso
│       │   ├── NoteForm.tsx         # Formulario de captura de apuntes, snippets de código, comandos e imágenes de apoyo
│       │   ├── ResultPanel.tsx      # Visualizador de Markdown renderizado y comentarios del agente
│       │   ├── ConfirmModal.tsx     # Modal reutilizable de confirmación
│       │   ├── CourseReorderModal.tsx # Reordenación de notas por arrastre (drag-and-drop con @dnd-kit)
│       │   ├── ProcessedNotesModal.tsx # Alertas de procesamiento en segundo plano
│       │   └── TemplateModal.tsx    # Selector de plantillas predefinidas
│       ├── hooks/
│       │   ├── useNotesApi.ts   # Conectores HTTP con backend (CRUD, subida de imágenes, ejecución de agente)
│       │   ├── useNoteForm.ts   # Controladores del formulario y validación reactiva con Zod
│       │   └── useModals.ts     # Controladores de apertura/cierre de ventanas emergentes
│       ├── schemas/
│       │   └── noteSchema.ts   # Validación estricta Zod del formulario
│       └── types/
│           └── index.ts        # Declaraciones de tipos TypeScript
├── docs/
│   └── agent-architecture.md   # Esta documentación técnica de arquitectura
└── ai-component/                # (Vacío — reservado para futuras extensiones)
```

---

## 📡 Referencia de Endpoints de la API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check del servicio |
| `POST` | `/api/notes` | Añadir nota cruda a la cola |
| `POST` | `/api/notes/images/upload` | Subir imagen de apoyo a MinIO (retorna URL y metadatos) |
| `GET` | `/api/notes/queue` | Listar notas pendientes |
| `GET` | `/api/notes/archive` | Listar notas procesadas |
| `GET` | `/api/notes/processed-since?since=ISO` | Notas procesadas después de un timestamp |
| `GET` | `/api/notes/{id}` | Detalle de una nota por ID |
| `PUT` | `/api/notes/{id}` | Actualizar nota en la cola |
| `DELETE` | `/api/notes/{id}` | Eliminar nota (cascada) |
| `POST` | `/api/notes/{id}/process` | Procesar nota con el agente IA |
| `GET` | `/api/courses` | Listar cursos con notas procesadas |
| `GET` | `/api/courses/{name}/notes` | Notas procesadas de un curso |
| `GET` | `/api/courses/{name}/markdown` | Markdown concatenado de un curso |
| `PUT` | `/api/courses/{name}/reorder` | Reordenar notas de un curso |
| `GET` | `/api/embeddings/status` | Estado de embeddings (real vs. dummy) |
| `POST` | `/api/embeddings/reprocess-dummies` | Re-generar embeddings dummy con Voyage |
