BEGIN;

CREATE TABLE IF NOT EXISTS local_sync_config (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    destination_subpath VARCHAR(500) NOT NULL DEFAULT 'Cursos',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO local_sync_config (id, enabled, destination_subpath)
VALUES (1, FALSE, 'Cursos')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS course_sync_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_name VARCHAR(255) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    filename VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'disabled',
    last_export_hash VARCHAR(64),
    last_file_hash VARCHAR(64),
    conflict_db_path VARCHAR(700),
    last_error TEXT,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    external_changed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_course_sync_states_enabled
ON course_sync_states(enabled);

DROP TRIGGER IF EXISTS trigger_update_local_sync_config_updated_at ON local_sync_config;
CREATE TRIGGER trigger_update_local_sync_config_updated_at
BEFORE UPDATE ON local_sync_config
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_update_course_sync_states_updated_at ON course_sync_states;
CREATE TRIGGER trigger_update_course_sync_states_updated_at
BEFORE UPDATE ON course_sync_states
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
