// Captura de áudio: loopback do sistema via getDisplayMedia, permissões de mídia e do SO.

import { app, desktopCapturer, session, shell, systemPreferences } from 'electron'
import type { MediaAccess } from '@shared/ipc'

/** Modo de teste E2E (ver enableLoopbackFeatures). */
const fakeMedia = process.env.RTFC_FAKE_MEDIA === '1'

/**
 * Precisa rodar antes do `app.ready`. No macOS, força o áudio do sistema via ScreenCaptureKit
 * (coberto pela permissão de Gravação de Tela).
 */
export function enableLoopbackFeatures(): void {
  if (fakeMedia) {
    // Testes E2E: microfone falso do Chromium (tom contínuo) e sem diálogos de permissão.
    app.commandLine.appendSwitch('use-fake-device-for-media-stream')
    app.commandLine.appendSwitch('use-fake-ui-for-media-stream')
  }
  if (process.platform === 'darwin') {
    app.commandLine.appendSwitch('enable-features', 'MacLoopbackAudioForScreenShare,MacSckSystemAudioLoopbackOverride')
    // O caminho padrão do Chromium 15x (Core Audio Taps) entrega silêncio sem a permissão
    // "Gravação de Áudio do Sistema", que o app em dev não consegue pedir. Ver ADR 0002.
    app.commandLine.appendSwitch('disable-features', 'MacCatapLoopbackAudioForScreenShare')
  }
}

const ALLOWED_PERMISSIONS = new Set(['media', 'display-capture', 'clipboard-sanitized-write'])

export function setupCapture(): void {
  const ses = session.defaultSession

  // getDisplayMedia() no renderer: sem seletor de janela, pega a tela principal só para obter o
  // áudio do sistema (o renderer descarta o vídeo na hora).
  ses.setDisplayMediaRequestHandler(
    (_request, callback) => {
      desktopCapturer
        .getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } })
        .then((sources) => {
          const screen = sources[0]
          if (!screen) throw new Error('nenhuma tela disponível')
          callback({ video: screen, audio: 'loopback' })
        })
        .catch((err: unknown) => {
          console.error('[capture] getDisplayMedia falhou:', err)
          // Sem argumentos válidos o Chromium rejeita a promise no renderer.
          callback({})
        })
    },
    { useSystemPicker: false }
  )

  ses.setPermissionRequestHandler((_wc, permission, callback) => callback(ALLOWED_PERMISSIONS.has(permission)))
  ses.setPermissionCheckHandler((_wc, permission) => ALLOWED_PERMISSIONS.has(permission))
}

export async function ensureMicrophoneAccess(): Promise<boolean> {
  if (fakeMedia || process.platform !== 'darwin') return true
  if (systemPreferences.getMediaAccessStatus('microphone') === 'granted') return true
  return systemPreferences.askForMediaAccess('microphone')
}

export function getMediaAccess(kind: 'microphone' | 'screen'): MediaAccess {
  if (process.platform !== 'darwin' && process.platform !== 'win32') return 'granted'
  return systemPreferences.getMediaAccessStatus(kind)
}

export async function openPrivacySettings(kind: 'microphone' | 'screen'): Promise<void> {
  if (process.platform === 'darwin') {
    const pane = kind === 'microphone' ? 'Privacy_Microphone' : 'Privacy_ScreenCapture'
    await shell.openExternal(`x-apple.systempreferences:com.apple.preference.security?${pane}`)
  } else if (process.platform === 'win32' && kind === 'microphone') {
    await shell.openExternal('ms-settings:privacy-microphone')
  }
}
