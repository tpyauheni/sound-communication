TODO:
1. Scan FFTs until there is huge spike (or fall) in one of needed frequencies.
    1.1. If that frequency was considered ON (OFF if freq. fall) already, then ignore it as a noise spike.
    1.2. If that frequency was considered OFF (ON if freq. fall), then invert it.
2. Wait `duration` seconds (should be less than Sender's `duration`) from first frequency change in currrent batch.
    2.1. If at least one frequency was considered ON and no other frequencies changed for that time, then it's fine.
    2.2. If one bit changed during that `duration` then... Well, no luck. Consider it broken and request resending of the entire block (in the future).
3. Repeat

In practical terms:
1. Open audio input device with relatively large number of scans per second.
2. Scan unless at least two bits are considered ON (counter bit must be set in the first message + any message will either be non-zero or transmission bit will be set).
3. For the future - somehow determine time when sender sent those bits more precisely.
4. Store that time (for now only the time that peer received >= 2 bits from another peer).
5. Record time from previous FFT analysis.
6. If it exceeds (or equals to) `duration` then perform FFT analysis with all the bytes from audio input concatenated.
7. For another peer, measure the time from the very first packet and make sure to keep time between bit batches to be exactly `duration`.
    If it is greater than `duration` by special treshold then cut some bytes from the next sample
    If it is less than `duration` by special treshold then concatenate some bytes from the beginning of the sample to its end (ugly solution!)

