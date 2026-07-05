export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}

const DEFAULT_DURATION = 3500

let toasts = $state<Toast[]>([])

function add(type: ToastType, message: string, duration?: number) {
  const id = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)
  toasts = [...toasts, { id, type, message, duration }]
  setTimeout(() => dismiss(id), duration ?? DEFAULT_DURATION)
}

function dismiss(id: string) {
  toasts = toasts.filter(t => t.id !== id)
}

export const toast = {
  get all() { return toasts },
  success(msg: string) { add('success', msg) },
  error(msg: string) { add('error', msg, 6000) },
  warning(msg: string) { add('warning', msg, 5000) },
  info(msg: string) { add('info', msg) },
  dismiss,
}
