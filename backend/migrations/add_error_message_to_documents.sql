-- Add error_message column to documents table (for surfacing ingestion errors)
-- Run manually if upgrading from a version without this column:
-- psql -d ragdb -f migrations/add_error_message_to_documents.sql

ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message TEXT;
