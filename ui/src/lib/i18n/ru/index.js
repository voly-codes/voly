import common from './common.js'
import tasks from './tasks.js'
import gateway from './gateway.js'
import telemetry from './telemetry.js'
import dspy from './dspy.js'
import cf from './cf.js'
import auth from './auth.js'

/** @type {Record<string, string | string[]>} */
export default {
  ...common,
  ...tasks,
  ...gateway,
  ...telemetry,
  ...dspy,
  ...cf,
  ...auth,
}
