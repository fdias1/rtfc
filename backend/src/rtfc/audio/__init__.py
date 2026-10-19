"""Ingestão de áudio: gravação de sessões ao vivo e decodificação de arquivos.

Todo áudio que entra no pipeline é PCM s16le mono 16 kHz (ver ADR 0001).
"""

PIPELINE_SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2
