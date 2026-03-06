//! Write policy parsing from Python dicts, including TTL and generation handling.

use std::sync::LazyLock;

use aerospike_core::{CommitLevel, Expiration, GenerationPolicy, RecordExistsAction, WritePolicy};
use log::trace;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::{extract_filter_expression, extract_policy_fields};

/// Lazily-initialized default write policy used when no policy dict is provided.
pub static DEFAULT_WRITE_POLICY: LazyLock<WritePolicy> = LazyLock::new(WritePolicy::default);

/// Convert a TTL integer value to an [`Expiration`] enum.
///
/// Special values: `0` = namespace default, `-1` = never expire, `-2` = don't update.
fn parse_ttl(ttl_val: i64) -> PyResult<Expiration> {
    match ttl_val {
        0 => Ok(Expiration::NamespaceDefault),
        -1 => Ok(Expiration::Never),
        -2 => Ok(Expiration::DontUpdate),
        t if t > 0 && t <= u32::MAX as i64 => Ok(Expiration::Seconds(t as u32)),
        t if t > u32::MAX as i64 => Err(crate::errors::InvalidArgError::new_err(format!(
            "ttl out of range: {t} (max: {})",
            u32::MAX
        ))),
        _ => Ok(Expiration::NamespaceDefault),
    }
}

/// Parse a Python policy dict into a WritePolicy
pub fn parse_write_policy(
    policy_dict: Option<&Bound<'_, PyDict>>,
    meta: Option<&Bound<'_, PyDict>>,
) -> PyResult<WritePolicy> {
    trace!("Parsing write policy");
    let mut policy = WritePolicy::default();

    // Apply meta (gen, ttl) first
    if let Some(meta_dict) = meta {
        if let Some(gen) = meta_dict.get_item("gen")? {
            policy.generation = gen.extract::<u32>()?;
            policy.generation_policy = GenerationPolicy::ExpectGenEqual;
        }
        if let Some(ttl) = meta_dict.get_item("ttl")? {
            policy.expiration = parse_ttl(ttl.extract::<i64>()?)?;
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
        "durable_delete" => policy.durable_delete
    });

    // Key (send_key)
    if let Some(val) = dict.get_item("key")? {
        let key_val: i32 = val.extract()?;
        policy.send_key = key_val == 1;
    }

    // Exists (record_exists_action)
    if let Some(val) = dict.get_item("exists")? {
        let exists_val: i32 = val.extract()?;
        policy.record_exists_action = match exists_val {
            0 => RecordExistsAction::Update,
            1 => RecordExistsAction::UpdateOnly,
            2 => RecordExistsAction::Replace,
            3 => RecordExistsAction::ReplaceOnly,
            4 => RecordExistsAction::CreateOnly,
            _ => RecordExistsAction::Update,
        };
    }

    // Gen policy
    if let Some(val) = dict.get_item("gen")? {
        let gen_val: i32 = val.extract()?;
        policy.generation_policy = match gen_val {
            0 => GenerationPolicy::None,
            1 => GenerationPolicy::ExpectGenEqual,
            2 => GenerationPolicy::ExpectGenGreater,
            _ => GenerationPolicy::None,
        };
    }

    // Commit level
    if let Some(val) = dict.get_item("commit_level")? {
        let commit_val: i32 = val.extract()?;
        policy.commit_level = match commit_val {
            0 => CommitLevel::CommitAll,
            1 => CommitLevel::CommitMaster,
            _ => CommitLevel::CommitAll,
        };
    }

    // TTL / expiration
    if let Some(val) = dict.get_item("ttl")? {
        policy.expiration = parse_ttl(val.extract::<i64>()?)?;
    }

    // Filter expression
    policy.base_policy.filter_expression = extract_filter_expression(dict)?;

    Ok(policy)
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
