//! Query and scan support for the Aerospike Python client.
//!
//! Provides [`PyQuery`], a Python-visible class that collects predicates and
//! selected bins, then executes them against the cluster as either a secondary
//! index query or a full scan (when no predicates are set).

use std::sync::Arc;

#[allow(unused_imports)]
use aerospike_core::as_val;
use aerospike_core::{
    Bins, Client as AsClient, CollectionIndexType, Error as AsError, PartitionFilter, Statement,
    Value,
};
use futures::StreamExt;
use log::{debug, trace};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::errors::as_to_pyerr;
use crate::policy::query_policy::parse_query_policy;
use crate::runtime::RUNTIME;
use crate::types::record::record_to_py;
use crate::types::value::py_to_value;

/// Stored predicate info, reconstructed into an `aerospike_core::Filter` at execution time.
///
/// Predicates are collected from Python `where()` calls and applied to the
/// [`Statement`] just before query execution.
#[derive(Clone)]
enum Predicate {
    Equals {
        bin: String,
        val: Value,
    },
    Between {
        bin: String,
        min: i64,
        max: i64,
    },
    ContainsString {
        bin: String,
        val: String,
        col_type: i32,
    },
    ContainsInteger {
        bin: String,
        val: i64,
        col_type: i32,
    },
    #[allow(dead_code)]
    GeoWithinRegion {
        bin: String,
        geojson: String,
    },
    #[allow(dead_code)]
    GeoWithinRadius {
        bin: String,
        lat: f64,
        lng: f64,
        radius: f64,
    },
    #[allow(dead_code)]
    GeoContainsPoint {
        bin: String,
        geojson: String,
    },
}

/// Parse a Python predicate tuple (from `aerospike_py.predicates`) into a [`Predicate`].
fn parse_predicate(pred: &Bound<'_, PyTuple>) -> PyResult<Predicate> {
    if pred.len() < 2 {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "Predicate tuple must have at least 2 elements (kind, bin, ...), got {}",
            pred.len()
        )));
    }
    let kind: String = pred.get_item(0)?.extract()?;
    let bin: String = pred.get_item(1)?.extract()?;
    trace!("Parsing predicate: kind={} bin={}", kind, bin);

    match kind.as_str() {
        "equals" => {
            ensure_predicate_min_len(pred, "equals", 3)?;
            let val = py_to_value(&pred.get_item(2)?)?;
            Ok(Predicate::Equals { bin, val })
        }
        "between" => {
            ensure_predicate_min_len(pred, "between", 4)?;
            let min: i64 = pred.get_item(2)?.extract()?;
            let max: i64 = pred.get_item(3)?.extract()?;
            Ok(Predicate::Between { bin, min, max })
        }
        "contains" => {
            ensure_predicate_min_len(pred, "contains", 4)?;
            let col_type: i32 = pred.get_item(2)?.extract()?;
            let val_any = pred.get_item(3)?;
            if let Ok(v) = val_any.extract::<i64>() {
                Ok(Predicate::ContainsInteger {
                    bin,
                    val: v,
                    col_type,
                })
            } else {
                let v: String = val_any.extract()?;
                Ok(Predicate::ContainsString {
                    bin,
                    val: v,
                    col_type,
                })
            }
        }
        "geo_within_geojson_region" => {
            ensure_predicate_min_len(pred, "geo_within_geojson_region", 3)?;
            let geojson: String = pred.get_item(2)?.extract()?;
            Ok(Predicate::GeoWithinRegion { bin, geojson })
        }
        "geo_within_radius" => {
            ensure_predicate_min_len(pred, "geo_within_radius", 5)?;
            let lat: f64 = pred.get_item(2)?.extract()?;
            let lng: f64 = pred.get_item(3)?.extract()?;
            let radius: f64 = pred.get_item(4)?.extract()?;
            Ok(Predicate::GeoWithinRadius {
                bin,
                lat,
                lng,
                radius,
            })
        }
        "geo_contains_geojson_point" => {
            ensure_predicate_min_len(pred, "geo_contains_geojson_point", 3)?;
            let geojson: String = pred.get_item(2)?.extract()?;
            Ok(Predicate::GeoContainsPoint { bin, geojson })
        }
        _ => Err(crate::errors::InvalidArgError::new_err(format!(
            "Unknown predicate type: {kind}"
        ))),
    }
}

