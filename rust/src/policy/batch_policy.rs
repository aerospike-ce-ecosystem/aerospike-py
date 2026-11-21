//! Batch policy parsing from Python dicts.

use aerospike_core::{
    BatchDeletePolicy, BatchPolicy, BatchReadPolicy, BatchUdfPolicy, BatchWritePolicy, Concurrency,
    GenerationPolicy,
};
use log::trace;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::write_policy::parse_ttl;
use super::{
    extract_filter_expression, extract_policy_fields, parse_commit_level, parse_generation_policy,
    parse_read_mode_ap, parse_read_touch_ttl, parse_record_exists_action, parse_replica,
};

/// Which defaults a batch call starts from.
///
/// The parent `BatchPolicy` is one type for every batch call, but the right
/// number of automatic retries is not: a read can be sent again freely, while
/// a write, delete or UDF call that is re-sent after the server already
/// applied it is applied twice (issue #453).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BatchKind {
    /// Every row only reads. Starts from `BatchPolicy::default()`, which
    /// retries (`max_retries` 2).
    Read,
    /// At least one row writes, deletes or runs a UDF. Starts from
    /// `BatchPolicy::write_default()`, which does not retry (`max_retries` 0).
    Write,
}

/// Parse a Python policy dict into a BatchPolicy.
///
/// `kind` only picks the starting defaults; a `max_retries` in the dict wins
/// for either kind.
pub fn parse_batch_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
    kind: BatchKind,
) -> PyResult<BatchPolicy> {
    trace!("Parsing batch policy");
    let mut policy = match kind {
        BatchKind::Read => BatchPolicy::default(),
        BatchKind::Write => BatchPolicy::write_default(),
    };

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "socket_timeout" => policy.base_policy.socket_timeout;
        "total_timeout" => policy.base_policy.total_timeout;
        "max_retries" => policy.base_policy.max_retries;
        "sleep_between_retries" => policy.base_policy.sleep_between_retries;
        "timeout_delay" => policy.base_policy.timeout_delay;
        "allow_inline" => policy.allow_inline;
        "allow_inline_ssd" => policy.allow_inline_ssd;
        "respond_all_keys" => policy.respond_all_keys
    });

    if let Some(val) = dict.get_item("replica")? {
        policy.base_policy.replica = parse_replica(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.read_mode_ap = parse_read_mode_ap(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.base_policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }

    if let Some(val) = dict.get_item("concurrency")? {
        policy.concurrency = parse_concurrency(val.extract::<i64>()?)?;
    }

    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Reject `retry=N` together with a `max_retries` in the batch policy.
///
/// The two would multiply: every one of the `retry + 1` client-side attempts
/// would itself be re-sent `max_retries` times inside aerospike-core, and the
/// inner re-sends ignore which rows already succeeded. `retry=` re-sends only
/// the rows that failed, so it is the one to use for `batch_write`.
///
/// A write batch starts from `max_retries` 0, so a non-zero value here is one
/// the caller asked for.
pub fn reject_doubled_retry(retry: u32, policy: &BatchPolicy) -> PyResult<()> {
    if retry > 0 && policy.base_policy.max_retries > 0 {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "retry={retry} and policy['max_retries']={} were both given; they would multiply \
             into up to {} sends per record. Use retry= alone: it re-sends only the records \
             that failed.",
            policy.base_policy.max_retries,
            (u64::from(retry) + 1).saturating_mul(policy.base_policy.max_retries as u64 + 1),
        )));
    }
    Ok(())
}

/// Map a Python ``int`` to an [`aerospike_core::Concurrency`] variant.
///
/// Mapping: ``0 -> Sequential``, ``1 -> Parallel``. Any other value
/// (including negatives and ``n >= 2``) is rejected with [`PyValueError`].
/// Note that aerospike-core 2.0's ``Concurrency`` enum only supports the
/// two variants — there is no ``MaxThreads(n)`` variant in this version.
fn parse_concurrency(value: i64) -> PyResult<Concurrency> {
    match value {
        0 => Ok(Concurrency::Sequential),
        1 => Ok(Concurrency::Parallel),
        _ => Err(PyValueError::new_err(format!(
            "Invalid concurrency value: {value}. Use BATCH_CONCURRENCY_SEQUENTIAL (0) or BATCH_CONCURRENCY_PARALLEL (1)"
        ))),
    }
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
        policy.record_exists_action = parse_record_exists_action(val.extract::<i32>()?)?;
    }

    // Generation policy — POLICY_GEN_*
    if let Some(val) = dict.get_item("gen")? {
        policy.generation_policy = parse_generation_policy(val.extract::<i32>()?)?;
    }

    // Commit level — POLICY_COMMIT_LEVEL_*
    if let Some(val) = dict.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(val.extract::<i32>()?)?;
    }

    // TTL / expiration
    if let Some(val) = dict.get_item("ttl")? {
        policy.expiration = parse_ttl(val.extract::<i64>()?)?;
    }

    // Filter expression
    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Parse the per-record-policy dict into a [`BatchReadPolicy`].
