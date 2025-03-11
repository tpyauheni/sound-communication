TODO:
1. Scan FFTs until there is huge spike (or fall) in one of needed frequencies.
    1.1. If that frequency was considered ON (OFF if freq. fall) already, then ignore it as a noise spike.
    1.2. If that frequency was considered OFF (ON if freq. fall), then invert it.
2. Wait `duration` seconds (should be less than Sender's `duration`; to be exact - half of it) from first frequency change in currrent batch.
    2.1. If at least one frequency was considered ON and no other frequencies changed for that time, then it's fine.
    2.2. If one bit changed during that `duration` then... Well, no luck. Consider it broken and request resending of the entire block (in the future).
3. At the next huge spike