fn ensure_predicate_min_len(pred: &Bound<'_, PyTuple>, kind: &str, min_len: usize) -> PyResult<()> {
    if pred.len() < min_len {
        return Err(crate::errors::InvalidArgError::new_err(format!(
            "Predicate '{kind}' requires at least {min_len} elements, got {}",
            pred.len()
        )));
    }
    Ok(())
}

/// Build an `aerospike_core::Statement` from namespace, set, bins, and predicates.
fn build_statement(
    namespace: &str,
    set_name: &str,
    bins: &[String],
    predicates: &[Predicate],
) -> PyResult<Statement> {
    let bins_selector = if bins.is_empty() {
        Bins::All
    } else {
        let refs: Vec<&str> = bins.iter().map(|s| s.as_str()).collect();
        Bins::from(refs.as_slice())
    };

    let mut stmt = Statement::new(namespace, set_name, bins_selector);

    for pred in predicates {
        let filter = match pred {
            Predicate::Equals { bin, val } => {
                aerospike_core::as_eq!(bin.as_str(), val.clone())
            }
            Predicate::Between { bin, min, max } => {
                aerospike_core::as_range!(bin.as_str(), *min, *max)
            }
            Predicate::ContainsString { bin, val, col_type } => {
                let ct = int_to_collection_index_type(*col_type);
                aerospike_core::as_contains!(bin.as_str(), val.as_str(), ct)
            }
            Predicate::ContainsInteger { bin, val, col_type } => {
                let ct = int_to_collection_index_type(*col_type);
                aerospike_core::as_contains!(bin.as_str(), *val, ct)
            }
            Predicate::GeoWithinRegion { .. }
            | Predicate::GeoWithinRadius { .. }
            | Predicate::GeoContainsPoint { .. } => {
                return Err(crate::errors::ClientError::new_err(
                    "Geo filters are not yet supported in this version",
                ));
            }
        };
        stmt.add_filter(filter);
    }

    Ok(stmt)
}

/// Map a Python integer to a [`CollectionIndexType`] for contains-predicates.
fn int_to_collection_index_type(val: i32) -> CollectionIndexType {
    match val {
        1 => CollectionIndexType::List,
        2 => CollectionIndexType::MapKeys,
        3 => CollectionIndexType::MapValues,
        _ => CollectionIndexType::Default,
    }
}

