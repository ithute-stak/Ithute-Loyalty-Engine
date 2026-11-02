#[cfg(not(feature = "service"))]
fn main() { eprintln!("Build with --features service to run ledger HTTP server"); }

#[cfg(feature = "service")]
mod server {
    use axum::{body::Bytes, extract::State, http::{HeaderMap, StatusCode}, routing::post, Json, Router};
    use hmac::{Hmac, Mac};
    use sha2::Sha256;
    use std::time::{SystemTime, UNIX_EPOCH};
    use serde::{Deserialize, Serialize};
    use sqlx::PgPool;
    use std::{collections::HashSet, env, net::SocketAddr, sync::Arc};
    use uuid::Uuid;
    use ithute_loyalty_ledger::postgres::{post as ledger_post, reverse, reconcile, Operation, PostError};

    #[derive(Clone)]
    struct AppState { pool: PgPool, secret: Arc<String>, allowed_tenants: Arc<HashSet<Uuid>> }

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

    fn authorized(h: &HeaderMap, secret: &str, body: &[u8]) -> bool {
        let (Some(ts), Some(sig)) = (h.get("x-ledger-timestamp"), h.get("x-ledger-signature"))
            else { return false; };
        let (Ok(ts), Ok(sig)) = (ts.to_str(), sig.to_str()) else { return false; };
        let Ok(when) = ts.parse::<u64>() else { return false; };
        let Ok(now) = SystemTime::now().duration_since(UNIX_EPOCH) else { return false; };
        if now.as_secs().abs_diff(when) > 60 { return false; }
        let Ok(received) = hex::decode(sig) else { return false; };
        let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(secret.as_bytes()) else { return false; };
        mac.update(ts.as_bytes());
        mac.update(b".");
        mac.update(body);
        mac.verify_slice(&received).is_ok()
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
        if !authorized(&headers, &s.secret, &body) { return Err(StatusCode::UNAUTHORIZED); }
        let c: Command = serde_json::from_slice(&body).map_err(|_| StatusCode::BAD_REQUEST)?;
        if !s.allowed_tenants.contains(&c.tenant_id) { return Err(StatusCode::FORBIDDEN); }
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
    struct BalanceQuery { tenant_id: Uuid, account_id: Uuid }
    #[derive(Serialize)]
    struct ReconcileBody { stored: i64, entries_total: i64 }
    async fn check(State(s): State<AppState>, headers: HeaderMap, body: Bytes)
        -> Result<Json<ReconcileBody>, StatusCode> {
        if !authorized(&headers, &s.secret, &body) { return Err(StatusCode::UNAUTHORIZED); }
        let q: BalanceQuery = serde_json::from_slice(&body).map_err(|_| StatusCode::BAD_REQUEST)?;
        if !s.allowed_tenants.contains(&q.tenant_id) { return Err(StatusCode::FORBIDDEN); }
        let (stored, entries_total) = reconcile(&s.pool, q.tenant_id, q.account_id).await.map_err(error)?;
        Ok(Json(ReconcileBody { stored, entries_total }))
    }
    #[cfg(test)]
    mod auth_tests {
        #[test]
        fn rust_owned_tenant_scope_excludes_unlisted_company() {
            let company_a = uuid::Uuid::new_v4();
            let company_b = uuid::Uuid::new_v4();
            let permitted = std::collections::HashSet::from([company_a]);
            assert!(permitted.contains(&company_a));
            assert!(!permitted.contains(&company_b));
        }

        use super::*;
        use axum::http::HeaderValue;

        fn signed(body: &[u8], timestamp: u64) -> HeaderMap {
            let mut headers = HeaderMap::new();
            let ts = timestamp.to_string();
            let mut mac = Hmac::<Sha256>::new_from_slice(b"01234567890123456789012345678901").unwrap();
            mac.update(ts.as_bytes());
            mac.update(b".");
            mac.update(body);
            headers.insert("x-ledger-timestamp", HeaderValue::from_str(&ts).unwrap());
            headers.insert("x-ledger-signature", HeaderValue::from_str(&hex::encode(mac.finalize().into_bytes())).unwrap());
            headers
        }

        #[test]
        fn signed_request_accepts_valid_and_rejects_tampering() {
            let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
            let headers = signed(b"{\"tenant_id\":\"a\"}", now);
            let secret = "01234567890123456789012345678901";
            assert!(authorized(&headers, secret, b"{\"tenant_id\":\"a\"}"));
            assert!(!authorized(&headers, secret, b"{\"tenant_id\":\"b\"}"));
            assert!(!authorized(&headers, "different-secret-different-secret", b"{\"tenant_id\":\"a\"}"));
            assert!(!authorized(&HeaderMap::new(), secret, b"{\"tenant_id\":\"a\"}"));
            let expired = signed(b"{}", now.saturating_sub(120));
            assert!(!authorized(&expired, secret, b"{}"));
        }
    }

    pub async fn run() {
        let url = env::var("LEDGER_DATABASE_URL").expect("LEDGER_DATABASE_URL required");
        let secret = env::var("LEDGER_INTERNAL_KEY").expect("LEDGER_INTERNAL_KEY required");
        assert!(secret.len() >= 32, "internal key must contain at least 32 characters");
        // Operational allowlist is configured at the Rust service, not forwarded by API.
        // Empty/malformed lists fail startup; never default to permitting all tenants.
        let allowed = env::var("LEDGER_ALLOWED_TENANTS").expect("LEDGER_ALLOWED_TENANTS required");
        let allowed_tenants: HashSet<Uuid> = allowed.split(',')
            .map(|s| s.trim().parse::<Uuid>().expect("invalid authorized tenant UUID"))
            .collect();
        assert!(!allowed_tenants.is_empty(), "at least one authorized tenant required");
        let pool = PgPool::connect(&url).await.expect("ledger DB unavailable");
        let app = Router::new().route("/internal/v1/commands", post(command))
            .route("/internal/v1/reconcile", post(check))
            .with_state(AppState { pool, secret: Arc::new(secret), allowed_tenants: Arc::new(allowed_tenants) });
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
