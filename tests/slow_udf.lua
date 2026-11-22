-- A UDF that keeps the server busy for a while and changes nothing.
--
-- Tests use it to make a client deadline expire for certain: the only
-- other way to get a timeout out of a healthy server is to race it, and a
-- race is not a test.

function spin(rec, rounds)
    local total = 0
    for i = 1, rounds do
        total = total + (i % 7)
    end
    return total
end
