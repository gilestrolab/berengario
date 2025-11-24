-- Migration: Add query tracking columns to conversation_messages table
-- Date: 2025-01-24
-- Description: Adds columns for tracking query optimization and source documents
--
-- This migration adds:
-- - original_query, optimized_query, optimization_applied (for QUERY messages)
-- - sources_used, retrieval_metadata (for REPLY messages)
--
-- Compatible with both SQLite and MariaDB

-- Add query optimization tracking columns
ALTER TABLE conversation_messages
ADD COLUMN original_query TEXT NULL;

ALTER TABLE conversation_messages
ADD COLUMN optimized_query TEXT NULL;

ALTER TABLE conversation_messages
ADD COLUMN optimization_applied BOOLEAN NOT NULL DEFAULT FALSE;

-- Add source document tracking columns
-- Note: JSON type works in both SQLite (3.9+) and MariaDB (5.7.8+)
ALTER TABLE conversation_messages
ADD COLUMN sources_used JSON NULL;

ALTER TABLE conversation_messages
ADD COLUMN retrieval_metadata JSON NULL;

-- Migration complete
-- Run this with: python migrations/apply_migration.py
