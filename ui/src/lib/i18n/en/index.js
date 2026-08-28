import common from './common.js'
import tasks from './tasks.js'
import gateway from './gateway.js'
import telemetry from './telemetry.js'
import dspy from './dspy.js'
import cf from './cf.js'
import decisions from './decisions.js'

/** @type {Record<string, string | string[]>} */
export default {
  ...common,
  ...tasks,
  ...gateway,
  ...telemetry,
  ...dspy,
  ...cf,
  ...decisions,
}
