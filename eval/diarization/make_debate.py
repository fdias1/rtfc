"""Gera um "debate" sintético com vozes pt-BR do macOS (`say`) e o gabarito de falantes.

Não substitui um debate real (as vozes sintéticas são mais fáceis de separar), mas dá uma
medida reproduzível e sem direitos autorais para o aceite do M4.

Uso: uv run --project backend python eval/diarization/make_debate.py [pasta de saída]
"""

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 16_000
GAP_S = 0.35

VOICES = {
    "A": "Luciana",
    "B": "Eddy (Portuguese (Brazil))",
    "C": "Flo (Portuguese (Brazil))",
}

TURNS = [
    ("C", "Boa noite. Vamos começar o debate de hoje com o tema da economia."),
    ("A", "Obrigada. O desemprego caiu para o menor nível da série histórica, segundo o IBGE."),
    ("A", "E a inflação ficou dentro da meta pelo segundo ano seguido."),
    ("B", "Isso não é verdade. A inflação dos alimentos subiu mais de dez por cento no ano."),
    ("B", "Quem vai ao supermercado sabe que o preço do arroz e do feijão disparou."),
    ("C", "Candidata, a senhora tem trinta segundos para responder."),
    ("A", "O preço do arroz caiu nos últimos seis meses. Os dados estão no site do governo."),
    ("B", "Os dados do governo são maquiados. A dívida pública passou de oitenta por cento do PIB."),
    ("C", "Vamos para o segundo bloco. O tema agora é segurança pública."),
    ("B", "No meu estado, os homicídios caíram quarenta por cento em quatro anos."),
    ("A", "Esse número considera só a capital. No interior a violência aumentou."),
    ("B", "Não, o número é do estado inteiro, e foi divulgado pelo Fórum de Segurança."),
    ("A", "Então explique por que a polícia perdeu dois mil agentes no seu mandato."),
    ("C", "Tempo esgotado. Peço aos candidatos que respeitem as regras."),
    ("B", "Eu respeito as regras. Foi ela quem me interrompeu."),
    ("A", "Eu só respondi a uma informação falsa."),
    ("C", "Terceiro bloco, educação. Candidato, sua pergunta."),
    ("B", "Por que o seu governo fechou mais de trezentas escolas rurais?"),
    ("A", "Nós não fechamos escolas. Nós juntamos turmas pequenas e abrimos vagas em tempo integral."),
    ("A", "Hoje temos o dobro de alunos em tempo integral do que tínhamos em dois mil e vinte."),
    ("B", "O dobro de quase nada continua sendo muito pouco."),
    ("C", "Encerramos aqui. Obrigada aos candidatos e a quem nos acompanhou."),
]


def synth(text: str, voice: str, out: Path) -> None:
    subprocess.run(
        ["say", "-v", voice, "-o", str(out), f"--data-format=LEI16@{RATE}", text], check=True
    )


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/diarization/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    truth = []
    gap = b"\x00\x00" * int(GAP_S * RATE)
    with tempfile.TemporaryDirectory() as tmp:
        for i, (speaker, text) in enumerate(TURNS):
            path = Path(tmp) / f"{i}.wav"
            synth(text, VOICES[speaker], path)
            with wave.open(str(path)) as w:
                data = w.readframes(w.getnframes())
            start = len(frames) // 2 / RATE
            frames += data
            truth.append({"start": start, "end": len(frames) // 2 / RATE, "speaker": speaker})
            frames += gap
    with wave.open(str(out_dir / "debate.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    (out_dir / "debate.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    print(f"{out_dir / 'debate.wav'}: {len(frames) / 2 / RATE:.0f} s, {len(TURNS)} falas")


if __name__ == "__main__":
    main()
