//! PostgreSQL transaction boundary for durable earn/redeem commands.
//! Caller supplies an already-authenticated tenant ID; do not trust HTTP inputs.
use sqlx::{PgPool, Row};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PostError {
    InvalidAmount,
    Insufficient,
    IdempotencyConflict,
    MissingAccount,
    Database(String),
}
impl From<sqlx::Error> for PostError {
    fn from(e: sqlx::Error) -> Self { Self::Database(e.to_string()) }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Operation { Earn, Redeem }
impl Operation {
    fn label(self) -> &'static str {
        match self { Self::Earn => "earn", Self::Redeem => "redeem" }
    }
}

/// Exactly-once *effect* for a given tenant/account/event_id.
/// All database operations run within one transaction; a row lock serializes
/// concurrent commands on the same points account.
pub async fn post(
    pool: &PgPool,
    tenant: Uuid,
    account: Uuid,
    event_id: &str,
    op: Operation,
    points: i64,
) -> Result<i64, PostError> {
    if points <= 0 || event_id.is_empty() || event_id.len() > 200 {
        return Err(PostError::InvalidAmount);
    }
    let delta = match op {
        Operation::Earn => points,
        Operation::Redeem => -points,
    };
    let mut tx = pool.begin().await?;
    sqlx::query("SELECT set_config('app.tenant_id', $1, true)")
        .bind(tenant.to_string()).execute(&mut *tx).await?;
    let current = sqlx::query(
        "SELECT balance FROM points_accounts WHERE tenant_id=$1 AND id=$2 FOR UPDATE"
    ).bind(tenant).bind(account).fetch_optional(&mut *tx).await?;
    let current: i64 = current.ok_or(PostError::MissingAccount)?.try_get("balance")?;
    if let Some(existing) = sqlx::query(
        "SELECT kind, delta, balance_after FROM points_entries          WHERE tenant_id=$1 AND account_id=$2 AND event_id=$3"
    ).bind(tenant).bind(account).bind(event_id)
        .fetch_optional(&mut *tx).await? {
        let kind: String = existing.try_get("kind")?;
        let old_delta: i64 = existing.try_get("delta")?;
        let old_result: i64 = existing.try_get("balance_after")?;
        if kind != op.label() || old_delta != delta {
            return Err(PostError::IdempotencyConflict);
        }
        tx.commit().await?;
        return Ok(old_result);
    }
    let next = current.checked_add(delta).ok_or(PostError::InvalidAmount)?;
    if next < 0 { return Err(PostError::Insufficient); }
    sqlx::query(
        "INSERT INTO points_entries          (id, tenant_id, account_id, event_id, kind, delta, balance_after)          VALUES ($1,$2,$3,$4,$5,$6,$7)"
    ).bind(Uuid::new_v4()).bind(tenant).bind(account).bind(event_id)
        .bind(op.label()).bind(delta).bind(next).execute(&mut *tx).await?;
    sqlx::query(
        "UPDATE points_accounts SET balance=$1 WHERE tenant_id=$2 AND id=$3"
    ).bind(next).bind(tenant).bind(account).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(next)
}
