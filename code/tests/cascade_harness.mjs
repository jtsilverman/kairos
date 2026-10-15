// Runs cascade_workflow.js with stub seats and prints what happened.
// The harness globals (args, agent, parallel, pipeline, log) are what the
// Workflow tool provides; here they are stubs that record every seat call.
//
// Usage: node cascade_harness.mjs <script.js> <verdictPlanJSON>
// The plan maps slug -> array of verdicts the triage seats return in order,
// plus optional `_adjudicate` per slug for the PANEL rule's opus seat.
import { readFileSync } from 'node:fs'

const src = readFileSync(process.argv[2], 'utf8').replace('export const meta', 'const meta')
const plan = JSON.parse(process.argv[3])

const calls = []
const models = []
const agent = async (prompt, opts) => {
  calls.push(opts.label)
  models.push(`${opts.label.split(':')[0]}=${opts.model}`)
  const [kind, slug] = opts.label.split(':')
  if (kind === 'adjudicate') {
    const v = plan[slug]?._adjudicate
    return v === null ? null : { verdict: v, decisive_number: '1', reason: 'r' }
  }
  const pass = Number(opts.label.split(':')[2])
  const v = plan[slug]?.passes?.[pass - 1]
  if (v === undefined || v === null) return null
  return { verdict: v, decisive_number: '1', reason: 'r' }
}
const parallel = (fns) => Promise.all(fns.map((f) => f()))
const pipeline = async (items, ...stages) => {
  const out = []
  for (const it of items) { let v = it; for (const s of stages) v = await s(v, it); out.push(v) }
  return out
}
const log = () => {}

const packet = Object.keys(plan).map((slug) => ({ slug, sheet: 'sheet' }))
const args = { asOf: '2026-02-02', packet }
const body = new Function('args', 'agent', 'parallel', 'pipeline', 'log',
  `return (async () => { ${src} })()`)
const res = await body(args, agent, parallel, pipeline, log)
console.log(JSON.stringify({ res, calls, models }))
