-- PostgreSQL initialization script for Pokemon TCG database
-- This script runs automatically when the container is first created

-- Create database (already done by POSTGRES_DB env var, but kept for reference)
-- CREATE DATABASE pokemon_tcg;

-- Connect to pokemon_tcg database
\c pokemon_tcg;

-- Enable UUID extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE pokemon_tcg TO pokemon_user;
GRANT ALL ON SCHEMA public TO pokemon_user;

-- Create indexes for common queries (will be populated by migration script)
-- Tables will be created by SQLModel.metadata.create_all()

-- Log successful initialization
SELECT 'PostgreSQL database initialized successfully!' AS status;
