let runOpen = $state(false)
let cfOpen = $state(false)
let marketOpen = $state(false)
let gatewayOpen = $state(false)
let telemetryOpen = $state(false)
let dspyOpen = $state(false)
let sidebarCollapsed = $state(false)
let costPanelCollapsed = $state(false)
let activeModal = $state<string | null>(null)

function closeAll() {
  runOpen = false
  cfOpen = false
  marketOpen = false
  gatewayOpen = false
  telemetryOpen = false
  dspyOpen = false
  activeModal = null
}

export const ui = {
  get runOpen() { return runOpen },
  set runOpen(v: boolean) { runOpen = v },
  get cfOpen() { return cfOpen },
  set cfOpen(v: boolean) { cfOpen = v },
  get marketOpen() { return marketOpen },
  set marketOpen(v: boolean) { marketOpen = v },
  get gatewayOpen() { return gatewayOpen },
  set gatewayOpen(v: boolean) { gatewayOpen = v },
  get telemetryOpen() { return telemetryOpen },
  set telemetryOpen(v: boolean) { telemetryOpen = v },
  get dspyOpen() { return dspyOpen },
  set dspyOpen(v: boolean) { dspyOpen = v },
  get sidebarCollapsed() { return sidebarCollapsed },
  set sidebarCollapsed(v: boolean) { sidebarCollapsed = v },
  get costPanelCollapsed() { return costPanelCollapsed },
  set costPanelCollapsed(v: boolean) { costPanelCollapsed = v },
  get activeModal() { return activeModal },
  set activeModal(v: string | null) { activeModal = v },
  closeAll,
}
