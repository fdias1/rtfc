import { levelToFraction } from '../lib/format'
import { useSession } from '../store/session'

export function LevelMeter(): React.JSX.Element {
  const level = useSession((s) => s.level)
  const fraction = levelToFraction(level.rms)
  const peak = levelToFraction(level.peak)
  const clipping = level.peak >= 0.99

  return (
    <div
      className="relative h-2 w-full overflow-hidden rounded-full bg-primary-soft"
      role="meter"
      aria-label="Nível do áudio"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(fraction * 100)}
      data-testid="level-meter"
    >
      <div
        className="absolute inset-y-0 left-0 rounded-full bg-primary transition-[width] duration-75"
        style={{ width: `${fraction * 100}%` }}
      />
      <div
        className={`absolute inset-y-0 w-0.5 ${clipping ? 'bg-verdict-false' : 'bg-primary-strong'}`}
        style={{ left: `calc(${peak * 100}% - 2px)`, opacity: peak > 0 ? 1 : 0 }}
      />
    </div>
  )
}
