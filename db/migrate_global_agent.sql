BEGIN;
CREATE TABLE IF NOT EXISTS agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), title VARCHAR(255) NOT NULL DEFAULT 'Nueva conversación',
    title_is_manual BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL, content TEXT NOT NULL, attachments JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation ON agent_messages(conversation_id);
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
    user_message_id UUID NOT NULL UNIQUE REFERENCES agent_messages(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', model_id VARCHAR(150) NOT NULL,
    scope JSONB NOT NULL DEFAULT '{}', progress VARCHAR(255) NOT NULL DEFAULT 'En espera', error TEXT,
    proposal JSONB, proposal_status VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation ON agent_runs(conversation_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_one_active_run
    ON agent_runs(conversation_id) WHERE status IN ('pending', 'running');
COMMIT;
