#[cfg(not(feature = "service"))]
fn main() { eprintln!("Build with --features service to run ledger HTTP server"); }

#[cfg(feature = "service")]
mod server {
    use axum::{body::Bytes, extract::{DefaultBodyLimit, State}, http::{HeaderMap, StatusCode}, routing::{get, post}, Json, Router};
    use hmac::{Hmac, Mac};
    use sha2::Sha256;
    use std::time::{SystemTime, UNIX_EPOCH};
    use serde::{Deserialize, Serialize};
    use sqlx::PgPool;
    use std::{collections::{HashMap, HashSet}, env, net::SocketAddr, sync::Arc};
    use uuid::Uuid;
    use ithute_loyalty_ledger::postgres::{post as ledger_post, reverse, reconcile, Operation, PostError};

    #[derive(Clone)]
    struct AppState { pool: PgPool, keys: Arc<HashMap<String, SigningKey>> }

    #[derive(Clone, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct SigningKey {
        id: String,
        secret: String,
        tenants: HashSet<Uuid>,
    }
    fn is_scoped(keys: &HashMap<String, SigningKey>, key_id: &str, tenant: Uuid) -> bool {
        keys.get(key_id).is_some_and(|key| key.tenants.contains(&tenant))
    }

    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Command {
        tenant_id: Uuid,
        account_id: Uuid,
        event_id: String,
        operation: String,
        points: Option<i64>,
        original_event_id: Option<String>,
    }
    #[derive(Serialize)]
    struct ResultBody { balance: i64 }

    fn authorized(h: &HeaderMap, keys: &HashMap<String, SigningKey>, body: &[u8]) -> Option<String> {
        let kid = h.get("x-ledger-key-id")?.to_str().ok()?;
        let key = keys.get(kid)?;
        let (Some(ts), Some(sig)) = (h.get("x-ledger-timestamp"), h.get("x-ledger-signature"))
            else { return None; };
        let (Ok(ts), Ok(sig)) = (ts.to_str(), sig.to_str()) else { return None; };
        let Ok(when) = ts.parse::<u64>() else { return None; };
        let Ok(now) = SystemTime::now().duration_since(UNIX_EPOCH) else { return None; };
        if now.as_secs().abs_diff(when) > 60 { return None; }
        let Ok(received) = hex::decode(sig) else { return None; };
        let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(key.secret.as_bytes()) else { return None; };
        mac.update(kid.as_bytes());
        mac.update(b".");
        mac.update(ts.as_bytes());
        mac.update(b".");
        mac.update(body);
        mac.verify_slice(&received).is_ok().then(|| kid.to_owned())
    }
    fn error(e: PostError) -> StatusCode {
        match e {
            PostError::InvalidAmount => StatusCode::UNPROCESSABLE_ENTITY,
            PostError::Insufficient | PostError::IdempotencyConflict => StatusCode::CONFLICT,
            PostError::MissingAccount => StatusCode::NOT_FOUND,
            PostError::Database(_) => StatusCode::SERVICE_UNAVAILABLE,
        }
    }
    async fn command(State(s): State<AppState>, headers: HeaderMap, body: Bytes)
        -> Result<Json<ResultBody>, StatusCode> {
        let key_id = authorized(&headers, &s.keys, &body).ok_or(StatusCode::UNAUTHORIZED)?;
        let c: Command = serde_json::from_slice(&body).map_err(|_| StatusCode::BAD_REQUEST)?;
        if !is_scoped(&s.keys, &key_id, c.tenant_id) { return Err(StatusCode::FORBIDDEN); }
        let balance = match c.operation.as_str() {
            "earn" | "redeem" => {
                if c.original_event_id.is_some() { return Err(StatusCode::UNPROCESSABLE_ENTITY); }
                let Some(points) = c.points else { return Err(StatusCode::UNPROCESSABLE_ENTITY); };
                let op = if c.operation == "earn" { Operation::Earn } else { Operation::Redeem };
                ledger_post(&s.pool, c.tenant_id, c.account_id, &c.event_id, op, points).await
            },
            "reverse" => {
                if c.points.is_some() { return Err(StatusCode::UNPROCESSABLE_ENTITY); }
                let Some(orig) = c.original_event_id else { return Err(StatusCode::UNPROCESSABLE_ENTITY); };
                reverse(&s.pool, c.tenant_id, c.account_id, &c.event_id, &orig).await
            },
            _ => return Err(StatusCode::UNPROCESSABLE_ENTITY),
        }.map_err(error)?;
        Ok(Json(ResultBody { balance }))
    }
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct BalanceQuery { tenant_id: Uuid, account_id: Uuid }
    #[derive(Serialize)]
    struct ReconcileBody { stored: i64, entries_total: i64 }
    async fn check(State(s): State<AppState>, headers: HeaderMap, body: Bytes)
        -> Result<Json<ReconcileBody>, StatusCode> {
        let key_id = authorized(&headers, &s.keys, &body).ok_or(StatusCode::UNAUTHORIZED)?;
        let q: BalanceQuery = serde_json::from_slice(&body).map_err(|_| StatusCode::BAD_REQUEST)?;
        if !is_scoped(&s.keys, &key_id, q.tenant_id) { return Err(StatusCode::FORBIDDEN); }
        let (stored, entries_total) = reconcile(&s.pool, q.tenant_id, q.account_id).await.map_err(error)?;
        Ok(Json(ReconcileBody { stored, entries_total }))
    }
    // Internal-only readiness probe: expose no tenant details or DB credentials.
    async fn ready(State(s): State<AppState>) -> StatusCode {
        match sqlx::query("SELECT 1").execute(&s.pool).await {
            Ok(_) => StatusCode::NO_CONTENT,
            Err(_) => StatusCode::SERVICE_UNAVAILABLE,
        }
    }

    #[cfg(test)]
    mod auth_tests {
        use super::*;
        use axum::http::HeaderValue;
        fn keys(tenant: Uuid) -> HashMap<String, SigningKey> {
            HashMap::from([("merchant-a-v1".to_owned(), SigningKey {
                id: "merchant-a-v1".into(), secret: "x".repeat(40),
                tenants: HashSet::from([tenant]),
            })])
        }
        fn signed(body: &[u8], ts: u64) -> HeaderMap {
            let mut h = HeaderMap::new();
            let ts = ts.to_string();
            let mut mac = Hmac::<Sha256>::new_from_slice("x".repeat(40).as_bytes()).unwrap();
            mac.update(b"merchant-a-v1.");
            mac.update(ts.as_bytes());
            mac.update(b".");
            mac.update(body);
            h.insert("x-ledger-key-id", HeaderValue::from_static("merchant-a-v1"));
            h.insert("x-ledger-timestamp", HeaderValue::from_str(&ts).unwrap());
            h.insert("x-ledger-signature", HeaderValue::from_str(&hex::encode(mac.finalize().into_bytes())).unwrap());
            h
        }
        #[tokio::test]
        async fn http_command_rejects_wrong_tenant_before_database_access() {
            let tenant_a = Uuid::new_v4();
            let tenant_b = Uuid::new_v4();
            let pool = sqlx::postgres::PgPoolOptions::new()
                .connect_lazy("postgres://unused:unused@localhost:5432/unused").unwrap();
            let state = AppState { pool, keys: Arc::new(keys(tenant_a)) };
            let body = format!(
                "{{\"tenant_id\":\"{}\",\"account_id\":\"{}\",\"event_id\":\"no-access\",\"operation\":\"earn\",\"points\":5}}",
                tenant_b, Uuid::new_v4()
            );
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
            let response = command(State(state.clone()), signed(body.as_bytes(), now),
                Bytes::from(body)).await;
            assert!(matches!(response, Err(StatusCode::FORBIDDEN)));

            let body = format!(
                "{{\"tenant_id\":\"{}\",\"account_id\":\"{}\",\"event_id\":\"no-access\",\"operation\":\"earn\",\"points\":5}}",
                tenant_b, Uuid::new_v4()
            );
            let response = command(State(state), HeaderMap::new(), Bytes::from(body)).await;
            assert!(matches!(response, Err(StatusCode::UNAUTHORIZED)));
        }
        #[tokio::test]
        async fn signed_command_payload_cannot_be_reused_as_reconciliation_query() {
            let tenant = Uuid::new_v4();
            let pool = sqlx::postgres::PgPoolOptions::new()
                .connect_lazy("postgres://unused:unused@localhost:5432/unused").unwrap();
            let state = AppState { pool, keys: Arc::new(keys(tenant)) };
            let command_body = format!(
                "{{\\"tenant_id\\":\\"{}\\",\\"account_id\\":\\"{}\\",\\"event_id\\":\\"sale\\",\\"operation\\":\\"earn\\",\\"points\\":5}}",
                tenant, Uuid::new_v4()
            );
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
            let response = check(
                State(state),
                signed(command_body.as_bytes(), now),
                Bytes::from(command_body),
            ).await;
            assert!(matches!(response, Err(StatusCode::BAD_REQUEST)));
        }

        #[test]
        fn signed_request_checks_signature_key_scope_and_expiry() {
            let a = Uuid::new_v4();
            let b = Uuid::new_v4();
            let keys = keys(a);
            assert!(is_scoped(&keys, "merchant-a-v1", a));
            assert!(!is_scoped(&keys, "merchant-a-v1", b));
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
            let h = signed(b"{}", now);
            assert_eq!(authorized(&h, &keys, b"{}").as_deref(), Some("merchant-a-v1"));
            assert!(authorized(&h, &keys, b"{ }").is_none());
            let mut wrong = h.clone();
            wrong.insert("x-ledger-key-id", HeaderValue::from_static("other-key"));
            assert!(authorized(&wrong, &keys, b"{}").is_none());
            assert!(authorized(&signed(b"{}", now.saturating_sub(120)), &keys, b"{}").is_none());
        }
    }

    pub async fn run() {
        let url = env::var("LEDGER_DATABASE_URL").expect("LEDGER_DATABASE_URL required");
        // Each signing key has an independent tenant allowlist. Unknown/empty config fails closed.
        let raw = env::var("LEDGER_SIGNING_KEYS_JSON").expect("LEDGER_SIGNING_KEYS_JSON required");
        let configured: Vec<SigningKey> = serde_json::from_str(&raw).expect("invalid signing keys JSON");
        assert!(!configured.is_empty(), "at least one signing key required");
        let mut keys = HashMap::new();
        for key in configured {
            assert!(!key.id.is_empty() && key.id.len() <= 128 && key.secret.len() >= 32
                && !key.tenants.is_empty(), "invalid signing key configuration");
            let id = key.id.clone();
            assert!(keys.insert(id, key).is_none(), "duplicate signing key ID");
        }
        let pool = PgPool::connect(&url).await.expect("ledger DB unavailable");
        let app = Router::new().route("/internal/health", get(ready))
            .route("/internal/v1/commands", post(command))
            .route("/internal/v1/reconcile", post(check))
            // Raw Bytes extractors have no small JSON limit by default.
            .layer(DefaultBodyLimit::max(16 * 1024))
            .with_state(AppState { pool, keys: Arc::new(keys) });
        // Private listener only; a reverse proxy or Docker private network is required.
        let bind_address = env::var("LEDGER_BIND_ADDRESS").unwrap_or_else(|_| "127.0.0.1:8090".to_string());
        let addr: SocketAddr = bind_address.parse().expect("invalid LEDGER_BIND_ADDRESS");
        let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
        axum::serve(listener, app).await.unwrap();
    }
}
#[cfg(feature = "service")]
#[tokio::main]
async fn main() { server::run().await; }
