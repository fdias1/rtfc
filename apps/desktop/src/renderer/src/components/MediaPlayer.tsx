import { mediaUrl } from '@shared/media'
import type { SessionInfo } from '@rtfc/protocol'
import { basename } from '../lib/format'

/** Player da sessão: vídeo/áudio original nas sessões de arquivo, `audio.ogg` nas ao vivo encerradas. */
export function MediaPlayer({ session }: { session: SessionInfo }): React.JSX.Element {
  const src = mediaUrl(session.audio_path)
  const title = session.source === 'file' ? basename(session.file_path ?? session.audio_path) : 'Gravação da sessão'

  return (
    <div className="flex flex-col gap-2" data-testid="media-player">
      <div className="flex items-baseline justify-between gap-3 text-xs">
        <span className="truncate font-medium text-text" title={session.audio_path}>
          {title}
        </span>
        <span className="shrink-0 font-mono text-text-muted">{session.id}</span>
      </div>
      {session.media_kind === 'video' ? (
        <video key={src} src={src} controls className="max-h-[45vh] w-full rounded-md bg-black" />
      ) : (
        <audio key={src} src={src} controls preload="metadata" className="w-full" />
      )}
    </div>
  )
}
