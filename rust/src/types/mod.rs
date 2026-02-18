//! Type conversion between Python objects and `aerospike_core` types.
//!
//! - [`value`]: Python ↔ `aerospike_core::Value`
//! - [`key`]: Python tuple ↔ `aerospike_core::Key`
//! - [`bin`]: Python dict ↔ `Vec<aerospike_core::Bin>`
//! - [`record`]: `aerospike_core::Record` → Python tuple `(key, meta, bins)`
//! - [`host`]: Python config dict → connection string

pub mod bin;
pub mod host;
pub mod key;
pub mod record;
pub mod value;
