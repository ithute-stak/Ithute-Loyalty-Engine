#[cfg(not(feature = "service"))]
fn main() { eprintln!("Build with --features service to run ledger HTTP server"); }

#[cfg(feature = "service")]
mod server {
    use axum::{extract::State, http::{HeaderMap, StatusCode}, routing::post, Json, Router};
    use serde::{Deserialize, Serialize};
    use sqlx::PgPool;
    use std::{env, net::SocketAddr, sync::Arc};
    use uuid::Uuid;
    use ithute_loyalty_ledger::postgres::{post as ledger_post, reverse, reconcile, Operation, PostError};

    #[derive(Clone)]
    struct AppState { pool: PgPool, secret: Arc<String> }

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

    fn authorized(h: &HeaderMap, secret: &str) -> bool {
        let Some(v) = h.get("x-internal-ledger-key") else { return false; };
        let Ok(v) = v.to_str() else { return false; };
        // This must be used only behind trusted private network controls.
        !v.is_empty() && subtle::ConstantTimeEq::ct_eq(v.as_bytes(), secret.as_bytes()).into()
    }
    fn error(e: PostError) -> StatusCode {
        match e {
            PostError::InvalidAmount => StatusCode::UNPROCESSABLE_ENTITY,
            PostError::Insufficient | PostError::IdempotencyConflict => StatusCode::CONFLICT,
            PostError::MissingAccount => StatusCode::NOT_FOUND,
            PostError::Database(_) => StatusCode::SERVICE_UNAVAILABLE,
        }
    }
    async fn command(State(s): State<AppState>, headers: HeaderMap, Json(c): Json<Command>)
        -> Result<Json<ResultBody>, StatusCode> {
        if !authorized(&headers, &s.secret) { return Err(StatusCode::UNAUTHORIZED); }
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
    async fn check(State(s): State<AppState>, headers: HeaderMap, Json(q): Json<BalanceQuery>)
        -> Result<Json<ReconcileBody>, StatusCode> {
        if !authorized(&headers, &s.secret) { return Err(StatusCode::UNAUTHORIZED); }
        let (stored, entries_total) = reconcile(&s.pool, q.tenant_id, q.account_id).await.map_err(error)?;
        Ok(Json(ReconcileBody { stored, entries_total }))
    }
    pub async fn run() {
        let url = env::var("LEDGER_DATABASE_URL").expect("LEDGER_DATABASE_URL required");
        let secret = env::var("LEDGER_INTERNAL_KEY").expect("LEDGER_INTERNAL_KEY required");
        assert!(secret.len() >= 32, "internal key must contain at least 32 characters");
        let pool = PgPool::connect(&url).await.expect("ledger DB unavailable");
        let app = Router::new().route("/internal/v1/commands", post(command))
            .route("/internal/v1/reconcile", post(check))
            .with_state(AppState { pool, secret: Arc::new(secret) });
        // Private listener only; a reverse proxy or Docker private network is required.
        let addr: SocketAddr = "127.0.0.1:8090".parse().unwrap();
        let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
        axum::serve(listener, app).await.unwrap();
    }
}
#[cfg(feature = "service")]
#[tokio::main]
async fn main() { server::run().await; }
