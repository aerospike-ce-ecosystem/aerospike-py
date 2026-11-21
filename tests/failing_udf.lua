-- A UDF that changes the record and then fails.
--
-- The server rolls a failed UDF back, so the change must not be there
-- afterwards. Tests use it to pin that a UDF failure is a definite answer:
-- nothing was applied, and nothing is in doubt.

function update_then_fail(rec)
    rec['touched'] = 1
    aerospike:update(rec)
    error("failing on purpose after the update")
end
