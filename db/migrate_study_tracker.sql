-- ============================================================================
-- MIGRACIÓN: Study Tracker — Ejecutar en DBs existentes con datos
-- ============================================================================
-- Este script crea las tablas study_logs y user_settings si no existen.
-- Es seguro ejecutarlo múltiples veces (idempotente).
-- ============================================================================

-- Tabla study_logs
CREATE TABLE IF NOT EXISTS study_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_date DATE NOT NULL UNIQUE,
    total_minutes INT NOT NULL DEFAULT 0,
    daily_goal_at_time INT NOT NULL,
    goal_percentage FLOAT NOT NULL DEFAULT 0.0,
    goal_met BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tabla user_settings
CREATE TABLE IF NOT EXISTS user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Meta diaria por defecto
INSERT INTO user_settings (key, value)
VALUES ('daily_study_goal', '60')
ON CONFLICT (key) DO NOTHING;

-- Índice
CREATE INDEX IF NOT EXISTS idx_study_logs_date ON study_logs(study_date);

-- Triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_study_logs_updated_at ON study_logs;
CREATE TRIGGER trigger_update_study_logs_updated_at
BEFORE UPDATE ON study_logs
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_update_user_settings_updated_at ON user_settings;
CREATE TRIGGER trigger_update_user_settings_updated_at
BEFORE UPDATE ON user_settings
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Añadir columna class_minutes a raw_notes si no existe
ALTER TABLE raw_notes ADD COLUMN IF NOT EXISTS class_minutes INT NOT NULL DEFAULT 0;
