-- Memoria de conocimiento v2. Migración aditiva, idempotente y reversible por configuración.
BEGIN;

CREATE TABLE IF NOT EXISTS source_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_note_id UUID NOT NULL REFERENCES raw_notes(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL,
    char_start INT,
    char_end INT,
    embedding vector(1024) NOT NULL,
    is_dummy_embedding BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_source_chunk_note_hash UNIQUE (raw_note_id, content_hash)
);

CREATE TABLE IF NOT EXISTS note_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_note_id UUID NOT NULL REFERENCES raw_notes(id) ON DELETE CASCADE,
    prior_claim_id UUID REFERENCES note_claims(id) ON DELETE SET NULL,
    concept VARCHAR(255) NOT NULL DEFAULT '',
    statement TEXT NOT NULL,
    claim_hash VARCHAR(64) NOT NULL,
    novelty_relation VARCHAR(16) NOT NULL DEFAULT 'NEW',
    evidence_source_type VARCHAR(32) NOT NULL DEFAULT 'transcription',
    evidence_text TEXT NOT NULL DEFAULT '',
    evidence_start INT,
    evidence_end INT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    embedding vector(1024) NOT NULL,
    is_dummy_embedding BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_note_claim_hash UNIQUE (raw_note_id, claim_hash),
    CONSTRAINT ck_note_claim_relation CHECK (novelty_relation IN ('NEW','EXTENDS','REPEATS','APPLIES','CLARIFIES','CONTRADICTS'))
);

CREATE TABLE IF NOT EXISTS flashcard_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_note_id UUID NOT NULL REFERENCES raw_notes(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    embedding vector(1024) NOT NULL,
    is_dummy_embedding BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_flashcard_note_fingerprint UNIQUE (raw_note_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS generation_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processed_note_id UUID NOT NULL UNIQUE REFERENCES processed_notes(id) ON DELETE CASCADE,
    pipeline_version VARCHAR(32) NOT NULL,
    body_markdown TEXT NOT NULL DEFAULT '',
    glossary_markdown TEXT NOT NULL DEFAULT '',
    flashcards_markdown TEXT NOT NULL DEFAULT '',
    evidence_manifest JSONB DEFAULT '{}'::jsonb,
    metrics JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_index_states (
    raw_note_id UUID PRIMARY KEY REFERENCES raw_notes(id) ON DELETE CASCADE,
    index_version VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_knowledge_index_status CHECK (status IN ('pending','processing','complete','failed'))
);

CREATE INDEX IF NOT EXISTS idx_source_chunks_note ON source_chunks(raw_note_id);
CREATE INDEX IF NOT EXISTS idx_note_claims_note ON note_claims(raw_note_id);
CREATE INDEX IF NOT EXISTS idx_note_claims_prior ON note_claims(prior_claim_id);
CREATE INDEX IF NOT EXISTS idx_flashcard_records_note ON flashcard_records(raw_note_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_index_status ON knowledge_index_states(status, index_version);
CREATE INDEX IF NOT EXISTS idx_source_chunks_embedding_hnsw ON source_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_note_claims_embedding_hnsw ON note_claims USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_flashcard_records_embedding_hnsw ON flashcard_records USING hnsw (embedding vector_cosine_ops);

INSERT INTO user_settings (key, value)
VALUES ('generation_pipeline_version', 'legacy')
ON CONFLICT (key) DO NOTHING;

DROP TRIGGER IF EXISTS trigger_update_generation_artifacts_updated_at ON generation_artifacts;
CREATE TRIGGER trigger_update_generation_artifacts_updated_at
BEFORE UPDATE ON generation_artifacts
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_update_knowledge_index_states_updated_at ON knowledge_index_states;
CREATE TRIGGER trigger_update_knowledge_index_states_updated_at
BEFORE UPDATE ON knowledge_index_states
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
