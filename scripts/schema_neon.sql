-- ====================================================================
-- Neon PostgreSQL Migration Script
-- Assam Regiment Digital Museum API
-- ====================================================================

-- 1. Enable pgvector extension for 384-dim embedding similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create custom processingstatus ENUM type if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processingstatus') THEN
        CREATE TYPE processingstatus AS ENUM (
            'pending',
            'in_progress',
            'done',
            'failed',
            'skipped',
            'not_applicable'
        );
    END IF;
END $$;

-- 3. Create 'documents' table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR NOT NULL,
    category VARCHAR,
    collection VARCHAR,
    file_path VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,
    ocr_status processingstatus NOT NULL DEFAULT 'pending',
    icr_status processingstatus NOT NULL DEFAULT 'pending',
    ocr_text TEXT,
    icr_text TEXT,
    tags VARCHAR,
    description TEXT,
    embedding vector(384),
    metadata_json JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
);

-- 4. Create vector Cosine Distance Index for fast semantic retrieval
CREATE INDEX IF NOT EXISTS documents_embedding_idx 
ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
