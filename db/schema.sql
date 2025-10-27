-- Sprint A: Conversations & Messages schema (SQLite)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  title TEXT,
  status TEXT DEFAULT 'active',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,        -- 'user' | 'assistant' | 'system' | 'tool'
  text TEXT NOT NULL,
  content_json TEXT,         -- reserved for rich parts later
  created_at INTEGER NOT NULL,
  parent_id TEXT,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

-- Future-proof (not used in Sprint A)
CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  status TEXT NOT NULL,      -- 'queued' | 'ok' | 'error'
  request_json TEXT,
  response_json TEXT,
  latency_ms INTEGER,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id),
  FOREIGN KEY(message_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
  ON messages (conversation_id, created_at DESC);
