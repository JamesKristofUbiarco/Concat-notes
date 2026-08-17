-- Biblioteca y programación interna de flashcards. Migración aditiva e idempotente.
BEGIN;

ALTER TABLE flashcard_records
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS learning_state VARCHAR(16) NOT NULL DEFAULT 'new',
    ADD COLUMN IF NOT EXISTS due_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS last_reviewed_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS interval_days INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ease_factor DOUBLE PRECISION NOT NULL DEFAULT 2.5,
    ADD COLUMN IF NOT EXISTS repetitions INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS lapses INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS review_count INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

DO $$ BEGIN
    ALTER TABLE flashcard_records ADD CONSTRAINT ck_flashcard_learning_state
        CHECK (learning_state IN ('new', 'learning', 'review'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS flashcard_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flashcard_id UUID NOT NULL REFERENCES flashcard_records(id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 4),
    previous_state VARCHAR(16) NOT NULL,
    new_state VARCHAR(16) NOT NULL,
    previous_interval_days INT NOT NULL DEFAULT 0,
    scheduled_interval_days INT NOT NULL DEFAULT 0,
    reviewed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcard_records(is_active, due_at);
CREATE INDEX IF NOT EXISTS idx_flashcards_state ON flashcard_records(learning_state);
CREATE INDEX IF NOT EXISTS idx_flashcard_reviews_card ON flashcard_reviews(flashcard_id, reviewed_at DESC);

DROP TRIGGER IF EXISTS trigger_update_flashcard_records_updated_at ON flashcard_records;
CREATE TRIGGER trigger_update_flashcard_records_updated_at
BEFORE UPDATE ON flashcard_records
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
