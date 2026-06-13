-- ============================================================================
-- MIGRATE_IMAGES.SQL - Agregar soporte para Snippets de Imagen
-- ============================================================================

-- 1. Crear la tabla raw_note_images si no existe
CREATE TABLE IF NOT EXISTS raw_note_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_note_id UUID REFERENCES raw_notes(id) ON DELETE CASCADE,
    image_url VARCHAR(500) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    descripcion_llm TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Crear índice para búsquedas rápidas por nota cruda
CREATE INDEX IF NOT EXISTS idx_raw_note_images_raw_note_id ON raw_note_images(raw_note_id);
