from rtfc.audio.ring_buffer import PcmRingBuffer


def samples(n: int, start: int = 0) -> bytes:
    return b"".join((i % 30000).to_bytes(2, "little") for i in range(start, start + n))


def test_read_since_returns_new_data_with_absolute_position() -> None:
    buf = PcmRingBuffer(capacity_s=1, sample_rate=10)
    buf.write(samples(4))
    r = buf.read_since(0)
    assert (r.data, r.start_sample, r.dropped_samples) == (samples(4), 0, 0)
    buf.write(samples(3, start=4))
    r = buf.read_since(4)
    assert (r.data, r.start_sample) == (samples(3, start=4), 4)
    assert buf.total_samples == 7
    assert buf.duration_ms == 700


def test_overflow_drops_oldest_and_reports_it() -> None:
    buf = PcmRingBuffer(capacity_s=1, sample_rate=10)  # 10 amostras
    buf.write(samples(25))
    r = buf.read_since(0)
    assert r.start_sample == 15
    assert r.dropped_samples == 15
    assert r.data == samples(10, start=15)


def test_odd_chunks_are_reassembled() -> None:
    buf = PcmRingBuffer(capacity_s=1, sample_rate=10)
    data = samples(3)
    buf.write(data[:3])
    assert buf.total_samples == 1
    buf.write(data[3:])
    assert buf.read_since(0).data == data
