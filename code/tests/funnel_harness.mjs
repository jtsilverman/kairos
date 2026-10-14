// Runs the generated funnel workflow with stub seats and prints what happened.
// The harness globals (args, agent, parallel, pipeline, log) are what the
// Workflow tool provides; here they are stubs that record every seat call.
import { readFileSync } from 'node:fs'
const src = readFileSync(process.argv[2], 'utf8').replace('export const meta', 'const meta')
const T = ['business_case', 'fundamentals', 'demand_case', 'positioned']
const cases = () => Object.fromEntries(T.map((t) => [t, { case: 'x'.repeat(200), strongest_fact: 'a fact of twenty chars', cites: ['Q1'] }]))
// The ruler now answers two questions per test. AAA wins every test whole;
// BBB wins every test but one, whose evidence is holed (the old 'gap').
const rulingsFor = (ticker) => ticker === 'AAA'
  ? [['bull', 'whole'], ['bull', 'whole'], ['bull', 'whole'], ['bull', 'whole']]
  : [['bull', 'whole'], ['bull', 'whole'], ['bull', 'holed'], ['bull', 'whole']]
const overallFor = (ticker) => ticker === 'BBB' ? 'bear' : 'bull'
const calls = []
const prompts = {}
const agent = async (prompt, opts) => {
  const [seat, rest] = opts.label.split(':'); const ticker = rest.split('@')[0]
  calls.push(`${seat}:${ticker}`)
  prompts[`${seat}:${ticker}`] = prompt
  const asOf = '2026-02-02'
  if (seat === 'bull' || seat === 'bear') return { ticker, as_of: asOf, tests: cases() }
  if (seat === 'ruler') return { ticker, as_of: asOf, tests: Object.fromEntries(T.map((t, i) => [t, { winner: rulingsFor(ticker)[i][0], completeness: rulingsFor(ticker)[i][1], why: 'w'.repeat(40), cite: 'Q1' }])), overall: { ruling: overallFor(ticker), why: 'o'.repeat(40) }, struck: [] }
  if (seat === 'editor') return { ticker, as_of: asOf, tests: Object.fromEntries(T.map((t) => [t, { bull: 'b'.repeat(200), bear: 'c'.repeat(200), ruling_stands: true }])), edit_log: [] }
  if (seat === 'verdict') return { ticker, as_of: asOf, thesis: 't'.repeat(200), bear_case: { finding: 'f'.repeat(40), cite: 'Q1', decisive: false, ruling: 'r'.repeat(40) }, shortlist: true, p_outperform: 0.66, citations: ['Q1'] }
  throw new Error('unknown seat ' + seat)
}
const parallel = (fns) => Promise.all(fns.map((f) => f()))
const pipeline = async (items, ...stages) => {
  const out = []
  for (const it of items) { let v = it; for (const s of stages) v = await s(v, it); out.push(v) }
  return out
}
const run = async (args, source = src) => {
  calls.length = 0
  const fn = new Function('args', 'agent', 'parallel', 'pipeline', 'log', 'return (async () => {' + source + '})()')
  const res = await fn(args, agent, parallel, pipeline, () => {})
  return { res, calls: [...calls] }
}
const fail = async (args, source) => { try { await run(args, source); return 'NO THROW' } catch (e) { return e.message } }
const names = [{ ticker: 'AAA', docIds: 'P1 Q1' }, { ticker: 'BBB', docIds: 'P1 Q1' }]
const base = { asOf: '2026-02-02', root: '/r' }
const out = {}
const srcA = src.replace("const PASS_RULE = 'overall'", "const PASS_RULE = 'A'")
let r = await run({ ...base, names }, srcA)
out.full = Object.fromEntries(r.res.summary.map((x) => [x.slug, [x.ruler_pass, x.shortlist, x.p_judge]]))
out.full_calls = r.calls
r = await run({ ...base, names: [...names, { ticker: 'CCC', docIds: 'P1 Q1' }], layer: 'middle' })
out.overall_rule = Object.fromEntries(r.res.summary.map((x) => [x.slug, x.ruler_pass]))
r = await run({ ...base, names, layer: 'middle' }, srcA)
out.middle_calls = r.calls
const stored = r.res.summary.map((x) => ({ ticker: x.slug, docIds: 'P1 Q1', casesPath: `/c/${x.slug}.json`, rulings: x.rulings, overall: x.overall }))
r = await run({ ...base, names: stored, layer: 'verdict' })
out.verdict_calls = r.calls
out.verdict_record_carries_path = r.res.summary.every((x) => x.casesPath && !x.cases)
// the editor's checked cases are what the ranker reads; the record must keep them
out.verdict_record_keeps_edited_cases = r.res.summary.every((x) => x.edited_cases && x.edited_cases.demand_case.bull === 'b'.repeat(200))
r = await run({ ...base, names: stored, layer: 'editor' })
out.editor_calls = r.calls
out.editor_record = r.res.summary.every((x) => x.edited_cases && x.edited_cases.demand_case.bear === 'c'.repeat(200) && !('shortlist' in x))
r = await run({ ...base, names, layer: 'middle' }, src.replace("const PASS_RULE = 'overall'", "const PASS_RULE = 'B'"))
out.rule_b_passes_one_gap = r.res.summary.find((x) => x.slug === 'BBB').ruler_pass
out.verdict_without_cases = await fail({ ...base, names, layer: 'verdict' })
out.blind_guard = await fail({ ...base, names: [{ ticker: 'AAA', docIds: 'P1', beat: true }] })
out.fable_on_a_rewind_date = await fail({ ...base, names }, src.replace("const VERDICT_MODEL = 'claude-fable-5'", "const VERDICT_MODEL = 'claude-fable-5-1'"))
out.alias_refused = await fail({ ...base, names }, src.replace("const SONNET = 'claude-sonnet-5'", "const SONNET = 'sonnet'"))
// Unit 11j: layer decide reuses the editor's checked cases and runs the verdict alone;
// with the rulings withheld the verdict prompt carries no ruling of any kind.
const editedTests = Object.fromEntries(T.map((t) => [t, { bull: 'b'.repeat(200), bear: 'c'.repeat(200), ruling_stands: true }]))
const decideNames = stored.map((n) => ({ ...n, edited: editedTests }))
const srcW = readFileSync(process.argv[3], 'utf8').replace('export const meta', 'const meta')
for (const [key, source] of [['decide_with', src], ['decide_without', srcW]]) {
  r = await run({ ...base, names: decideNames, layer: 'decide' }, source)
  const p = prompts['verdict:AAA']
  out[key] = { calls: r.calls, shortlist: r.res.summary.map((x) => x.shortlist),
               rulings_block: p.includes('===== RULINGS ====='), ruling_stands: p.includes('ruling_stands'),
               four_rulings: p.includes('the four rulings'), cases: p.includes('b'.repeat(200)) }
}
out.decide_without_edited = await fail({ ...base, names: stored, layer: 'decide' })
// a live date names its dossier directory; the default stays rewind-<asOf>
const dirs = {}
const agentSpy = async () => {}
const capture = (dir) => run({ ...base, names, layer: 'middle', ...(dir ? { dossierDir: dir } : {}) })
for (const [k, d] of [['default', null], ['live', '2026-10-07']]) {
  const r = await capture(d)
  dirs[k] = Object.values(prompts).some((p) => p.includes(`/dossiers/${d || 'rewind-2026-02-02'}/AAA.md`))
}
out.dossier_dirs = dirs
console.log(JSON.stringify(out))
