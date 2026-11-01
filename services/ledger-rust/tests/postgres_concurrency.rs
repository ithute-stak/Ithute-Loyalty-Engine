//! Database-backed concurrency checks. Set LEDGER_TEST_DATABASE_URL to a
//! disposable migrated PostgreSQL database. Never run against production.
#![cfg(feature = "postgres")]

use ithute_loyalty_ledger::postgres::{post, reconcile, reverse, Operation, PostError};
use sqlx::{PgPool, Row};
use uuid::Uuid;

async fn fixture(pool: &PgPool) -> (Uuid, Uuid) {
    let tenant = Uuid::new_v4();
    let programme = Uuid::new_v4();
    let account = Uuid::new_v4();
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("INSERT INTO tenants(id,name,slug,status) VALUES($1,'Rust CI',$2,'active')")
        .bind(tenant).bind(tenant.to_string()).execute(&mut *tx).await.unwrap();
    sqlx::query("SELECT set_config('app.tenant_id',$1,true)")
        .bind(tenant.to_string()).execute(&mut *tx).await.unwrap();
    sqlx::query("INSERT INTO loyalty_programmes(id,tenant_id,code,name) VALUES($1,$2,'CI','CI')")
        .bind(programme).bind(tenant).execute(&mut *tx).await.unwrap();
    sqlx::query("INSERT INTO points_accounts(id,tenant_id,programme_id,customer_ref,balance) VALUES($1,$2,$3,'ci',0)")
        .bind(account).bind(tenant).bind(programme).execute(&mut *tx).await.unwrap();
    tx.commit().await.unwrap();
    (tenant, account)
}

async fn teardown(pool: &PgPool, tenant: Uuid) {
    let mut tx = pool.begin().await.unwrap();
    sqlx::query("SELECT set_config('app.tenant_id',$1,true)")
        .bind(tenant.to_string()).execute(&mut *tx).await.unwrap();
    // Only disposable CI fixture data. Ledger's trigger blocks deleting entries:
    // fixture cleanup is handled by dropping the disposable database after the run.
    tx.rollback().await.unwrap();
}

#[tokio::test(flavor = "current_thread")]
async fn concurrent_redemption_cannot_double_spend() {
    let Ok(url) = std::env::var("LEDGER_TEST_DATABASE_URL") else { return; };
    let pool = PgPool::connect(&url).await.unwrap();
    let (tenant, account) = fixture(&pool).await;
    post(&pool, tenant, account, "sale-1", Operation::Earn, 100).await.unwrap();

    let (a, b) = tokio::join!(
        post(&pool, tenant, account, "redeem-a", Operation::Redeem, 80),
        post(&pool, tenant, account, "redeem-b", Operation::Redeem, 80),
    );
    let successful = [a, b].into_iter().filter(|r| r.is_ok()).count();
    assert_eq!(successful, 1);
    assert_eq!(reconcile(&pool, tenant, account).await.unwrap(), (20, 20));
    teardown(&pool, tenant).await;
}

#[tokio::test(flavor = "current_thread")]
async fn retry_refund_and_reconcile() {
    let Ok(url) = std::env::var("LEDGER_TEST_DATABASE_URL") else { return; };
    let pool = PgPool::connect(&url).await.unwrap();
    let (tenant, account) = fixture(&pool).await;
    assert_eq!(post(&pool, tenant, account, "purchase", Operation::Earn, 50).await.unwrap(), 50);
    assert_eq!(post(&pool, tenant, account, "purchase", Operation::Earn, 50).await.unwrap(), 50);
    assert_eq!(reverse(&pool, tenant, account, "refund", "purchase").await.unwrap(), 0);
    assert_eq!(reverse(&pool, tenant, account, "refund", "purchase").await.unwrap(), 0);
    assert!(matches!(reverse(&pool, tenant, account, "refund-two", "purchase").await, Err(PostError::IdempotencyConflict)));
    assert_eq!(reconcile(&pool, tenant, account).await.unwrap(), (0, 0));
    teardown(&pool, tenant).await;
}
