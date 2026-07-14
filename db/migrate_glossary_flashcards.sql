-- ============================================================================
-- MIGRACIÓN: Glosario y Flashcards — Ejecutar en DBs existentes
-- ============================================================================
-- Este script crea la tabla course_glossaries y añade flashcard_target a raw_notes.
-- Es seguro ejecutarlo múltiples veces (idempotente).
-- ============================================================================

-- 1. Añadir columna flashcard_target a raw_notes si no existe
ALTER TABLE raw_notes ADD COLUMN IF NOT EXISTS flashcard_target INT NULL;

-- 2. Crear tabla course_glossaries
CREATE TABLE IF NOT EXISTS course_glossaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_name VARCHAR(255) NOT NULL UNIQUE,
    entries JSONB DEFAULT '[]'::jsonb,
    compiled_markdown TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Crear índice para búsquedas por curso en los glosarios
CREATE INDEX IF NOT EXISTS idx_course_glossaries_course_name ON course_glossaries(course_name);

-- 4. Trigger para actualizar updated_at automáticamente en course_glossaries
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_course_glossaries_updated_at ON course_glossaries;
CREATE TRIGGER trigger_update_course_glossaries_updated_at
BEFORE UPDATE ON course_glossaries
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- 5. Insertar densidad de flashcards por defecto (5 por cada 10,000 caracteres) si no existe
INSERT INTO user_settings (key, value)
VALUES ('flashcard_density', '5')
ON CONFLICT (key) DO NOTHING;
