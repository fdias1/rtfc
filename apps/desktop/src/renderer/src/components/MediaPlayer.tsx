import { useCallback } from 'react'
import { mediaUrl } from '@shared/media'
import type { SessionInfo } from '@rtfc/protocol'
import { usePlayer } from '../store/player'

/** Player da sessão: vídeo/áudio original nas sessões de arquivo, `audio.ogg` nas ao vivo encerradas. */
export function MediaPlayer({ session }: { session: SessionInfo }): React.JSX.Element {
  const attach = usePlayer((s) => s.attach)
  const src = mediaUrl(session.audio_path)
  // Ref de callback: registra o elemento no store do player e o solta ao desmontar.
  const ref = useCallback((el: HTMLMediaElement | null) => attach(el), [attach])

  return (
    <div data-testid="media-player">
      {session.media_kind === 'video' ? (
        <video ref={ref} key={src} src={src} controls className="max-h-[40vh] w-full rounded-md bg-black" />
      ) : (
        <audio ref={ref} key={src} src={src} controls preload="metadata" className="w-full" />
      )}
    </div>
  )
}
