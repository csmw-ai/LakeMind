-- Graph storage using PG native tables (AGE extension to be added later)
CREATE TABLE IF NOT EXISTS graph_nodes (
    graph_name  TEXT NOT NULL,
    node_id     TEXT NOT NULL,
    label       TEXT NOT NULL,
    properties  JSONB DEFAULT '{}',
    tenant_id   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (graph_name, node_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    graph_name  TEXT NOT NULL,
    edge_id     TEXT NOT NULL,
    src_id      TEXT NOT NULL,
    dst_id      TEXT NOT NULL,
    rel_type    TEXT NOT NULL,
    properties  JSONB DEFAULT '{}',
    tenant_id   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (graph_name, edge_id)
);

CREATE INDEX IF NOT EXISTS idx_nodes_tenant ON graph_nodes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_nodes_label ON graph_nodes(graph_name, label);
CREATE INDEX IF NOT EXISTS idx_edges_src ON graph_edges(graph_name, src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON graph_edges(graph_name, dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_rel ON graph_edges(graph_name, rel_type);
CREATE INDEX IF NOT EXISTS idx_edges_tenant ON graph_edges(tenant_id);

-- Platform metadata tables
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE,
    tenant_id   TEXT NOT NULL REFERENCES tenants(tenant_id),
    role        TEXT DEFAULT 'user',
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tokens (
    token       TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    scopes      TEXT[] DEFAULT '{}',
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS asset_types (
    type            TEXT PRIMARY KEY,
    definition_yaml TEXT NOT NULL,
    tenant_id       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Tenant secrets (AES-256-GCM encrypted)
CREATE TABLE IF NOT EXISTS tenant_secrets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    key_name        VARCHAR(100) NOT NULL,
    encrypted_value BYTEA NOT NULL,
    iv              BYTEA NOT NULL,
    auth_tag        BYTEA NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    created_by      TEXT,

    UNIQUE(tenant_id, key_name)
);

CREATE INDEX IF NOT EXISTS idx_secrets_tenant ON tenant_secrets(tenant_id);

-- Secret access audit log
CREATE TABLE IF NOT EXISTS secret_access_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   TEXT NOT NULL,
    key_name    VARCHAR(100) NOT NULL,
    task_id     TEXT,
    ray_job_id  TEXT,
    accessed_by TEXT NOT NULL,
    accessed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_secret_log_tenant ON secret_access_log(tenant_id, accessed_at);
