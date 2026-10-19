"""Buffer circular de PCM com posição absoluta, para os consumidores do pipeline (M2+)."""

from dataclasses import dataclass

from rtfc.audio import BYTES_PER_SAMPLE, PIPELINE_SAMPLE_RATE


@dataclass(frozen=True)
class PcmRead:
    data: bytes
    start_sample: int
    """Posição absoluta (em amostras desde o início da sessão) do primeiro byte de `data`."""
    dropped_samples: int
    """Amostras perdidas porque o leitor ficou para trás mais que a capacidade do buffer."""


class PcmRingBuffer:
    """Guarda os últimos `capacity_s` segundos de PCM s16le mono.

    Escrita contínua; cada leitor guarda sua posição absoluta e pede o que veio depois dela.
    """

    def __init__(self, capacity_s: float = 60.0, sample_rate: int = PIPELINE_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._capacity = int(capacity_s * sample_rate) * BYTES_PER_SAMPLE
        self._buf = bytearray()
        self._start_byte = 0  # posição absoluta (em bytes) de self._buf[0]
        self._pending_odd = b""  # meio sample de um chunk ímpar

    @property
    def total_samples(self) -> int:
        return (self._start_byte + len(self._buf)) // BYTES_PER_SAMPLE

    @property
    def duration_ms(self) -> int:
        return self.total_samples * 1000 // self.sample_rate

    def write(self, chunk: bytes) -> None:
        if self._pending_odd:
            chunk = self._pending_odd + chunk
            self._pending_odd = b""
        if len(chunk) % BYTES_PER_SAMPLE:
            chunk, self._pending_odd = chunk[:-1], chunk[-1:]
        self._buf += chunk
        overflow = len(self._buf) - self._capacity
        if overflow > 0:
            del self._buf[:overflow]
            self._start_byte += overflow

    def read_since(self, sample: int) -> PcmRead:
        want = sample * BYTES_PER_SAMPLE
        dropped = max(0, self._start_byte - want)
        begin = max(want, self._start_byte) - self._start_byte
        data = bytes(self._buf[begin:])
        start = (self._start_byte + begin) // BYTES_PER_SAMPLE
        return PcmRead(data=data, start_sample=start, dropped_samples=dropped // BYTES_PER_SAMPLE)
