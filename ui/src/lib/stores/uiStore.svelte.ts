export interface ActiveRun {
  id: string
  task: string
  executor: string
  agent: string
  model: string
  startedAt: number
}

let runOpen = $state(false)
let cfOpen = $state(false)
let marketOpen = $state(false)
let sidebarCollapsed = $state(false)
let costPanelCollapsed = $state(false)
let activeModal = $state<string | null>(null)
let activeRuns = $state<ActiveRun[]>([])

function closeAll() {
  runOpen = false
  cfOpen = false
  marketOpen = false
  activeModal = null
}

function pushRun(run: ActiveRun) {
  activeRuns = [...activeRuns, run]
}

function resolveRun(id: string) {
  activeRuns = activeRuns.filter(r => r.id !== id)
}

export const ui = {
  get runOpen() { return runOpen },
  set runOpen(v: boolean) { runOpen = v },
  get cfOpen() { return cfOpen },
  set cfOpen(v: boolean) { cfOpen = v },
  get marketOpen() { return marketOpen },
  set marketOpen(v: boolean) { marketOpen = v },
  get sidebarCollapsed() { return sidebarCollapsed },
  set sidebarCollapsed(v: boolean) { sidebarCollapsed = v },
  get costPanelCollapsed() { return costPanelCollapsed },
  set costPanelCollapsed(v: boolean) { costPanelCollapsed = v },
  get activeModal() { return activeModal },
  set activeModal(v: string | null) { activeModal = v },
  get activeRuns() { return activeRuns },
  closeAll,
  pushRun,
  resolveRun,
}
