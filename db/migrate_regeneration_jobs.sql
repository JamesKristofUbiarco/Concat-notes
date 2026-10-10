-- Aditiva e idempotente: no cambia las notas ni los índices existentes.
CREATE TABLE IF NOT EXISTS regeneration_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    instructions TEXT NOT NULL DEFAULT '',
    components JSON NOT NULL DEFAULT '[]',
    items JSON NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_regeneration_jobs_status ON regeneration_jobs(status);
