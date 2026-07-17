import { fetchTasks, fetchTask, fetchSummary, fetchStatus, taskStream } from '../api/client.js'
import { liveTaskFromRun } from '../utils/liveTask.js'
import { router } from './routerStore.svelte'

let tasks = $state<any[]>([])
let selected = $state<any>(null)
let summary = $state<any>(null)
let status = $state<any>(null)
let loading = $state(true)
let error = $state<string | null>(null)
let unseenIds = $state<Set<string>>(new Set())

let _es: EventSource | null = null
let _pollTimer: ReturnType<typeof setInterval> | null = null
let _sseFailures = 0
const MAX_SSE_FAILURES = 3
const POLL_INTERVAL_MS = 10_000

function _startPolling() {
  if (_pollTimer) return
  _pollTimer = setInterval(refresh, POLL_INTERVAL_MS)
}

function _stopPolling() {
  if (_pollTimer) {
    clearInterval(_pollTimer)
    _pollTimer = null
  }
}

// Merge SSE tasks into the list (deduplicate by task_id, sort by mtime desc).
// markUnseen=false for the initial snapshot ("init") — historical tasks must
// not be badged as new after a page refresh or an SSE reconnect.
function _mergeNew(incoming: any[], markUnseen = true) {
  const map = new Map<string, any>()
  for (const t of tasks) map.set(t.task_id, t)
  for (const t of incoming) {
    const existing = map.get(t.task_id)
    const isNew = !existing
    if (isNew || (t._mtime ?? 0) > (existing._mtime ?? 0)) {
      map.set(t.task_id, t)
      if (markUnseen && isNew && selected?.task_id !== t.task_id) {
        unseenIds = new Set([...unseenIds, t.task_id])
      }
    }
  }
  tasks = [...map.values()].sort((a, b) => (b._mtime ?? 0) - (a._mtime ?? 0))

  // Auto-select if we have a deep-linked taskId
  if (router.taskId && selected?.task_id !== router.taskId) {
    const match = tasks.find((x: any) => x.task_id?.startsWith(router.taskId!))
    if (match) selected = match
  }
}

async function refresh() {
  try {
    const [t, s, st] = await Promise.all([fetchTasks(), fetchSummary(), fetchStatus()])
    tasks = t
    summary = s
    status = st
    error = null

    if (router.taskId && selected?.task_id !== router.taskId) {
      const match = tasks.find((x: any) => x.task_id?.startsWith(router.taskId!))
      if (match) selected = match
      else await loadById(router.taskId)
    }
  } catch (e: any) {
    error = e.message
  } finally {
    loading = false
  }
}

async function loadById(taskId: string) {
  try {
    const t = await fetchTask(taskId)
    if (t) selected = t
  } catch {}
}

function select(task: any) {
  selected = task
  if (task?.task_id) {
    unseenIds = new Set([...unseenIds].filter(id => id !== task.task_id))
    router.navigate('tasks', task.task_id.slice(0, 8))
  }
}

/** Open an in-flight /api/runs record in the inspector (live card while work runs). */
function selectLive(run: any) {
  const live = liveTaskFromRun(run)
  if (!live) return
  selected = live
  router.navigate('tasks', live.task_id.slice(0, 8))
}

/** Refresh selected live card when ActiveRuns polls the same task_id. */
function patchLive(run: any) {
  if (!selected?._live || !run?.task_id) return
  if (selected.task_id !== run.task_id) return
  const live = liveTaskFromRun(run)
  if (live) selected = live
}

function isUnseen(taskId: string): boolean {
  return unseenIds.has(taskId)
}

function markAllSeen() {
  unseenIds = new Set()
}

async function startStream() {
  try {
    const es = await taskStream()
    es.onopen = () => {
      _sseFailures = 0
      _stopPolling()
    }
    es.onmessage = (e) => {
      _sseFailures = 0
      _stopPolling()
      try {
        const msg = JSON.parse(e.data)
        if ((msg.type === 'new' || msg.type === 'init') && msg.tasks?.length) {
          _mergeNew(msg.tasks, msg.type === 'new')
        }
      } catch {}
    }
    es.onerror = () => {
      // EventSource auto-reconnects on its own; if it keeps failing, stop
      // waiting on it and fall back to polling so the UI doesn't go stale.
      _sseFailures += 1
      if (_sseFailures >= MAX_SSE_FAILURES) {
        es.close()
        if (_es === es) _es = null
        _startPolling()
      }
    }
    _es = es
  } catch {
    // Fallback: poll every 10s if EventSource not available
    _startPolling()
  }
  window.addEventListener('beforeunload', _stopPolling)
}

function stopStream() {
  _es?.close()
  _es = null
  _stopPolling()
  window.removeEventListener('beforeunload', _stopPolling)
}

export const tasksStore = {
  get tasks() { return tasks },
  get selected() { return selected },
  set selected(v) { selected = v },
  get summary() { return summary },
  get status() { return status },
  get loading() { return loading },
  get error() { return error },
  get unseenCount() { return unseenIds.size },
  isUnseen,
  markAllSeen,
  refresh,
  select,
  selectLive,
  patchLive,
  startStream,
  stopStream,
}
