CREATE TABLE IF NOT EXISTS source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(100) NOT NULL, format VARCHAR(8) NOT NULL, size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL, storage_key VARCHAR(700) NOT NULL UNIQUE,
    page_count INT, title VARCHAR(500) NOT NULL DEFAULT '', author VARCHAR(500) NOT NULL DEFAULT '',
    language VARCHAR(32) NOT NULL DEFAULT '', parser_name VARCHAR(100) NOT NULL DEFAULT '',
    parser_version VARCHAR(50) NOT NULL DEFAULT '', status VARCHAR(32) NOT NULL DEFAULT 'uploaded',
    capabilities JSONB NOT NULL DEFAULT '{}', warnings JSONB NOT NULL DEFAULT '[]', error TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_source_documents_sha256 ON source_documents(sha256);

CREATE TABLE IF NOT EXISTS document_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES document_sections(id) ON DELETE CASCADE, order_index INT NOT NULL,
    level INT NOT NULL DEFAULT 1, title VARCHAR(1000) NOT NULL, source_kind VARCHAR(32) NOT NULL,
    page_start INT, page_end INT, epub_href VARCHAR(1000), fragment_id VARCHAR(500),
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_document_sections_document ON document_sections(document_id, order_index);

CREATE TABLE IF NOT EXISTS document_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    storage_key VARCHAR(700) NOT NULL UNIQUE, media_type VARCHAR(100) NOT NULL, kind VARCHAR(32) NOT NULL,
    page_number INT, content_hash VARCHAR(64) NOT NULL, perceptual_hash VARCHAR(64), width INT, height INT,
    description TEXT NOT NULL DEFAULT '', analysis_model VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_document_assets_document ON document_assets(document_id);

CREATE TABLE IF NOT EXISTS document_elements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    section_id UUID REFERENCES document_sections(id) ON DELETE SET NULL, order_index INT NOT NULL,
    page_number INT, element_type VARCHAR(32) NOT NULL, bbox_json JSONB, text TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '', visual_description TEXT NOT NULL DEFAULT '',
    structured_data JSONB NOT NULL DEFAULT '{}', asset_id UUID REFERENCES document_assets(id) ON DELETE SET NULL,
    content_hash VARCHAR(64) NOT NULL, parser VARCHAR(100) NOT NULL, model VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'extracted', status_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_document_elements_document ON document_elements(document_id, order_index);

CREATE TABLE IF NOT EXISTS document_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    kind VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL DEFAULT 'pending', stage VARCHAR(64) NOT NULL DEFAULT 'queued',
    progress INT NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT 'Pendiente', error TEXT,
    profile VARCHAR(16) NOT NULL DEFAULT 'balanced', selection_json JSONB NOT NULL DEFAULT '{}',
    options_json JSONB NOT NULL DEFAULT '{}', warnings JSONB NOT NULL DEFAULT '[]', heartbeat_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, attempt INT NOT NULL DEFAULT 0,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE, idempotency_key VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_document_jobs_status ON document_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_document_jobs_idempotency ON document_jobs(idempotency_key);

CREATE TABLE IF NOT EXISTS document_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), document_id UUID NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
    job_id UUID REFERENCES document_jobs(id) ON DELETE SET NULL, selection_json JSONB NOT NULL DEFAULT '{}',
    profile VARCHAR(16) NOT NULL, model_snapshot JSONB NOT NULL DEFAULT '{}', parser_version VARCHAR(50) NOT NULL DEFAULT '1',
    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0, approved_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 1,
    actual_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0, status VARCHAR(32) NOT NULL DEFAULT 'processing',
    warnings JSONB NOT NULL DEFAULT '[]', created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS document_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), run_id UUID NOT NULL REFERENCES document_runs(id) ON DELETE CASCADE,
    order_index INT NOT NULL, title VARCHAR(1000) NOT NULL, heading_path JSONB NOT NULL DEFAULT '[]',
    page_ranges JSONB NOT NULL DEFAULT '[]', source_markdown TEXT NOT NULL,
    course_name VARCHAR(255) NOT NULL DEFAULT '', course_module VARCHAR(255) NOT NULL DEFAULT '',
    class_title VARCHAR(255) NOT NULL DEFAULT '', asset_ids JSONB NOT NULL DEFAULT '[]',
    raw_note_id UUID REFERENCES raw_notes(id) ON DELETE SET NULL, confirmed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_document_drafts_run ON document_drafts(run_id, order_index);

ALTER TABLE raw_note_images ADD COLUMN IF NOT EXISTS document_asset_id UUID REFERENCES document_assets(id) ON DELETE SET NULL;

INSERT INTO user_settings (key, value) VALUES ('model_document_vision', 'google/gemini-3.6-flash')
ON CONFLICT (key) DO NOTHING;
