# ADR 0002 — Captura do áudio do sistema

**Status:** aceito · 2026-10-19 · Marco M1

## Decisão por plataforma

| SO | Mecanismo | Estado |
|---|---|---|
| **macOS** | `getDisplayMedia` + `setDisplayMediaRequestHandler({ audio: 'loopback' })`, com as features `MacLoopbackAudioForScreenShare` e `MacSckSystemAudioLoopbackOverride` **e** `--disable-features=MacCatapLoopbackAudioForScreenShare` | ✅ validado no M2 Pro / macOS 26.5 |
| **Windows** | Mesmo caminho (`audio: 'loopback'` via WASAPI) | ⚠️ implementado, não validado em hardware |
| **Linux** | O backend captura o monitor padrão do PulseAudio/PipeWire (`ffmpeg -f pulse -i @DEFAULT_MONITOR@`) | ⚠️ experimental, não validado |

## Por que desligar o Core Audio Taps no macOS
O Chromium 152 (Electron 44) usa por padrão o **Core Audio Taps** (CATap) para o loopback. Esse caminho exige a permissão de **Gravação de Áudio do Sistema** (TCC `kTCCServiceAudioCapture`). Sem ela, **entrega silêncio sem nenhum erro**: medimos pico 0,0, mesmo com a Gravação de Tela concedida. Forçando o **ScreenCaptureKit**, o áudio vem coberto pela permissão de Gravação de Tela (pico 0,64, gravação a -3,6 dBFS).

## Outros achados
- O track de loopback vem com `echoCancellation`, `noiseSuppression` e `autoGainControl` ligados. O cancelador de eco remove justamente o som dos alto-falantes. Desligamos os três na constraint.
- O vídeo do `getDisplayMedia` é descartado logo depois de obtido.

## A revisitar
- No M9, com o app empacotado e assinado (Info.plist próprio com `NSAudioCaptureUsageDescription`), reavaliar o CATap: ele não exige compartilhar a tela.
- Validar Windows e Linux no M9, em hardware real.
