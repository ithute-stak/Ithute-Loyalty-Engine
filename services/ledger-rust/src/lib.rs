//! Pure in-memory domain model for an append-only loyalty point ledger.
//! This is NOT a database or a concurrency-safe production posting service.
//! Persist commands in PostgreSQL with tenant/member locks and unique keys.
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Account {
    pub tenant_id: u128,
    pub programme_id: u128,
    pub membership_id: u128,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Kind {
    Earn,
    Redeem,
    Reverse { original_event_id: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub event_id: String,
    pub account: Account,
    pub delta: i64,
    pub kind: Kind,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LedgerError {
    InvalidAmount,
    DuplicateConflict,
    InsufficientPoints,
    Overflow,
    NotFound,
    AlreadyReversed,
    WrongAccount,
    CannotReverseReversal,
}

#[derive(Default)]
pub struct Ledger {
    entries: Vec<Entry>,
    event_index: HashMap<(Account, String), usize>,
    reversals: HashSet<(Account, String)>,
    balances: HashMap<Account, i64>,
}

impl Ledger {
    pub fn balance(&self, account: Account) -> i64 {
        *self.balances.get(&account).unwrap_or(&0)
    }

    pub fn entries(&self) -> &[Entry] {
        &self.entries
    }

    pub fn earn(&mut self, account: Account, event_id: &str, points: i64) -> Result<i64, LedgerError> {
        if points <= 0 { return Err(LedgerError::InvalidAmount); }
        self.post(Entry {
            event_id: event_id.into(), account, delta: points, kind: Kind::Earn,
        })
    }

    pub fn redeem(&mut self, account: Account, event_id: &str, points: i64) -> Result<i64, LedgerError> {
        if points <= 0 { return Err(LedgerError::InvalidAmount); }
        self.post(Entry {
            event_id: event_id.into(), account, delta: -points, kind: Kind::Redeem,
        })
    }

    pub fn reverse(&mut self, account: Account, event_id: &str, original_event_id: &str) -> Result<i64, LedgerError> {
        let original_index = *self.event_index
            .get(&(account, original_event_id.to_owned()))
            .ok_or(LedgerError::NotFound)?;
        let original = &self.entries[original_index];
        if matches!(original.kind, Kind::Reverse { .. }) {
            return Err(LedgerError::CannotReverseReversal);
        }
        let reversal = Entry {
            event_id: event_id.into(),
            account,
            delta: original.delta.checked_neg().ok_or(LedgerError::Overflow)?,
            kind: Kind::Reverse { original_event_id: original_event_id.into() },
        };
        self.post(reversal)
    }

    fn post(&mut self, entry: Entry) -> Result<i64, LedgerError> {
        if entry.event_id.trim().is_empty() {
            return Err(LedgerError::InvalidAmount);
        }
        let key = (entry.account, entry.event_id.clone());
        if let Some(&i) = self.event_index.get(&key) {
            if self.entries[i] == entry {
                return Ok(self.balance(entry.account)); // exact retry
            }
            return Err(LedgerError::DuplicateConflict);
        }
        if let Kind::Reverse { ref original_event_id } = entry.kind {
            if self.reversals.contains(&(entry.account, original_event_id.clone())) {
                return Err(LedgerError::AlreadyReversed);
            }
        }
        let current = self.balance(entry.account);
        let next = current.checked_add(entry.delta).ok_or(LedgerError::Overflow)?;
        if next < 0 {
            return Err(LedgerError::InsufficientPoints);
        }
        let i = self.entries.len();
        if let Kind::Reverse { ref original_event_id } = entry.kind {
            self.reversals.insert((entry.account, original_event_id.clone()));
        }
        self.event_index.insert(key, i);
        self.balances.insert(entry.account, next);
        self.entries.push(entry);
        Ok(next)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const A: Account = Account { tenant_id: 1, programme_id: 7, membership_id: 3 };
    const B: Account = Account { tenant_id: 2, programme_id: 7, membership_id: 3 };

    #[test]
    fn earn_redeem_and_exact_retry() {
        let mut l = Ledger::default();
        assert_eq!(l.earn(A, "sale-1", 100), Ok(100));
        assert_eq!(l.earn(A, "sale-1", 100), Ok(100));
        assert_eq!(l.entries().len(), 1);
        assert_eq!(l.redeem(A, "reward-1", 35), Ok(65));
        assert_eq!(l.redeem(A, "reward-2", 66), Err(LedgerError::InsufficientPoints));
        assert_eq!(l.balance(A), 65);
    }

    #[test]
    fn conflicting_retry_is_rejected() {
        let mut l = Ledger::default();
        l.earn(A, "sale", 5).unwrap();
        assert_eq!(l.earn(A, "sale", 6), Err(LedgerError::DuplicateConflict));
    }

    #[test]
    fn tenant_accounts_are_independent() {
        let mut l = Ledger::default();
        l.earn(A, "same-id", 20).unwrap();
        l.earn(B, "same-id", 8).unwrap();
        assert_eq!(l.balance(A), 20);
        assert_eq!(l.balance(B), 8);
    }

    #[test]
    fn reversals_are_single_use() {
        let mut l = Ledger::default();
        l.earn(A, "purchase", 30).unwrap();
        assert_eq!(l.reverse(A, "refund", "purchase"), Ok(0));
        assert_eq!(l.reverse(A, "refund", "purchase"), Ok(0));
        assert_eq!(l.reverse(A, "another-refund", "purchase"), Err(LedgerError::AlreadyReversed));
        assert_eq!(l.entries().len(), 2);
    }

    #[test]
    fn cannot_reverse_earned_points_already_spent() {
        let mut l = Ledger::default();
        l.earn(A, "purchase", 20).unwrap();
        l.redeem(A, "reward", 15).unwrap();
        assert_eq!(l.reverse(A, "refund", "purchase"), Err(LedgerError::InsufficientPoints));
        assert_eq!(l.balance(A), 5);
    }

    #[test]
    fn overflow_rejected_without_mutation() {
        let mut l = Ledger::default();
        l.earn(A, "first", i64::MAX).unwrap();
        assert_eq!(l.earn(A, "second", 1), Err(LedgerError::Overflow));
        assert_eq!(l.entries().len(), 1);
    }
}