/// Execute a query/scan, collect all records, with metrics and OTel span.
#[allow(unused, clippy::too_many_arguments)]
fn execute_query_collect(
    py: Python<'_>,
    client: &Arc<AsClient>,
    statement: Statement,
    policy: Option<&Bound<'_, PyDict>>,
    op_name: &str,
    namespace: &str,
    set_name: &str,
    conn_info: &crate::tracing::ConnectionInfo,
) -> PyResult<Vec<aerospike_core::Record>> {
    let client = client.clone();
    let query_policy = parse_query_policy(policy)?;
    debug!("Executing {}", op_name);

    let timer = crate::metrics::OperationTimer::start(op_name, namespace, set_name);
    let result: Result<Vec<_>, AsError> = py.detach(|| {
        RUNTIME.block_on(async {
            let rs = client
                .query(&query_policy, PartitionFilter::all(), statement)
                .await?;
            let mut stream = rs.into_stream();
            let mut results = Vec::new();
            while let Some(result) = stream.next().await {
                results.push(result?);
            }
            Ok(results)
        })
    });

    match &result {
        Ok(_) => timer.finish(""),
        Err(e) => timer.finish(&crate::metrics::error_type_from_aerospike_error(e)),
    }

    #[cfg(feature = "otel")]
    {
        use opentelemetry::trace::{SpanKind, TraceContextExt, Tracer};
        use opentelemetry::KeyValue;
        let tracer = crate::tracing::otel_impl::get_tracer();
        let span_name = format!("{} {}.{}", op_name.to_uppercase(), namespace, set_name);
        let span = tracer
            .span_builder(span_name)
            .with_kind(SpanKind::Client)
            .with_attributes(vec![
                KeyValue::new("db.system.name", "aerospike"),
                KeyValue::new("db.namespace", namespace.to_string()),
                KeyValue::new("db.collection.name", set_name.to_string()),
                KeyValue::new("db.operation.name", op_name.to_uppercase()),
                KeyValue::new("server.address", conn_info.server_address.clone()),
                KeyValue::new("server.port", conn_info.server_port),
                KeyValue::new("db.aerospike.cluster_name", conn_info.cluster_name.clone()),
            ])
            .start(&tracer);
        let cx = opentelemetry::Context::current().with_span(span);
        let span_ref = opentelemetry::trace::TraceContextExt::span(&cx);
        if let Err(e) = &result {
            crate::tracing::otel_impl::record_error_on_span(&span_ref, e);
        }
        span_ref.end();
    }

    result.map_err(as_to_pyerr)
}

/// Execute a query/scan and collect all results as a Python list.
#[allow(unused, clippy::too_many_arguments)]
fn execute_query(
    py: Python<'_>,
    client: &Arc<AsClient>,
    statement: Statement,
    policy: Option<&Bound<'_, PyDict>>,
    op_name: &str,
    namespace: &str,
    set_name: &str,
    conn_info: &crate::tracing::ConnectionInfo,
) -> PyResult<Py<PyAny>> {
    let records = execute_query_collect(
        py, client, statement, policy, op_name, namespace, set_name, conn_info,
    )?;
    debug!("{} returned {} records", op_name, records.len());
    let py_records: Vec<Py<PyAny>> = records
        .iter()
        .map(|record| record_to_py(py, record, None))
        .collect::<PyResult<_>>()?;
    let py_list = PyList::new(py, &py_records)?;
    Ok(py_list.into_any().unbind())
}

/// Execute a query/scan and call a callback for each record.
#[allow(clippy::too_many_arguments, unused)]
fn execute_foreach(
    py: Python<'_>,
    client: &Arc<AsClient>,
    statement: Statement,
    callback: &Bound<'_, PyAny>,
    policy: Option<&Bound<'_, PyDict>>,
    op_name: &str,
    namespace: &str,
    set_name: &str,
    conn_info: &crate::tracing::ConnectionInfo,
) -> PyResult<()> {
    let records = execute_query_collect(
        py, client, statement, policy, op_name, namespace, set_name, conn_info,
    )?;
    for record in &records {
        let py_record = record_to_py(py, record, None)?;
        let result = callback.call1((py_record,))?;
        // If callback returns False, stop iteration
        if let Ok(false) = result.extract::<bool>() {
            break;
        }
    }
    Ok(())
}

// ── Query class ──────────────────────────────────────────

/// Python-visible query builder exposed as `Query`.
///
/// Created by `Client.query()` / `AsyncClient.query()`. Users add predicates
/// via `where()`, select bins via `select()`, then execute via `results()` or
/// `foreach()`.
#[pyclass(name = "Query")]
pub struct PyQuery {
    client: Arc<AsClient>,
    namespace: String,
    set_name: String,
    bins: Vec<String>,
    predicates: Vec<Predicate>,
    connection_info: Arc<crate::tracing::ConnectionInfo>,
}

