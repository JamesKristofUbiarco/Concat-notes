-- Migración aditiva e idempotente para alinear instalaciones existentes
-- con el modelo actual. No elimina tablas, columnas ni datos.
BEGIN;

ALTER TABLE raw_notes
    ADD COLUMN IF NOT EXISTS flashcard_target INT;

ALTER TABLE raw_note_images
    ADD COLUMN IF NOT EXISTS image_type VARCHAR(20) NOT NULL DEFAULT 'image';

CREATE TABLE IF NOT EXISTS course_glossaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_name VARCHAR(255) NOT NULL UNIQUE,
    entries JSONB DEFAULT '[]'::jsonb,
    compiled_markdown TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_course_glossaries_course_name
    ON course_glossaries(course_name);

INSERT INTO user_settings (key, value)
VALUES ('flashcard_density', '5')
ON CONFLICT (key) DO NOTHING;

DROP TRIGGER IF EXISTS trigger_update_course_glossaries_updated_at
    ON course_glossaries;
CREATE TRIGGER trigger_update_course_glossaries_updated_at
BEFORE UPDATE ON course_glossaries
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

COMMIT;
