-- ============================================================================
-- INIT.SQL - ESQUEMA DE BASE DE DATOS DE NOTAS DE CURSOS CON VECTOR SEARCH
-- ============================================================================
-- Este script inicializa las tablas para manejar la cola de apuntes de cursos,
-- el historial de notas procesadas en Markdown y las divisiones vectoriales (chunks)
-- para búsquedas semánticas de alta precisión utilizando pgvector y embeddings Voyage-4.
-- ============================================================================

-- 1. Habilitar la extensión de pgvector en la base de datos
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Crear enum para controlar el estado de la cola de apuntes
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'queue_status') THEN
        CREATE TYPE queue_status AS ENUM ('pending', 'processed', 'failed');
    END IF;
END$$;

-- 3. TABLA: raw_notes
-- Almacena las fichas crudas de apuntes que ingresa el usuario a la cola.
CREATE TABLE IF NOT EXISTS raw_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    writing_mode TEXT DEFAULT '',
    platform VARCHAR(100) DEFAULT '',
    course_name VARCHAR(255) NOT NULL,
    teacher VARCHAR(255) DEFAULT '',
    course_module VARCHAR(255) DEFAULT '',
    class_title VARCHAR(255) NOT NULL,
    transcription TEXT DEFAULT '',
    class_summary TEXT DEFAULT '',
    my_notes TEXT DEFAULT '',
    code_snippets JSONB DEFAULT '[]'::jsonb,
    command_snippets JSONB DEFAULT '[]'::jsonb,
    status queue_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- 4. TABLA: processed_notes
-- Almacena el resultado final Markdown procesado por el agente de IA (LangGraph).
CREATE TABLE IF NOT EXISTS processed_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_note_id UUID UNIQUE REFERENCES raw_notes(id) ON DELETE CASCADE,
    structured_markdown TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. TABLA: note_chunks
-- Almacena las particiones o fragmentos de las notas procesadas junto con sus
-- embeddings vectoriales (Voyage-4, con 1024 dimensiones) para búsqueda semántica.
CREATE TABLE IF NOT EXISTS note_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processed_note_id UUID NOT NULL REFERENCES processed_notes(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL, -- Configurado para Voyage-3/Voyage-4 (1024 dimensiones)
    chunk_index INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ÍNDICES PARA OPTIMIZACIÓN Y BÚSQUEDAS
-- ============================================================================

-- Índice para búsquedas rápidas por estado de la cola en raw_notes (Ej: consultar pendientes)
CREATE INDEX IF NOT EXISTS idx_raw_notes_status ON raw_notes(status);

-- Índice para ordenar la cola por fecha de creación
CREATE INDEX IF NOT EXISTS idx_raw_notes_created_at ON raw_notes(created_at);

-- Índice para búsquedas por curso en las notas crudas
CREATE INDEX IF NOT EXISTS idx_raw_notes_course ON raw_notes(course_name);

-- Índice vectorial de tipo HNSW (Hierarchical Navigable Small World) en note_chunks.
-- Optimiza búsquedas semánticas ultrarrápidas usando distancia de coseno.
-- HNSW es ideal para base de datos en producción por su alta velocidad y recall balanceado.
CREATE INDEX IF NOT EXISTS idx_note_chunks_embedding_hnsw 
ON note_chunks USING hnsw (embedding vector_cosine_ops);

-- ============================================================================
-- TRIGGERS PARA CONTROL DE FECHAS (UPDATED_AT)
-- ============================================================================

-- Función auxiliar para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para raw_notes
DROP TRIGGER IF EXISTS trigger_update_raw_notes_updated_at ON raw_notes;
CREATE TRIGGER trigger_update_raw_notes_updated_at
BEFORE UPDATE ON raw_notes
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Trigger para processed_notes
DROP TRIGGER IF EXISTS trigger_update_processed_notes_updated_at ON processed_notes;
CREATE TRIGGER trigger_update_processed_notes_updated_at
BEFORE UPDATE ON processed_notes
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