///
/// Mirrors [`parse_batch_write_policy`] but covers only the read-side
/// fields exposed by `aerospike-core`'s `BatchReadPolicy`:
/// `read_touch_ttl_percent` (user-facing key) and `filter_expression`.
pub fn parse_batch_read_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
) -> PyResult<BatchReadPolicy> {
    trace!("Parsing batch read policy");
    let mut policy = BatchReadPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }

    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Parse the per-record-policy dict into a [`BatchDeletePolicy`].
///
/// Covers `gen` (generation_policy), `commit_level`, `key` (send_key),
/// `durable_delete`, and `filter_expression`. Mirrors the write-side
/// parser but omits TTL and `exists` (deletes don't write expiration
/// or care about record-exists semantics).
pub fn parse_batch_delete_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
) -> PyResult<BatchDeletePolicy> {
    trace!("Parsing batch delete policy");
    let mut policy = BatchDeletePolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "durable_delete" => policy.durable_delete
    });

    if let Some(val) = dict.get_item("key")? {
        policy.send_key = val.extract::<i32>()? == 1;
    }
    if let Some(val) = dict.get_item("gen")? {
        policy.generation_policy = parse_generation_policy(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(val.extract::<i32>()?)?;
    }

    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Apply per-record meta to a [`BatchDeletePolicy`], overriding the batch-level
/// default. Per-record settings always win.
///
/// Supported meta keys: `gen` (sets `generation` + `GenerationPolicy::
/// ExpectGenEqual`, mirroring `apply_record_meta` for writes), `key`
/// (send_key), `commit_level`, `durable_delete`. Unknown keys are
/// silently ignored, matching the batch_write meta convention.
pub fn apply_record_meta_for_delete(
    base: &BatchDeletePolicy,
    meta: &Bound<'_, PyDict>,
) -> PyResult<BatchDeletePolicy> {
    let mut policy = base.clone();

    if let Some(gen) = meta.get_item("gen")? {
        policy.generation = gen.extract::<u32>()?;
        policy.generation_policy = GenerationPolicy::ExpectGenEqual;
    }
    if let Some(key) = meta.get_item("key")? {
        policy.send_key = key.extract::<i32>()? == 1;
    }
    if let Some(commit_level) = meta.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(commit_level.extract::<i32>()?)?;
    }
    if let Some(durable_delete) = meta.get_item("durable_delete")? {
        policy.durable_delete = durable_delete.extract::<bool>()?;
    }

    Ok(policy)
}

/// Parse the per-record-policy dict into a [`BatchUdfPolicy`].
///
/// Covers `commit_level`, `expiration` (via the user-facing `ttl` key,
/// matching the `WritePolicy` parser convention), `key` (send_key),
/// `durable_delete`, and `filter_expression`. UDFs may write — keeping
/// the same field surface as `BatchWritePolicy` minus `gen`/`exists`
/// keeps the parsers consistent for downstream `apply_record_meta_for_apply`.
pub fn parse_batch_udf_policy(policy_dict: Option<&Bound<'_, PyDict>>) -> PyResult<BatchUdfPolicy> {
    trace!("Parsing batch UDF policy");
    let mut policy = BatchUdfPolicy::default();

    let dict = match policy_dict {
        Some(d) => d,
        None => return Ok(policy),
    };

    extract_policy_fields!(dict, {
        "durable_delete" => policy.durable_delete
    });

    if let Some(val) = dict.get_item("key")? {
        policy.send_key = val.extract::<i32>()? == 1;
    }
    if let Some(val) = dict.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(val.extract::<i32>()?)?;
    }
    if let Some(val) = dict.get_item("ttl")? {
        policy.expiration = parse_ttl(val.extract::<i64>()?)?;
    }

    policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

