//! Batch policy parsing from Python dicts.

use aerospike_core::{BatchPolicy, BatchWritePolicy, GenerationPolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::write_policy::parse_ttl;
use super::{
    extract_filter_expression, extract_policy_fields, parse_commit_level, parse_consistency_level,
    parse_generation_policy, parse_read_touch_ttl, parse_record_exists_action, parse_replica,
};

/// Parse a Python policy dict into a BatchPolicy
pub fn parse_batch_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<BatchPolicy> {
    trace!("Parsing batch policy");
    let mut policy = BatchPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "allow_inline" => policy.allow_inline;
        "allow_inline_ssd" => policy.allow_inline_ssd;
        "respond_all_keys" => policy.respond_all_keys
    });

    if let Some(val) = dict.get_item("replica")? {
        policy.replica = parse_replica(val.extract::<i32>()?);
    }
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.consistency_level = parse_consistency_level(val.extract::<i32>()?);
    }
    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.base_policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }

    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Parse the batch-level policy dict into a [`BatchWritePolicy`].
///
/// Mirrors [`super::write_policy::parse_write_policy`] for the write-related
/// fields exposed by `aerospike-core`'s `BatchWritePolicy` struct. Per-record
/// overrides are applied later via [`apply_record_meta`].
pub fn parse_batch_write_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
) -> PyResult<BatchWritePolicy> {
    trace!("Parsing batch write policy");
    let mut policy = BatchWritePolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "durable_delete" => policy.durable_delete
    });

    // Key (send_key) — POLICY_KEY_DIGEST(0) | POLICY_KEY_SEND(1)
    if let Some(val) = dict.get_item("key")? {
        policy.send_key = val.extract::<i32>()? == 1;
    }

    // Exists (record_exists_action) — POLICY_EXISTS_*
    if let Some(val) = dict.get_item("exists")? {
        policy.record_exists_action = parse_record_exists_action(val.extract::<i32>()?);
    }

    // Generation policy — POLICY_GEN_*
    if let Some(val) = dict.get_item("gen")? {
        policy.generation_policy = parse_generation_policy(val.extract::<i32>()?);
    }

    // Commit level — POLICY_COMMIT_LEVEL_*
    if let Some(val) = dict.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(val.extract::<i32>()?);
    }

    // TTL / expiration
    if let Some(val) = dict.get_item("ttl")? {
        policy.expiration = parse_ttl(val.extract::<i64>()?)?;
    }

    // Filter expression
    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Apply per-record meta to a [`BatchWritePolicy`], overriding the batch-level
