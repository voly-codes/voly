/**
 * Build PipelineStages rows and token-bar segments from a TaskEvent-shaped task.
 */
import {
  RouteIcon, DatabaseIcon, ZapIcon, LayersIcon,
  BrainCircuitIcon, MessageSquareIcon, SaveIcon,
  BarChart2Icon, BookOpenIcon,
} from '../../icons.js'
import { statusRu, calcPct } from '../../utils/format.js'

export function buildTokenBar(task, t) {
  if (!task) return []
  const tokens = task.tokens ?? {}
  const rtkSaved = tokens.saved_rtk ?? 0
  const hrSaved = tokens.saved_headroom ?? 0
  const input = tokens.input ?? 0
  const output = tokens.output ?? 0
  const total = rtkSaved + hrSaved + input + output
  if (!total) return []
  const seg = (n) => Math.round((n / total) * 100)
  return [
    { label: 'RTK', value: rtkSaved, pct: seg(rtkSaved), color: 'var(--accent-teal)' },
    { label: 'Headroom', value: hrSaved, pct: seg(hrSaved), color: 'var(--accent-purple)' },
    { label: t('tokens.input'), value: input, pct: seg(input), color: 'var(--accent-blue)' },
    { label: t('tokens.output'), value: output, pct: seg(output), color: 'var(--accent-indigo)' },
  ].filter((s) => s.value > 0)
}

export function buildPipelineStages(task, t) {
  if (!task) return []
  const tokens = task.tokens ?? {}
  const gw = task.gateway ?? {}
  const totalIn = tokens.input ?? 0
  const savedRtk = tokens.saved_rtk ?? 0
  const savedHr = tokens.saved_headroom ?? 0

  return [
    {
      id: 'route', label: t('stage.route'),
      hint: t('stage.route.hint'),
      icon: RouteIcon, detail: `${task.agent} → ${task.model}`, meta: task.provider ?? '',
      badge: task.routing_score ? `score ${(task.routing_score * 100).toFixed(0)}%` : null, ok: true,
    },
    {
      id: 'memory', label: t('stage.memory'),
      hint: t('stage.memory.hint'),
      icon: DatabaseIcon,
      detail: task.memory_hits ? t('stage.memory.hits', { n: task.memory_hits }) : t('stage.memory.none'),
      meta: '', badge: task.memory_hits ? `+${task.memory_hits}` : null,
      badgeColor: task.memory_hits ? 'var(--accent-blue)' : null, ok: true,
    },
    {
      id: 'rtk', label: t('stage.rtk'),
      hint: t('stage.rtk.hint'),
      icon: ZapIcon,
      detail: savedRtk ? t('stage.rtk.saved', { n: savedRtk.toLocaleString() }) : t('stage.rtk.none'),
      meta: savedRtk ? t('stage.reduction', { n: calcPct(savedRtk, totalIn) }) : '',
      badge: savedRtk ? `-${savedRtk.toLocaleString()}` : null,
      badgeColor: savedRtk ? 'var(--accent-teal)' : null, ok: true,
    },
    {
      id: 'skill_inject', label: t('stage.skills'),
      hint: t('stage.skills.hint'),
      icon: BookOpenIcon,
      detail: task.skill_ids?.length
        ? t('stage.skills.injected', { n: task.skill_ids.length })
        : t('stage.skills.none'),
      meta: task.skill_ids?.join(', ') ?? '',
      badge: task.skill_ids?.length ? `+${task.skill_ids.length}` : null,
      badgeColor: task.skill_ids?.length ? 'var(--accent-teal)' : null, ok: true,
    },
    {
      id: 'headroom', label: t('stage.headroom'),
      hint: t('stage.headroom.hint'),
      icon: LayersIcon,
      detail: savedHr ? t('stage.headroom.saved', { n: savedHr.toLocaleString() }) : t('stage.headroom.none'),
      meta: savedHr ? t('stage.reduction', { n: calcPct(savedHr, totalIn) }) : '',
      badge: savedHr ? `-${savedHr.toLocaleString()}` : null,
      badgeColor: savedHr ? 'var(--accent-purple)' : null, ok: true,
    },
    ...(task.dspy_enabled ? [{
      id: 'dspy', label: t('stage.dspy'),
      hint: t('stage.dspy.hint'),
      icon: BrainCircuitIcon, detail: task.dspy_program_id ?? t('stage.dspy.enabled'),
      meta: t('stage.dspy.meta', { mode: task.dspy_mode ?? 'shadow', tag: task.dspy_program_tag ?? '—' }),
      badge: task.dspy_mode, ok: true,
    }] : []),
    {
      id: 'model_call', label: t('stage.model'),
      hint: t('stage.model.hint'),
      icon: MessageSquareIcon,
      detail: t('stage.model.tokens', {
        in: totalIn.toLocaleString(),
        out: (tokens.output ?? 0).toLocaleString(),
      }),
      meta: [
        gw.cache_hit ? t('stage.model.cacheHit') : null,
        gw.fallback_used ? `fallback → ${gw.fallback_model || '?'}` : null,
        gw.dlp_blocked ? t('stage.model.dlpBlocked') : null,
      ].filter(Boolean).join(' · ') || `${task.provider ?? ''}`,
      badge: gw.cache_hit ? t('stage.model.cacheBadge') : (gw.fallback_used ? 'fallback' : null),
      badgeColor: gw.cache_hit ? 'var(--accent-green)' : (gw.fallback_used ? 'var(--accent-amber)' : null),
      ok: !gw.dlp_blocked,
    },
    {
      id: 'memory_store', label: t('stage.store'),
      hint: t('stage.store.hint'),
      icon: SaveIcon,
      detail: task.status === 'completed' ? t('stage.store.saved') : t('stage.store.skipped'),
      ok: task.status === 'completed',
    },
    {
      id: 'telemetry', label: t('stage.telemetry'),
      hint: t('stage.telemetry.hint'),
      icon: BarChart2Icon,
      detail: task.duration_ms
        ? t('stage.telemetry.total', { s: (task.duration_ms / 1000).toFixed(2) })
        : '—',
      meta: t('stage.telemetry.status', { s: statusRu[task.status] ?? task.status }),
      ok: task.status === 'completed',
    },
  ]
}
