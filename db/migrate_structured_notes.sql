BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL DEFAULT 'Mi espacio',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO workspaces (slug, name)
VALUES ('default', 'Mi espacio')
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS note_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_note_collection_workspace_name UNIQUE (workspace_id, name)
);

CREATE TABLE IF NOT EXISTS structured_note_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    raw_note_id UUID REFERENCES raw_notes(id) ON DELETE SET NULL,
    collection_id UUID REFERENCES note_collections(id) ON DELETE SET NULL,
    origin_kind VARCHAR(32) NOT NULL,
    schema_version VARCHAR(16) NOT NULL DEFAULT '1.0',
    migration_status VARCHAR(24) NOT NULL DEFAULT 'native',
    current_revision_id UUID,
    revision_number INTEGER NOT NULL DEFAULT 0,
    document_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rendered_markdown TEXT NOT NULL DEFAULT '',
    sync_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    sync_status VARCHAR(24) NOT NULL DEFAULT 'disabled',
    sync_filename VARCHAR(255) NOT NULL DEFAULT '',
    last_sync_hash VARCHAR(64),
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_structured_note_documents_raw_note_id
    ON structured_note_documents(raw_note_id);
CREATE INDEX IF NOT EXISTS ix_structured_note_documents_metadata
    ON structured_note_documents USING gin (document_json jsonb_path_ops);
CREATE UNIQUE INDEX IF NOT EXISTS uq_primary_generated_document_per_raw_note
    ON structured_note_documents(raw_note_id)
    WHERE raw_note_id IS NOT NULL AND origin_kind = 'generated_class';

ALTER TABLE structured_note_documents ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE structured_note_documents ADD COLUMN IF NOT EXISTS sync_status VARCHAR(24) NOT NULL DEFAULT 'disabled';
ALTER TABLE structured_note_documents ADD COLUMN IF NOT EXISTS sync_filename VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE structured_note_documents ADD COLUMN IF NOT EXISTS last_sync_hash VARCHAR(64);
ALTER TABLE structured_note_documents ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS note_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES structured_note_documents(id) ON DELETE CASCADE,
    parent_revision_id UUID REFERENCES note_revisions(id) ON DELETE SET NULL,
    revision_number INTEGER NOT NULL,
    change_kind VARCHAR(32) NOT NULL,
    change_summary TEXT NOT NULL DEFAULT '',
    actor VARCHAR(24) NOT NULL DEFAULT 'user',
    document_json JSONB NOT NULL,
    rendered_markdown TEXT NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_note_revision_number UNIQUE (document_id, revision_number)
);
CREATE INDEX IF NOT EXISTS ix_note_revisions_document_id ON note_revisions(document_id);

CREATE TABLE IF NOT EXISTS note_edit_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES structured_note_documents(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL DEFAULT 'Edición con IA',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_note_edit_sessions_document_id ON note_edit_sessions(document_id);

CREATE TABLE IF NOT EXISTS note_edit_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES note_edit_sessions(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_note_edit_messages_session_id ON note_edit_messages(session_id);

CREATE TABLE IF NOT EXISTS note_patch_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES note_edit_sessions(id) ON DELETE CASCADE,
    base_revision_id UUID NOT NULL REFERENCES note_revisions(id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'validated',
    intent TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    operations JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_revision_id UUID REFERENCES note_revisions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_note_patch_proposals_session_id ON note_patch_proposals(session_id);

CREATE TABLE IF NOT EXISTS note_style_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    slug VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_note_style_workspace_slug UNIQUE (workspace_id, slug)
);

CREATE TABLE IF NOT EXISTS note_style_examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES note_style_profiles(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES structured_note_documents(id) ON DELETE CASCADE,
    methodology_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_note_style_example UNIQUE (profile_id, document_id)
);

CREATE TABLE IF NOT EXISTS flashcard_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flashcard_id UUID NOT NULL REFERENCES flashcard_records(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES structured_note_documents(id) ON DELETE CASCADE,
    block_id UUID NOT NULL,
    source_revision_id UUID REFERENCES note_revisions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_flashcard_source_block UNIQUE (flashcard_id, document_id, block_id)
);
CREATE INDEX IF NOT EXISTS ix_flashcard_sources_flashcard_id ON flashcard_sources(flashcard_id);
CREATE INDEX IF NOT EXISTS ix_flashcard_sources_document_id ON flashcard_sources(document_id);

ALTER TABLE flashcard_records ALTER COLUMN raw_note_id DROP NOT NULL;
ALTER TABLE flashcard_records
    ADD COLUMN IF NOT EXISTS structured_document_id UUID REFERENCES structured_note_documents(id) ON DELETE CASCADE;
ALTER TABLE flashcard_records
    ADD COLUMN IF NOT EXISTS candidate_status VARCHAR(16) NOT NULL DEFAULT 'active';
CREATE INDEX IF NOT EXISTS ix_flashcard_records_structured_document_id
    ON flashcard_records(structured_document_id);

ALTER TABLE local_sync_config
    ADD COLUMN IF NOT EXISTS assets_subdirectory VARCHAR(120) NOT NULL DEFAULT 'ANEXOS';

ALTER TABLE raw_notes
    ADD COLUMN IF NOT EXISTS composition_profile VARCHAR(100) NOT NULL DEFAULT 'adaptive';

ALTER TABLE structured_note_documents
    DROP CONSTRAINT IF EXISTS fk_structured_note_current_revision;
ALTER TABLE structured_note_documents
    ADD CONSTRAINT fk_structured_note_current_revision
    FOREIGN KEY (current_revision_id) REFERENCES note_revisions(id) ON DELETE SET NULL;

COMMIT;