impl PyQuery {
    pub fn new(
        client: Arc<AsClient>,
        namespace: String,
        set_name: String,
        connection_info: Arc<crate::tracing::ConnectionInfo>,
    ) -> Self {
        Self {
            client,
            namespace,
            set_name,
            bins: vec![],
            predicates: vec![],
            connection_info,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::parse_predicate;
    use pyo3::prelude::*;
    use pyo3::types::PyTuple;

    #[test]
    fn parse_predicate_rejects_short_equals_tuple() {
        Python::initialize();
        Python::attach(|py| {
            let pred = PyTuple::new(py, ["equals", "age"]).unwrap();
            match parse_predicate(&pred) {
                Ok(_) => panic!("expected short equals predicate to fail"),
                Err(err) => {
                    let msg = err.to_string();
                    assert!(msg.contains("InvalidArgError"));
                    assert!(msg.contains("equals"));
                }
            }
        });
    }

    #[test]
    fn parse_predicate_rejects_short_between_tuple() {
        Python::initialize();
        Python::attach(|py| {
            let pred = PyTuple::new(py, ["between", "age", "10"]).unwrap();
            match parse_predicate(&pred) {
                Ok(_) => panic!("expected short between predicate to fail"),
                Err(err) => {
                    let msg = err.to_string();
                    assert!(msg.contains("InvalidArgError"));
                    assert!(msg.contains("between"));
                }
            }
        });
    }

    #[test]
    fn parse_predicate_rejects_short_contains_tuple() {
        Python::initialize();
        Python::attach(|py| {
            let pred = PyTuple::new(py, ["contains", "tags", "1"]).unwrap();
            match parse_predicate(&pred) {
                Ok(_) => panic!("expected short contains predicate to fail"),
                Err(err) => {
                    let msg = err.to_string();
                    assert!(msg.contains("InvalidArgError"));
                    assert!(msg.contains("contains"));
                }
            }
        });
    }

    #[test]
    fn parse_predicate_rejects_short_geo_within_radius_tuple() {
        Python::initialize();
        Python::attach(|py| {
            let pred = PyTuple::new(py, ["geo_within_radius", "loc", "1.0", "2.0"]).unwrap();
            match parse_predicate(&pred) {
                Ok(_) => panic!("expected short geo_within_radius predicate to fail"),
                Err(err) => {
                    let msg = err.to_string();
                    assert!(msg.contains("InvalidArgError"));
                    assert!(msg.contains("geo_within_radius"));
                }
            }
        });
    }
}

#[pymethods]
impl PyQuery {
    /// Select specific bins to return in query results.
    #[pyo3(signature = (*bins))]
    fn select(&mut self, bins: &Bound<'_, PyTuple>) -> PyResult<()> {
        for bin in bins.iter() {
            self.bins.push(bin.extract::<String>()?);
        }
        Ok(())
    }

    /// Add a filter predicate (secondary index query).
    #[pyo3(name = "where")]
    fn where_(&mut self, predicate: &Bound<'_, PyTuple>) -> PyResult<()> {
        let pred = parse_predicate(predicate)?;
        self.predicates.push(pred);
        Ok(())
    }

    /// Execute the query and return all results as a list of (key, meta, bins).
    #[pyo3(signature = (policy=None))]
    fn results(&self, py: Python<'_>, policy: Option<&Bound<'_, PyDict>>) -> PyResult<Py<PyAny>> {
        let stmt = build_statement(
            &self.namespace,
            &self.set_name,
            &self.bins,
            &self.predicates,
        )?;
        execute_query(
            py,
            &self.client,
            stmt,
            policy,
            "query",
            &self.namespace,
            &self.set_name,
            &self.connection_info,
        )
    }

    /// Execute the query and call callback for each record.
    #[pyo3(signature = (callback, policy=None))]
    fn foreach(
        &self,
        py: Python<'_>,
        callback: &Bound<'_, PyAny>,
        policy: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let stmt = build_statement(
            &self.namespace,
            &self.set_name,
            &self.bins,
            &self.predicates,
        )?;
        execute_foreach(
            py,
            &self.client,
            stmt,
            callback,
            policy,
            "query",
            &self.namespace,
            &self.set_name,
            &self.connection_info,
        )
    }
}
