//! Database-backed concurrency checks. Set LEDGER_TEST_DATABASE_URL (restricted role) and LEDGER_FIXTURE_DATABASE_URL (owner) to a
//! disposable migrated PostgreSQL database. Never run against production.
#![cfg(feature = "postgres")]

use ithute_loyalty_ledger::postgres::{post, reconcile, reverse, Operation, PostError};
use sqlx::PgPool;
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

#[tokio::test(flavor = "current_thread")]
async fn concurrent_redemption_cannot_double_spend() {
    let Ok(url) = std::env::var("LEDGER_TEST_DATABASE_URL") else {
        assert_ne!(
            std::env::var("LEDGER_REQUIRE_POSTGRES_TESTS").as_deref(), Ok("1"),
            "CI requires LEDGER_TEST_DATABASE_URL; do not silently skip PostgreSQL tests"
        );
        return;
    };
    let owner_url = std::env::var("LEDGER_FIXTURE_DATABASE_URL")
        .expect("owner fixture URL required for ledger integration tests");
    assert_ne!(url, owner_url, "runtime and fixture credentials must differ");
    let owner_pool = PgPool::connect(&owner_url).await.unwrap();
    let pool = PgPool::connect(&url).await.unwrap();
    let (tenant, account) = fixture(&owner_pool).await;
    post(&pool, tenant, account, "sale-1", Operation::Earn, 100).await.unwrap();

    let (a, b) = tokio::join!(
        post(&pool, tenant, account, "redeem-a", Operation::Redeem, 80),
        post(&pool, tenant, account, "redeem-b", Operation::Redeem, 80),
    );
    let successful = [a, b].into_iter().filter(|r| r.is_ok()).count();
    assert_eq!(successful, 1);
    assert_eq!(reconcile(&pool, tenant, account).await.unwrap(), (20, 20));
    // Disposable CI database is discarded after tests.
}

#[tokio::test(flavor = "current_thread")]
async fn retry_refund_and_reconcile() {
    let Ok(url) = std::env::var("LEDGER_TEST_DATABASE_URL") else {
        assert_ne!(
            std::env::var("LEDGER_REQUIRE_POSTGRES_TESTS").as_deref(), Ok("1"),
            "CI requires LEDGER_TEST_DATABASE_URL; do not silently skip PostgreSQL tests"
        );
        return;
    };
    let pool = PgPool::connect(&url).await.unwrap();
    let (tenant, account) = fixture(&pool).await;
    assert_eq!(post(&pool, tenant, account, "purchase", Operation::Earn, 50).await.unwrap(), 50);
    assert_eq!(post(&pool, tenant, account, "purchase", Operation::Earn, 50).await.unwrap(), 50);
    assert_eq!(reverse(&pool, tenant, account, "refund", "purchase").await.unwrap(), 0);
    assert_eq!(reverse(&pool, tenant, account, "refund", "purchase").await.unwrap(), 0);
    assert!(matches!(reverse(&pool, tenant, account, "refund-two", "purchase").await, Err(PostError::IdempotencyConflict)));
    assert_eq!(reconcile(&pool, tenant, account).await.unwrap(), (0, 0));
    // Disposable CI database is discarded after tests.
}

#[tokio::test(flavor = "current_thread")]
async fn restricted_role_cannot_cross_tenant_account_boundary() {
    let Ok(runtime_url) = std::env::var("LEDGER_TEST_DATABASE_URL") else { return; };
    let owner_url = std::env::var("LEDGER_FIXTURE_DATABASE_URL")
        .expect("owner fixture database URL required");
    assert_ne!(runtime_url, owner_url);
    let owner = PgPool::connect(&owner_url).await.unwrap();
    let restricted = PgPool::connect(&runtime_url).await.unwrap();
    let (tenant_a, account_a) = fixture(&owner).await;
    let (tenant_b, account_b) = fixture(&owner).await;
    post(&restricted, tenant_a, account_a, "a-award", Operation::Earn, 35).await.unwrap();
    post(&restricted, tenant_b, account_b, "b-award", Operation::Earn, 60).await.unwrap();

    // Supplying B's account with A's tenant context must not access B.
    assert!(matches!(
        post(&restricted, tenant_a, account_b, "forged", Operation::Redeem, 10).await,
        Err(PostError::MissingAccount)
    ));
    assert!(matches!(
        reconcile(&restricted, tenant_b, account_a).await,
        Err(PostError::MissingAccount)
    ));
    // An unset tenant context must never reveal either company's records.
    let mut tx = restricted.begin().await.unwrap();
    sqlx::query("SELECT set_config('app.tenant_id','',true)")
        .execute(&mut *tx).await.unwrap();
    let visible: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM points_accounts WHERE id=$1 OR id=$2"
    ).bind(account_a).bind(account_b).fetch_one(&mut *tx).await.unwrap();
    assert_eq!(visible, 0);
    tx.rollback().await.unwrap();

    assert_eq!(reconcile(&restricted, tenant_a, account_a).await.unwrap(), (35, 35));
    assert_eq!(reconcile(&restricted, tenant_b, account_b).await.unwrap(), (60, 60));
}
