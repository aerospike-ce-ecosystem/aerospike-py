"""Unit tests for set_log_level validation and TRACE level registration."""

import logging

import pytest

import aerospike_py


class TestTraceLevelRegistered:
    def test_trace_level_name_registered(self):
        """Numeric level 5 must render as 'TRACE', not 'Level 5'."""
        assert logging.getLevelName(5) == "TRACE"

    def test_trace_record_formats_as_trace(self):
        record = logging.LogRecord(
            name="aerospike_py",
            level=5,
            pathname=__file__,
            lineno=1,
            msg="trace message",
            args=(),
            exc_info=None,
        )
        assert record.levelname == "TRACE"


class TestSetLogLevelValid:
    @pytest.mark.parametrize(
        "level,expected",
        [
            (aerospike_py.LOG_LEVEL_OFF, logging.CRITICAL + 1),
            (aerospike_py.LOG_LEVEL_ERROR, logging.ERROR),
            (aerospike_py.LOG_LEVEL_WARN, logging.WARNING),
            (aerospike_py.LOG_LEVEL_INFO, logging.INFO),
            (aerospike_py.LOG_LEVEL_DEBUG, logging.DEBUG),
            (aerospike_py.LOG_LEVEL_TRACE, 5),
        ],
    )
    def test_valid_levels_applied(self, level, expected):
        try:
            aerospike_py.set_log_level(level)
            assert logging.getLogger("aerospike_py").level == expected
        finally:
            # Reset to a sane default so other tests are unaffected.
            logging.getLogger("aerospike_py").setLevel(logging.WARNING)


class TestSetLogLevelInvalid:
    @pytest.mark.parametrize("bad_level", [5, 99, -2, 100])
    def test_invalid_level_raises_value_error(self, bad_level):
        with pytest.raises(ValueError, match="LOG_LEVEL"):
            aerospike_py.set_log_level(bad_level)

    def test_invalid_level_does_not_change_logger(self):
        logging.getLogger("aerospike_py").setLevel(logging.INFO)
        with pytest.raises(ValueError):
            aerospike_py.set_log_level(42)
        assert logging.getLogger("aerospike_py").level == logging.INFO
        logging.getLogger("aerospike_py").setLevel(logging.WARNING)
