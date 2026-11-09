-- Decision engine tables (schema decision_engine, owned by role decision_engine). Idempotent.
SET search_path = decision_engine;

CREATE TABLE IF NOT EXISTS ruleset (
    id          serial PRIMARY KEY,
    flow        text NOT NULL,            -- 'claim' | 'prior_auth'
    version     int  NOT NULL,
    body        jsonb NOT NULL,           -- {"default": {...}, "rules": [...]}
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    is_active   boolean NOT NULL DEFAULT false,
    UNIQUE (flow, version)
);

CREATE TABLE IF NOT EXISTS decision (
    id               bigserial PRIMARY KEY,
    flow             text NOT NULL,
    subject_id       text NOT NULL,       -- claim id or prior-auth request id
    member_id        text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    outcome          text NOT NULL,
    queue            text NOT NULL,
    amount           numeric(12,2),       -- claim total or PA estimated cost
    reasons          jsonb NOT NULL,
    request          jsonb NOT NULL,      -- the claim / PA request as received
    facts            jsonb NOT NULL,      -- everything rules saw (enables backtesting)
    explanations     jsonb,               -- SHAP contributions per model
    rule_trace       jsonb NOT NULL,
    ruleset_version  int NOT NULL,
    model_versions   jsonb,
    latency_ms       numeric(10,1),
    injected         text,                -- simulator ground truth (fraud scenario), NULL = genuine
    review_status    text NOT NULL DEFAULT 'none',   -- none | open | resolved
    review_outcome   text,
    review_note      text,
    reviewed_at      timestamptz
);
CREATE INDEX IF NOT EXISTS decision_flow_time ON decision (flow, created_at DESC);
CREATE INDEX IF NOT EXISTS decision_member ON decision (member_id);
CREATE INDEX IF NOT EXISTS decision_queue ON decision (flow, review_status, queue);

-- Claims received by the engine (for duplicate / velocity checks against new submissions).
CREATE TABLE IF NOT EXISTS incoming_claim (
    claim_id      text PRIMARY KEY,
    member_id     text NOT NULL,
    service_date  date NOT NULL,
    signature     text NOT NULL,
    decision_id   bigint REFERENCES decision(id) ON DELETE CASCADE,
    in_history    boolean NOT NULL DEFAULT false  -- replayed real claim already in synpuf history
);
CREATE INDEX IF NOT EXISTS incoming_claim_member ON incoming_claim (member_id, service_date);

-- Member risk scores from the cost model (rescored whenever the champion changes).
CREATE TABLE IF NOT EXISTS member_risk (
    member_id       text PRIMARY KEY,
    predicted_cost  numeric(12,2) NOT NULL,
    risk_pct        real NOT NULL,        -- percentile among members, 0-100
    risk_tier       text NOT NULL,
    model_version   text NOT NULL
);
CREATE INDEX IF NOT EXISTS member_risk_tier ON member_risk (risk_tier, predicted_cost DESC);
