import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Timer } from 'lucide-react'

export function useCountdown(isoTarget?: string) {
  const [remaining, setRemaining] = useState<{ h: number; m: number; s: number } | null>(null)

  useEffect(() => {
    if (!isoTarget) { setRemaining(null); return }

    const calc = () => {
      const diff = new Date(isoTarget).getTime() - Date.now()
      if (diff <= 0) return null
      const totalSec = Math.floor(diff / 1000)
      return {
        h: Math.floor(totalSec / 3600),
        m: Math.floor((totalSec % 3600) / 60),
        s: totalSec % 60,
      }
    }

    setRemaining(calc())
    const id = setInterval(() => {
      const r = calc()
      setRemaining(r)
      if (!r) clearInterval(id)
    }, 1000)
    return () => clearInterval(id)
  }, [isoTarget])

  return remaining
}

export default function CountdownDisplay({ isoTarget, skipped }: { isoTarget?: string, skipped?: boolean }) {
  const { t } = useTranslation()
  const cd = useCountdown(isoTarget)
  if (!cd || skipped) return null

  const text = cd.h > 0
    ? t('schedule.countdown', { h: cd.h, m: String(cd.m).padStart(2, '0'), s: String(cd.s).padStart(2, '0') })
    : t('schedule.countdownShort', { m: cd.m, s: String(cd.s).padStart(2, '0') })

  return (
    <span className="inline-flex items-center gap-1 text-xs text-primary-400 font-mono">
      <Timer size={11} />{text}
    </span>
  )
}
