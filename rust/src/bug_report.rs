//! Bug report logging for unexpected internal errors.
//!
//! When aerospike-py encounters an error that is likely a library bug
//! (not an expected Aerospike server error), these helpers log a message
//! suggesting the user file a GitHub issue.

use log::error;

const REPO: &str = "KimSoungRyoul/aerospike-py";

/// Escape single quotes for shell single-quoted strings: `'` → `'\''`.
fn shell_escape(s: &str) -> String {
    s.replace('\'', "'\\''")
}

/// Truncate and sanitize a string for use in a GitHub issue title.
fn sanitize_for_title(s: &str, max_len: usize) -> String {
    let cleaned: String = s.chars().map(|c| if c == '\n' { ' ' } else { c }).collect();
    if cleaned.len() <= max_len {
        cleaned
    } else {
        format!("{}...", &cleaned[..max_len - 3])
    }
}

/// Log an unexpected internal error with a `gh issue create` command.
///
/// Only call this for errors that are NOT expected Aerospike errors.
pub fn log_unexpected_error(context: &str, error_detail: &str) {
    let version = env!("CARGO_PKG_VERSION");
    let title = format!("Unexpected error: {}", sanitize_for_title(error_detail, 80));
    let body =
        format!("aerospike-py version: {version}\nContext: {context}\nError: {error_detail}");
    error!(
        "Unexpected internal error in aerospike-py ({context}): {error_detail}\n\
         \n\
         This error may be a bug in aerospike-py. Please report it by running:\n\
         gh issue create --repo {REPO} \
         --title '{title}' \
         --body '{body}'",
        title = shell_escape(&title),
        body = shell_escape(&body),
    );
}

/// Replace `unreachable!()` with a version that logs a bug report
/// and returns a `PyErr` instead of panicking.
macro_rules! internal_bug {
    ($context:expr, $($arg:tt)*) => {{
        let detail = format!($($arg)*);
        $crate::bug_report::log_unexpected_error($context, &detail);
        Err(pyo3::exceptions::PyRuntimeError::new_err(
            format!("aerospike-py internal error ({}): {}", $context, detail)
        ))
    }};
}

pub(crate) use internal_bug;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_short_string() {
        assert_eq!(sanitize_for_title("hello", 80), "hello");
    }

    #[test]
    fn test_sanitize_long_string() {
        let long = "a".repeat(100);
        let result = sanitize_for_title(&long, 80);
        assert_eq!(result.len(), 80);
        assert!(result.ends_with("..."));
    }

    #[test]
    fn test_sanitize_newlines() {
        assert_eq!(sanitize_for_title("line1\nline2", 80), "line1 line2");
    }

    #[test]
    fn test_sanitize_exact_length() {
        let exact = "a".repeat(80);
        assert_eq!(sanitize_for_title(&exact, 80), exact);
    }

    #[test]
    fn test_shell_escape_no_quotes() {
        assert_eq!(shell_escape("hello world"), "hello world");
    }

    #[test]
    fn test_shell_escape_with_quotes() {
        assert_eq!(shell_escape("it's a bug"), "it'\\''s a bug");
    }
}
