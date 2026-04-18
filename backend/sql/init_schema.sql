CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    phone VARCHAR(20) UNIQUE,
    wechat_unionid VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    anonymous_id VARCHAR(64),
    owner_type VARCHAR(20) NOT NULL DEFAULT 'anonymous',
    title VARCHAR(200) DEFAULT '未命名案件',
    region_code VARCHAR(20) DEFAULT 'xian',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id),
    user_id UUID REFERENCES users(id),
    anonymous_id VARCHAR(64),
    openharness_session_id VARCHAR(128),
    status VARCHAR(20) DEFAULT 'active',
    message_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID NOT NULL,
    user_id UUID,
    anonymous_id VARCHAR(64),
    session_id UUID,
    event_type VARCHAR(50),
    request_payload JSONB,
    response_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cases_user_updated ON cases(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_anon_updated ON cases(anonymous_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_case_created ON sessions(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_logs(trace_id);