/// Apply per-record meta to a [`BatchUdfPolicy`], overriding the batch-level
/// default. Per-record settings always win.
///
/// Supported meta keys (single flat `BatchUDFMeta` dict, mirroring
/// `BatchDeleteMeta`): `ttl`, `key` (send_key), `commit_level`,
/// `durable_delete`. Note that `module`, `function`, and `args` are
/// extracted separately by `prepare_batch_apply_args` — they affect
/// the UDF call shape, not the policy.
pub fn apply_record_meta_for_apply(
    base: &BatchUdfPolicy,
    meta: &Bound<'_, PyDict>,
) -> PyResult<BatchUdfPolicy> {
    let mut policy = base.clone();

    if let Some(ttl) = meta.get_item("ttl")? {
        policy.expiration = parse_ttl(ttl.extract::<i64>()?)?;
    }
    if let Some(key) = meta.get_item("key")? {
        policy.send_key = key.extract::<i32>()? == 1;
    }
    if let Some(commit_level) = meta.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(commit_level.extract::<i32>()?)?;
    }
    if let Some(durable_delete) = meta.get_item("durable_delete")? {
        policy.durable_delete = durable_delete.extract::<bool>()?;
    }

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
        policy.record_exists_action = parse_record_exists_action(exists.extract::<i32>()?)?;
    }
    if let Some(commit_level) = meta.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(commit_level.extract::<i32>()?)?;
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
            let base = BatchWritePolicy {
                send_key: true,
                commit_level: CommitLevel::CommitMaster,
                ..BatchWritePolicy::default()
            };

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
            let p = parse_batch_policy(Some(&d), BatchKind::Read).unwrap();
            assert_eq!(
                p.base_policy.replica,
                aerospike_core::policy::Replica::Master
            );
        });
    }

    #[test]
    fn parse_batch_policy_with_timeout_delay() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("timeout_delay", 500u32).unwrap();
            });
            let p = parse_batch_policy(Some(&d), BatchKind::Read).unwrap();
            assert_eq!(p.base_policy.timeout_delay, 500);
        });
    }

    #[test]
    fn parse_batch_policy_with_sleep_between_retries() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("sleep_between_retries", 250u32).unwrap();
            });
            let p = parse_batch_policy(Some(&d), BatchKind::Read).unwrap();
            assert_eq!(p.base_policy.sleep_between_retries, 250);
        });
    }

    #[test]
    fn parse_batch_policy_default_concurrency_is_parallel() {
        let p = parse_batch_policy(None, BatchKind::Read).expect("parse ok");
        assert!(matches!(p.concurrency, Concurrency::Parallel));
    }

    #[test]
    fn parse_batch_policy_concurrency_sequential() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("concurrency", 0i64).unwrap();
            });
            let p = parse_batch_policy(Some(&d), BatchKind::Read).expect("parse ok");
            assert!(matches!(p.concurrency, Concurrency::Sequential));
        });
    }

    #[test]
    fn parse_batch_policy_concurrency_parallel() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("concurrency", 1i64).unwrap();
            });
            let p = parse_batch_policy(Some(&d), BatchKind::Read).expect("parse ok");
            assert!(matches!(p.concurrency, Concurrency::Parallel));
        });
    }

    #[test]
    fn parse_batch_policy_concurrency_rejects_negative() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("concurrency", -1i64).unwrap();
            });
            assert!(parse_batch_policy(Some(&d), BatchKind::Read).is_err());
        });
    }

    #[test]
    fn parse_batch_policy_concurrency_rejects_unsupported_max_threads() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("concurrency", 4i64).unwrap();
            });
            assert!(parse_batch_policy(Some(&d), BatchKind::Read).is_err());
        });
    }

    // ── BatchKind: who retries by default (issue #453) ──────────

    #[test]
    fn a_read_batch_retries_by_default_and_a_write_batch_does_not() {
        let read = parse_batch_policy(None, BatchKind::Read).unwrap();
        let write = parse_batch_policy(None, BatchKind::Write).unwrap();
        assert_eq!(read.base_policy.max_retries, 2);
        assert_eq!(
            write.base_policy.max_retries, 0,
            "a re-sent increment or UDF call is applied twice"
        );
    }

    #[test]
    fn the_kind_changes_nothing_but_the_retry_default() {
        let read = parse_batch_policy(None, BatchKind::Read).unwrap();
        let write = parse_batch_policy(None, BatchKind::Write).unwrap();
        assert_eq!(
            read.base_policy.total_timeout,
            write.base_policy.total_timeout
        );
        assert_eq!(
            read.base_policy.socket_timeout,
            write.base_policy.socket_timeout
        );
        assert_eq!(
            read.base_policy.sleep_between_retries,
            write.base_policy.sleep_between_retries
        );
    }

    #[test]
    fn an_explicit_max_retries_wins_for_either_kind() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| d.set_item("max_retries", 5u32).unwrap());
            for kind in [BatchKind::Read, BatchKind::Write] {
                let p = parse_batch_policy(Some(&d), kind).unwrap();
                assert_eq!(p.base_policy.max_retries, 5, "{kind:?}");
            }
        });
    }

    #[test]
    fn a_policy_without_max_retries_keeps_the_kind_default() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| d.set_item("total_timeout", 3000u32).unwrap());
            let write = parse_batch_policy(Some(&d), BatchKind::Write).unwrap();
            assert_eq!(write.base_policy.max_retries, 0);
            assert_eq!(write.base_policy.total_timeout, 3000);
        });
    }

    #[test]
    fn retry_together_with_max_retries_is_rejected() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| d.set_item("max_retries", 2u32).unwrap());
            let policy = parse_batch_policy(Some(&d), BatchKind::Write).unwrap();

            let err = reject_doubled_retry(3, &policy).expect_err("both were given");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            let message = err.to_string();
            assert!(
                message.contains("retry=3")
                    && message.contains("max_retries")
                    && message.contains("12"),
                "the message names both settings and the product, got: {message}"
            );
        });
    }

    #[test]
    fn either_retry_setting_alone_is_accepted() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| d.set_item("max_retries", 2u32).unwrap());
            let with_max_retries = parse_batch_policy(Some(&d), BatchKind::Write).unwrap();
            assert!(reject_doubled_retry(0, &with_max_retries).is_ok());

            let default_policy = parse_batch_policy(None, BatchKind::Write).unwrap();
            assert!(reject_doubled_retry(3, &default_policy).is_ok());
            assert!(reject_doubled_retry(0, &default_policy).is_ok());
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
            let p = parse_batch_policy(Some(&d), BatchKind::Read).unwrap();
            assert_eq!(p.base_policy.read_mode_ap, aerospike_core::ReadModeAp::All);
            assert!(matches!(
                p.base_policy.read_touch_ttl,
                aerospike_core::ReadTouchTtl::Percent(80)
            ));
        });
    }

    #[test]
    fn apply_record_meta_per_record_wins_over_base() {
        Python::initialize();
        Python::attach(|py| {
            let base = BatchWritePolicy {
                send_key: false, // batch policy = DIGEST
                ..BatchWritePolicy::default()
            };

            // Per-record meta = SEND must override.
            let meta = build_dict(py, |d| {
                d.set_item("key", 1i32).unwrap();
            });
            let overridden = apply_record_meta(&base, &meta).expect("apply ok");
            assert!(overridden.send_key, "per-record key must override base");
        });
    }

    // ── BatchReadPolicy ──────────────────────────────────────────────────

    #[test]
    fn parse_batch_read_policy_default_when_dict_is_none() {
        let p = parse_batch_read_policy(None).expect("parse ok");
        assert!(matches!(
            p.read_touch_ttl,
            aerospike_core::ReadTouchTtl::ServerDefault
        ));
        assert!(p.filter_expression.is_none());
    }

    #[test]
    fn parse_batch_read_policy_with_read_touch_ttl_percent_80() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_touch_ttl_percent", 80i32).unwrap();
            });
            let p = parse_batch_read_policy(Some(&d)).expect("parse ok");
            assert!(matches!(
                p.read_touch_ttl,
                aerospike_core::ReadTouchTtl::Percent(80)
            ));
        });
    }

    #[test]
    fn parse_batch_read_policy_rejects_out_of_range() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("read_touch_ttl_percent", 150i32).unwrap();
            });
            assert!(parse_batch_read_policy(Some(&d)).is_err());
        });
    }

    // ── BatchDeletePolicy ────────────────────────────────────────────────

    #[test]
    fn parse_batch_delete_policy_default_when_dict_is_none() {
        let p = parse_batch_delete_policy(None).expect("parse ok");
        assert!(!p.send_key);
        assert!(!p.durable_delete);
        assert_eq!(p.generation_policy, GenerationPolicy::None);
        assert_eq!(p.commit_level, aerospike_core::CommitLevel::CommitAll);
        assert_eq!(p.generation, 0);
    }

    #[test]
    fn parse_batch_delete_policy_with_durable_delete_and_send_key() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("durable_delete", true).unwrap();
                d.set_item("key", 1i32).unwrap();
            });
            let p = parse_batch_delete_policy(Some(&d)).expect("parse ok");
            assert!(p.durable_delete);
            assert!(p.send_key);
        });
    }

    #[test]
    fn apply_record_meta_for_delete_sets_gen_and_policy() {
        Python::initialize();
        Python::attach(|py| {
            let base = aerospike_core::BatchDeletePolicy::default();
            let meta = build_dict(py, |d| {
                d.set_item("gen", 42u32).unwrap();
            });
            let overridden = apply_record_meta_for_delete(&base, &meta).expect("apply ok");
            assert_eq!(overridden.generation, 42);
            assert_eq!(
                overridden.generation_policy,
                GenerationPolicy::ExpectGenEqual
            );
        });
    }

    #[test]
    fn apply_record_meta_for_delete_per_record_wins_over_base() {
        Python::initialize();
        Python::attach(|py| {
            let base = aerospike_core::BatchDeletePolicy {
                send_key: false,
                ..Default::default()
            };
            let meta = build_dict(py, |d| {
                d.set_item("key", 1i32).unwrap();
                d.set_item("durable_delete", true).unwrap();
            });
            let overridden = apply_record_meta_for_delete(&base, &meta).expect("apply ok");
            assert!(overridden.send_key);
            assert!(overridden.durable_delete);
        });
    }

    // ── BatchUdfPolicy ───────────────────────────────────────────────────

    #[test]
    fn parse_batch_udf_policy_default_when_dict_is_none() {
        let p = parse_batch_udf_policy(None).expect("parse ok");
        assert!(!p.send_key);
        assert!(!p.durable_delete);
        assert_eq!(p.commit_level, CommitLevel::CommitAll);
        assert!(matches!(p.expiration, Expiration::NamespaceDefault));
        assert!(p.filter_expression.is_none());
    }

    #[test]
    fn parse_batch_udf_policy_with_ttl_and_send_key() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("ttl", 60i64).unwrap();
                d.set_item("key", 1i32).unwrap();
            });
            let p = parse_batch_udf_policy(Some(&d)).expect("parse ok");
            assert!(p.send_key);
            assert!(matches!(p.expiration, Expiration::Seconds(60)));
        });
    }

    #[test]
    fn parse_batch_udf_policy_with_commit_level_and_durable_delete() {
        Python::initialize();
        Python::attach(|py| {
            let d = build_dict(py, |d| {
                d.set_item("commit_level", 1i32).unwrap();
                d.set_item("durable_delete", true).unwrap();
            });
            let p = parse_batch_udf_policy(Some(&d)).expect("parse ok");
            assert_eq!(p.commit_level, CommitLevel::CommitMaster);
            assert!(p.durable_delete);
        });
    }

    #[test]
    fn apply_record_meta_for_apply_overrides_ttl_and_send_key() {
        Python::initialize();
        Python::attach(|py| {
            let base = BatchUdfPolicy::default();
            let meta = build_dict(py, |d| {
                d.set_item("ttl", 3600i64).unwrap();
                d.set_item("key", 1i32).unwrap();
            });
            let overridden = apply_record_meta_for_apply(&base, &meta).expect("apply ok");
            assert!(overridden.send_key);
            assert!(matches!(overridden.expiration, Expiration::Seconds(3600)));
        });
    }

    #[test]
    fn apply_record_meta_for_apply_per_record_wins_over_base() {
        Python::initialize();
        Python::attach(|py| {
            let base = BatchUdfPolicy {
                send_key: false,
                commit_level: CommitLevel::CommitAll,
                ..Default::default()
            };
            let meta = build_dict(py, |d| {
                d.set_item("commit_level", 1i32).unwrap();
                d.set_item("durable_delete", true).unwrap();
            });
            let overridden = apply_record_meta_for_apply(&base, &meta).expect("apply ok");
            assert_eq!(overridden.commit_level, CommitLevel::CommitMaster);
            assert!(overridden.durable_delete);
            assert!(!overridden.send_key, "send_key inherited from base");
        });
    }
}