/// default. Per-record settings always win.
///
/// Supported meta keys mirror the write fields of `BatchWritePolicy`: `ttl`,
/// `gen` (sets `generation` + `GenerationPolicy::ExpectGenEqual`, matching
/// the existing `WriteMeta` semantics for `put`), `key`, `exists`,
/// `commit_level`, `durable_delete`.
pub fn apply_record_meta(
    base: &BatchWritePolicy,
    meta: &Bound<'_, PyDict>,
) -> PyResult<BatchWritePolicy> {
    let mut policy = base.clone();

    if let Some(ttl) = meta.get_item("ttl")? {
        policy.expiration = parse_ttl(ttl.extract::<i64>()?)?;
    }
    if let Some(gen) = meta.get_item("gen")? {
        policy.generation = gen.extract::<u32>()?;
        policy.generation_policy = GenerationPolicy::ExpectGenEqual;
    }
    if let Some(key) = meta.get_item("key")? {
        policy.send_key = key.extract::<i32>()? == 1;
    }
    if let Some(exists) = meta.get_item("exists")? {
        policy.record_exists_action = parse_record_exists_action(exists.extract::<i32>()?);
    }
    if let Some(commit_level) = meta.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(commit_level.extract::<i32>()?);
    }
    if let Some(durable_delete) = meta.get_item("durable_delete")? {
        policy.durable_delete = durable_delete.extract::<bool>()?;
    }

    Ok(policy)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aerospike_core::{CommitLevel, Expiration, RecordExistsAction};

    /// Build a Python dict from `(key, value)` pairs for testing.
    fn build_dict<'py>(
        py: Python<'py>,
        build: impl FnOnce(&Bound<'py, PyDict>),
    ) -> Bound<'py, PyDict> {
        let d = PyDict::new(py);
        build(&d);
        d
    }

    #[test]
    fn parse_batch_write_policy_with_send_key() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("key", 1i32).unwrap();
            });
            let p = parse_batch_write_policy(Some(&d)).expect("parse ok");
            assert!(p.send_key, "key=1 must enable send_key");
        });
    }

    #[test]
    fn parse_batch_write_policy_send_key_zero_means_digest() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("key", 0i32).unwrap();
            });
            let p = parse_batch_write_policy(Some(&d)).expect("parse ok");
            assert!(!p.send_key, "key=0 must keep digest-only behavior");
        });
    }

    #[test]
    fn parse_batch_write_policy_with_exists_create_only() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("exists", 4i32).unwrap();
            });
            let p = parse_batch_write_policy(Some(&d)).expect("parse ok");
            assert_eq!(p.record_exists_action, RecordExistsAction::CreateOnly);
        });
    }

    #[test]
    fn parse_batch_write_policy_with_commit_level_master() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("commit_level", 1i32).unwrap();
            });
            let p = parse_batch_write_policy(Some(&d)).expect("parse ok");
            assert_eq!(p.commit_level, CommitLevel::CommitMaster);
        });
    }

    #[test]
    fn parse_batch_write_policy_with_durable_delete() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("durable_delete", true).unwrap();
            });
            let p = parse_batch_write_policy(Some(&d)).expect("parse ok");
            assert!(p.durable_delete);
        });
    }

    #[test]
    fn parse_batch_write_policy_default_when_dict_is_none() {
        let p = parse_batch_write_policy(None).expect("parse ok");
        assert!(!p.send_key);
        assert!(!p.durable_delete);
        assert_eq!(p.record_exists_action, RecordExistsAction::Update);
        assert_eq!(p.commit_level, CommitLevel::CommitAll);
        assert!(matches!(p.expiration, Expiration::NamespaceDefault));
    }

    #[test]
    fn apply_record_meta_overrides_send_key() {
        Python::initialize();
        Python::attach(|py| {
            let base = BatchWritePolicy::default(); // send_key = false
            let meta = build_dict(py, |d| {
                d.set_item("key", 1i32).unwrap();
            });
            let overridden = apply_record_meta(&base, &meta).expect("apply ok");
            assert!(overridden.send_key);
        });
    }

    #[test]
    fn apply_record_meta_overrides_exists() {
        Python::initialize();
        Python::attach(|py| {
            let base = BatchWritePolicy::default();
            let meta = build_dict(py, |d| {
                d.set_item("exists", 4i32).unwrap();
            });
            let overridden = apply_record_meta(&base, &meta).expect("apply ok");
            assert_eq!(
                overridden.record_exists_action,
                RecordExistsAction::CreateOnly
            );
        });
    }

    #[test]
    fn apply_record_meta_preserves_unrelated_fields() {
        Python::initialize();
        Python::attach(|py| {
            let mut base = BatchWritePolicy::default();
            base.send_key = true;
            base.commit_level = CommitLevel::CommitMaster;

            // Meta only sets ttl — other fields must come from base.
            let meta = build_dict(py, |d| {
                d.set_item("ttl", 3600i64).unwrap();
            });
            let overridden = apply_record_meta(&base, &meta).expect("apply ok");
            assert!(overridden.send_key, "send_key must be inherited from base");
            assert_eq!(overridden.commit_level, CommitLevel::CommitMaster);
            assert!(matches!(overridden.expiration, Expiration::Seconds(3600)));
        });
    }

    #[test]
    fn parse_batch_policy_with_replica_master() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("replica", 0i32).unwrap();
            });
            let p = parse_batch_policy(Some(&d)).unwrap();
            assert_eq!(p.replica, aerospike_core::policy::Replica::Master);
        });
    }

    #[test]
    fn parse_batch_policy_with_read_mode_and_ttl() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_mode_ap", 1i32).unwrap();
                d.set_item("read_touch_ttl_percent", 80i64).unwrap();
            });
            let p = parse_batch_policy(Some(&d)).unwrap();
            assert_eq!(
                p.base_policy.consistency_level,
                aerospike_core::ConsistencyLevel::ConsistencyAll
            );
            assert!(matches!(
                p.base_policy.read_touch_ttl,
                aerospike_core::ReadTouchTTL::Percent(80)
            ));
        });
    }

    #[test]
    fn apply_record_meta_per_record_wins_over_base() {
        Python::initialize();
        Python::attach(|py| {
            let mut base = BatchWritePolicy::default();
            base.send_key = false; // batch policy = DIGEST

            // Per-record meta = SEND must override.
            let meta = build_dict(py, |d| {
                d.set_item("key", 1i32).unwrap();
            });
            let overridden = apply_record_meta(&base, &meta).expect("apply ok");
            assert!(overridden.send_key, "per-record key must override base");
        });
    }
}
