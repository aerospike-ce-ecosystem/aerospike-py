//! Write policy parsing from Python dicts, including TTL and generation handling.

use std::sync::LazyLock;

use aerospike_core::{Expiration, GenerationPolicy, WritePolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{
    extract_filter_expression, extract_policy_fields, parse_commit_level, parse_consistency_level,
    parse_generation_policy, parse_read_touch_ttl, parse_record_exists_action,
};

/// Build a [`WritePolicy`] carrying aerospike-py's write defaults.
///
/// aerospike-core's `BasePolicy::default()` is `socket_timeout: 30000,
/// total_timeout: 1000, max_retries: 2, sleep_between_retries: 0`
/// (aerospike-core-2.2.0 `src/policy/read_policy.rs:33-45`; the numbers are
/// unchanged from 2.0.0). `max_retries: 2`
/// is a reasonable read default but an unsafe **write** default: `increment()`,
/// `append()`, `prepend()`, and `operate()` with `OP_INCR` are not idempotent,
/// and the inherited budget retries twice with **zero backoff** inside a
/// 1000 ms total timeout — precisely the conditions that produce a client-side
/// timeout on a write the server already committed. A retried counter
/// over-counts; a retried append duplicates. Silently, in both cases.
///
/// Note that this default only became *effective* with aerospike-core 2.2.0.
/// Under 2.0.0 the retry cap was gated on `policy.max_retries() > 0`
/// (`src/commands/single_command.rs:112`), so `0` meant "retry until
/// `total_timeout` expires" rather than "do not retry" — the opposite of the
/// intent here. 2.2.0 computes `effective_attempt = max_retries + 1`, so `0`
/// now means exactly one attempt. Do not read this default as having been
/// honoured on 2.0.0.
///
/// Writes therefore default to **no retries**, matching the official Aerospike
/// clients and this repo's own documentation — `docs/docs/api/types.md` already
/// documents the `WritePolicy` `max_retries` default as `0`, and
/// `docs/docs/guides/config/performance-tuning.md` recommends "2-3 for reads,
/// 0 for writes (idempotency)". Callers whose write *is* idempotent opt back in
/// explicitly with `policy={"max_retries": N}`.
///
/// Read, query, scan, and batch policy defaults are deliberately left alone.
///
/// # Reach
///
/// This is the default for every operation that parses a write policy — all
/// eight `prepare_*_args` helpers in `client_common.rs`: `put`, `remove`,
/// `touch`, `append`/`prepend`, `increment`, `remove_bin`,
/// `operate`/`operate_ordered`, and `apply`.
///
/// Only `increment`, `append`, `prepend`, `operate` with an increment op, and
/// `apply` (an arbitrary UDF) are actually unsafe to retry. `put`, `remove`,
/// `touch`, and `remove_bin` are idempotent in their effect on bin data, so
/// they lose retry resilience without gaining safety.
///
/// That uniformity is deliberate. `docs/docs/api/types.md` names `remove()` and
/// `touch()` as `WritePolicy` consumers on the same table that publishes
/// `max_retries` default `0`, so giving those two a different default would
/// re-create the docs/code divergence this default exists to close — and would
/// mean threading a per-operation flag through all eight call sites, each one a
/// chance to pick wrong. One default is the cheaper invariant to hold.
fn default_write_policy() -> WritePolicy {
    let mut policy = WritePolicy::default();
    policy.base_policy.max_retries = 0;
    policy
}

/// Lazily-initialized default write policy used when no policy dict is provided.
pub static DEFAULT_WRITE_POLICY: LazyLock<WritePolicy> = LazyLock::new(default_write_policy);

/// Convert a TTL integer value to an [`Expiration`] enum.
///
/// Special values: `0` = namespace default, `-1` = never expire, `-2` = don't update,
/// `-3` = client default (degrades to namespace default).
pub(crate) fn parse_ttl(ttl_val: i64) -> PyResult<Expiration> {
    match ttl_val {
        0 => Ok(Expiration::NamespaceDefault),
        -1 => Ok(Expiration::Never),
        -2 => Ok(Expiration::DontUpdate),
        // TTL_CLIENT_DEFAULT (-3) degrades to the namespace default: aerospike-py
        // exposes no client-level default-TTL config and aerospike-core's Expiration
        // enum has no ClientDefault variant, so there is nothing else to fall back to.
        -3 => Ok(Expiration::NamespaceDefault),
        t if t > 0 && t <= u32::MAX as i64 => Ok(Expiration::Seconds(t as u32)),
        t if t > u32::MAX as i64 => Err(crate::errors::InvalidArgError::new_err(format!(
            "ttl out of range: {t} (max: {})",
            u32::MAX
        ))),
        t => Err(crate::errors::InvalidArgError::new_err(format!(
            "ttl out of range: {t} (only 0, -1, -2, -3, or positive seconds are valid)"
        ))),
    }
}

/// Parse a Python policy dict into a WritePolicy
pub fn parse_write_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
    meta: Option<&Bound<'_, PyDict>>,
) -> PyResult<WritePolicy> {
    trace!("Parsing write policy");
    let mut policy = default_write_policy();

    // Apply the per-call `meta` dict first; an explicit `policy` dict below
    // overrides any field the two have in common (unchanged precedence).
    //
    // Every key of the public `WriteMeta` TypedDict is honoured here, with the
    // same semantics as the batch path's `apply_record_meta` — note `gen` is
    // asymmetric: in `meta` it is an expected generation (implying
    // `ExpectGenEqual`), in `policy` it is a `POLICY_GEN_*` enum index.
    if let Some(meta_dict) = meta {
        if let Some(gen) = meta_dict.get_item("gen")? {
            policy.generation = gen.extract::<u32>()?;
            policy.generation_policy = GenerationPolicy::ExpectGenEqual;
        }
        if let Some(ttl) = meta_dict.get_item("ttl")? {
            policy.expiration = parse_ttl(ttl.extract::<i64>()?)?;
        }
        if let Some(key) = meta_dict.get_item("key")? {
            policy.send_key = key.extract::<i32>()? == 1;
        }
        if let Some(exists) = meta_dict.get_item("exists")? {
            policy.record_exists_action = parse_record_exists_action(exists.extract::<i32>()?);
        }
        if let Some(commit_level) = meta_dict.get_item("commit_level")? {
            policy.commit_level = parse_commit_level(commit_level.extract::<i32>()?);
        }
        if let Some(durable_delete) = meta_dict.get_item("durable_delete")? {
            policy.durable_delete = durable_delete.extract::<bool>()?;
        }
    }

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
        "durable_delete" => policy.durable_delete
    });

    // Key (send_key)
    if let Some(val) = dict.get_item("key")? {
        policy.send_key = val.extract::<i32>()? == 1;
    }

    // Exists (record_exists_action)
    if let Some(val) = dict.get_item("exists")? {
        policy.record_exists_action = parse_record_exists_action(val.extract::<i32>()?);
    }

    // Gen policy
    if let Some(val) = dict.get_item("gen")? {
        policy.generation_policy = parse_generation_policy(val.extract::<i32>()?);
    }

    // Commit level
    if let Some(val) = dict.get_item("commit_level")? {
        policy.commit_level = parse_commit_level(val.extract::<i32>()?);
    }

    // TTL / expiration
    if let Some(val) = dict.get_item("ttl")? {
        policy.expiration = parse_ttl(val.extract::<i64>()?)?;
    }

    // Read mode AP (BasePolicy field — operate() with read ops can use this)
    if let Some(val) = dict.get_item("read_mode_ap")? {
        policy.base_policy.consistency_level = parse_consistency_level(val.extract::<i32>()?);
    }
    // Read touch TTL percent (BasePolicy field)
    if let Some(val) = dict.get_item("read_touch_ttl_percent")? {
        policy.base_policy.read_touch_ttl = parse_read_touch_ttl(val.extract::<i64>()?)?;
    }

    // Filter expression
    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aerospike_core::{CommitLevel, RecordExistsAction};

    #[test]
    fn parse_ttl_accepts_valid_positive_seconds() {
        assert!(matches!(
            parse_ttl(300).expect("valid ttl should parse"),
            Expiration::Seconds(300)
        ));
    }

    #[test]
    fn parse_ttl_rejects_values_above_u32_max() {
        Python::initialize();
        Python::attach(|py| {
            let ttl = u32::MAX as i64 + 1;
            let err = parse_ttl(ttl).expect_err("ttl above u32::MAX must fail");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            assert!(err.to_string().contains("ttl out of range"));
        });
    }

    #[test]
    fn parse_write_policy_with_timeout_delay() {
        Python::initialize();
        Python::attach(|py| {
            let d = pyo3::types::PyDict::new(py);
            d.set_item("timeout_delay", 500u32).unwrap();
            let p = parse_write_policy(Some(&d), None).unwrap();
            assert_eq!(p.base_policy.timeout_delay, 500);
        });
    }

    #[test]
    fn parse_write_policy_with_sleep_between_retries() {
        Python::initialize();
        Python::attach(|py| {
            let d = pyo3::types::PyDict::new(py);
            d.set_item("sleep_between_retries", 250u32).unwrap();
            let p = parse_write_policy(Some(&d), None).unwrap();
            assert_eq!(p.base_policy.sleep_between_retries, 250);
        });
    }

    #[test]
    fn parse_ttl_accepts_client_default_sentinel() {
        assert!(matches!(
            parse_ttl(-3).expect("TTL_CLIENT_DEFAULT should parse"),
            Expiration::NamespaceDefault
        ));
    }

    #[test]
    fn write_policy_defaults_to_no_retries() {
        Python::initialize();
        Python::attach(|_py| {
            // Writes are not idempotent; a retried increment / append silently
            // double-applies. This assertion fails against
            // `WritePolicy::default()` (aerospike-core ships `max_retries: 2`).
            let p = parse_write_policy(None, None).expect("empty write policy should parse");
            assert_eq!(p.base_policy.max_retries, 0);
            assert_eq!(DEFAULT_WRITE_POLICY.base_policy.max_retries, 0);
        });
    }

    #[test]
    fn write_policy_keeps_upstream_timeout_defaults() {
        Python::initialize();
        Python::attach(|_py| {
            // Only max_retries is overridden — the rest of BasePolicy::default()
            // is inherited unchanged.
            let p = parse_write_policy(None, None).expect("empty write policy should parse");
            assert_eq!(p.base_policy.socket_timeout, 30000);
            assert_eq!(p.base_policy.total_timeout, 1000);
            assert_eq!(p.base_policy.sleep_between_retries, 0);
        });
    }

    #[test]
    fn write_policy_max_retries_is_still_caller_overridable() {
        Python::initialize();
        Python::attach(|py| {
            let d = pyo3::types::PyDict::new(py);
            d.set_item("max_retries", 3u32).unwrap();
            let p = parse_write_policy(Some(&d), None).unwrap();
            assert_eq!(p.base_policy.max_retries, 3);
        });
    }

    #[test]
    fn write_policy_meta_only_still_defaults_to_no_retries() {
        Python::initialize();
        Python::attach(|py| {
            // meta-only calls return early, before the policy dict is read —
            // that early return must carry the safe default too.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("ttl", 300i64).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert_eq!(p.base_policy.max_retries, 0);
            assert!(matches!(p.expiration, Expiration::Seconds(300)));
        });
    }

    #[test]
    fn parse_ttl_rejects_unknown_negative_values() {
        Python::initialize();
        Python::attach(|py| {
            let err = parse_ttl(-100).expect_err("unknown negative ttl must fail");
            assert!(err.is_instance_of::<crate::errors::InvalidArgError>(py));
            assert!(err.to_string().contains("ttl out of range"));
        });
    }

    #[test]
    fn write_policy_meta_exists_create_only_is_honoured() {
        Python::initialize();
        Python::attach(|py| {
            // POLICY_EXISTS_CREATE_ONLY == 4. Dropping this key silently turns a
            // create-only write into an unconditional upsert.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("exists", 4i32).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert!(matches!(
                p.record_exists_action,
                RecordExistsAction::CreateOnly
            ));
        });
    }

    #[test]
    fn write_policy_meta_key_send_is_honoured() {
        Python::initialize();
        Python::attach(|py| {
            // POLICY_KEY_SEND == 1.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("key", 1i32).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert!(p.send_key, "meta key=1 must enable send_key");

            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("key", 0i32).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert!(
                !p.send_key,
                "meta key=0 (POLICY_KEY_DIGEST) must not send the key"
            );
        });
    }

    #[test]
    fn write_policy_meta_commit_level_is_honoured() {
        Python::initialize();
        Python::attach(|py| {
            // POLICY_COMMIT_LEVEL_MASTER == 1.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("commit_level", 1i32).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert!(matches!(p.commit_level, CommitLevel::CommitMaster));
        });
    }

    #[test]
    fn write_policy_meta_durable_delete_is_honoured() {
        Python::initialize();
        Python::attach(|py| {
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("durable_delete", true).unwrap();
            let p = parse_write_policy(None, Some(&meta)).unwrap();
            assert!(p.durable_delete);
        });
    }

    #[test]
    fn write_policy_dict_still_overrides_meta_for_the_same_field() {
        Python::initialize();
        Python::attach(|py| {
            // Precedence for single-record writes is unchanged: meta is applied
            // first, the explicit policy dict wins on conflict.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("exists", 4i32).unwrap(); // CREATE_ONLY
            meta.set_item("key", 1i32).unwrap(); // KEY_SEND
            meta.set_item("commit_level", 1i32).unwrap(); // MASTER
            meta.set_item("durable_delete", true).unwrap();
            meta.set_item("ttl", 300i64).unwrap();

            let d = pyo3::types::PyDict::new(py);
            d.set_item("exists", 1i32).unwrap(); // POLICY_EXISTS_UPDATE_ONLY
            d.set_item("key", 0i32).unwrap(); // KEY_DIGEST
            d.set_item("commit_level", 0i32).unwrap(); // ALL
            d.set_item("durable_delete", false).unwrap();
            d.set_item("ttl", 600i64).unwrap();

            let p = parse_write_policy(Some(&d), Some(&meta)).unwrap();
            assert!(matches!(
                p.record_exists_action,
                RecordExistsAction::UpdateOnly
            ));
            assert!(!p.send_key);
            assert!(matches!(p.commit_level, CommitLevel::CommitAll));
            assert!(!p.durable_delete);
            assert!(matches!(p.expiration, Expiration::Seconds(600)));
        });
    }

    #[test]
    fn write_policy_meta_fields_survive_an_unrelated_policy_dict() {
        Python::initialize();
        Python::attach(|py| {
            // A policy dict that does not mention the meta fields must not reset
            // them back to the defaults.
            let meta = pyo3::types::PyDict::new(py);
            meta.set_item("exists", 4i32).unwrap();
            meta.set_item("key", 1i32).unwrap();
            meta.set_item("durable_delete", true).unwrap();

            let d = pyo3::types::PyDict::new(py);
            d.set_item("total_timeout", 5000u32).unwrap();

            let p = parse_write_policy(Some(&d), Some(&meta)).unwrap();
            assert!(matches!(
                p.record_exists_action,
                RecordExistsAction::CreateOnly
            ));
            assert!(p.send_key);
            assert!(p.durable_delete);
            assert_eq!(p.base_policy.total_timeout, 5000);
        });
    }
}
