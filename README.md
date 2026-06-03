# 📘 Gestor Inteligente de Apuntes: Next.js, FastAPI & LangGraph

Bienvenido al **Gestor Inteligente de Apuntes y Código**. Esta es una aplicación de nivel empresarial y full-stack diseñada en **Mayo de 2026** para tomar notas de cursos, capturar transcripciones de audio, snippets de código y comandos de shell, y procesarlos de manera autónoma utilizando un **Agente cognitivo basado en LangGraph y Google Gemini 3.5 Flash**, con persistencia relacional e indexación semántica en **PostgreSQL con pgvector**.

---

## 🚀 Arquitectura del Proyecto

El ecosistema se compone de tres módulos desacoplados:

1. **Frontend (Next.js + Tailwind CSS + Zod)**: 
   - Una interfaz oscura de diseño prémium y ultra-reactiva que permite registrar apuntes interactivos, controlar una cola activa de estudio y visualizar fichas sintetizadas en Markdown con resaltado sintáctico.
2. **Backend (FastAPI + SQLAlchemy + Pydantic)**: 
   - API REST robusta que expone operaciones CRUD e interactúa directamente con PostgreSQL.
3. **Agente IA (LangGraph + Gemini 3.5 Flash + pgvector)**: 
   - Un agente cognitivo representado como un grafo de estados cíclicos (`StateGraph`) que implementa:
     - **Memoria**: Persistencia de hilos conversacionales mediante `MemorySaver`.
     - **Contexto (RAG)**: Recuperación vectorial de apuntes similares históricos con similitud por coseno en `pgvector`.
     - **Planeación**: Un nodo inteligente que analiza los contenidos y formula un plan pedagógico antes de sintetizar.
     - **Herramientas**: Optimizador de código y validador sintáctico de shell CLI.
     - **Razonamiento**: Explicaciones pedagógicas detalladas de diseño.
     - **Acción**: Ejecución de herramientas e hilado final en Markdown.

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

## ⚙️ Configuración y Puesta en Marcha

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
2. Crea tu archivo `.env` tomando como base la plantilla o ingresando lo siguiente:
   ```env
   # URL de conexión de la base de datos PostgreSQL en Docker
   DATABASE_URL=postgresql://notes_user:notes_password@localhost:5432/notes_db
   PORT=8000

   # ==========================================================================
   # INTELIGENCIA ARTIFICIAL (AGENTE LANGGRAPH) - CONFIGURACIÓN DE MAYO DE 2026
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
*   El agente de **LangGraph** se ejecutará con total normalidad a través de cada uno de sus nodos.
*   Autodetectará de manera interactiva lo que has ingresado en el formulario (ej. si ve código TypeScript, el optimizador corregirá el alcance de variables de `var` a `const` y agregará notas avanzadas; si ve comandos Bash, validará su sintaxis y explicará flags).
*   Esto garantiza un flujo de desarrollo estable e interactivo en local sin costo de red.

### 2. Modo Real (Con llaves API)
Una vez que añades tus API keys al `.env`:
1. **Google Gemini 3.5 Flash** tomará el control completo de la síntesis conceptual, el modelado pedagógico de planeación y la redacción del Markdown. Su inmensa ventana de contexto te permitirá procesar horas enteras de transcripción cruda de clases en un par de segundos.
2. **VoyageAI** generará embeddings semánticos reales de alta fidelidad que se indexarán directamente en PostgreSQL empleando la extensión de base de datos `pgvector`.
3. Al pulsar **"Procesar con Agente IA"**, verás las barras de escaneo premium progresar por cada nodo y recibirás una ficha académica estructurada lista para el autoestudio.

---

## 📁 Estructura del Workspace

*   `db/`: Contenedor Docker y scripts SQL de base de datos relacional y vectorial.
*   `backend/`: Código Python en FastAPI, esquemas Pydantic y el núcleo del agente en `app/agent.py`.
*   `frontend/`: Código TypeScript en Next.js, esquemas Zod de validación y estilos globales reactivos.
