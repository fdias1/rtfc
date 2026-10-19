import type { RtfcBridge } from '../shared/ipc'

declare global {
  interface Window {
    rtfc: RtfcBridge
  }
}
