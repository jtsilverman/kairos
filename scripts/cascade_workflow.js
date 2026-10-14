export const meta = {
  name: 'cascade-triage',
  description: 'kairos funnel layer 1: sonnet triage seats per anonymized fact sheet. Rules out; never ranks. Two rules: TWO_NO (a no is confirmed by a second pass) or PANEL (three passes plus an opus adjudicator on every 2-1 split).',
  whenToUse: 'Layer-1 triage over one cohort. args: {asOf, packet: [{slug, sheet}]}. Build the packet with scripts/run_cascade.py <as-of>.',
  phases: [
    { title: 'Triage', detail: 'one sonnet pass per sheet, a second only where the first says no (TWO_NO); three passes per sheet (PANEL)' },
    { title: 'Adjudicate', detail: 'PANEL only: one opus seat on each 2-1 split, reading the sheet plus all three verdicts' },
  ],
}

// A single sonnet pass on an identical sheet with an identical prompt
// disagrees with itself 6.0% of the time (336 names,
// docs/stage2-triage-2026-08.md). Two rules answer that:
//
// PANEL: three passes on every sheet plus an opus adjudicator on every 2-1
// split. ~3.06 reads per name. The rule the three tuning cohorts were drawn
// under; kept so those runs stay reproducible.
//
// TWO_NO: one pass, and a NO is confirmed by a second pass before it cuts;
// the name is cut only when both say no. ~1.3 reads per name, no
// adjudicator. The asymmetry is the point: this layer rules out, a wrong cut
// loses a name for good, and a wrong keep costs three sonnet reads
// downstream. Jake, for June and live.
const RULE = 'TWO_NO'
const PASSES = 3

// The adjudicator reads a fact sheet dated to the as-of day, so it must not
// carry a cutoff later than the cohort. The bare 'opus' alias moves with the
// session; the versioned id does not. Probe-verified 2026-08-19:
// `claude-opus-4-8[1m], training cutoff January 2026`. The pin lives HERE and
// never in the agent frontmatter, because the frontmatter is what the
// registry serves stale.
const OPUS = 'claude-opus-4-8'
// The triage seat is pinned the same way. Its frontmatter says 'sonnet', which
// is an alias: on 2026-09-28 it began resolving to Sonnet 5.5 (cutoff not
// probed), so the June triage of record ran on a different model from the
// tuning cohorts. opts.model here overrides the frontmatter.
const SONNET = 'claude-sonnet-5'

const VERDICT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['yes', 'no'] },
    decisive_number: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['verdict', 'decisive_number', 'reason'],
  additionalProperties: false,
}

const packet = args?.packet ?? []
const asOf = args?.asOf
if (!asOf) throw new Error('args.asOf is required; the cohort date rides every artefact')
if (!packet.length) throw new Error('args.packet is empty; run scripts/run_cascade.py first')

// The sheet is anonymized upstream and the packet carries a slug, never a
// ticker. A seat that can name the company is judging its own familiarity
// with it: the named A/B moved 24 verdicts, 23 of them yes->no, and never
// moved a name under $2B.
const triagePrompt = (row, pass) => [
  `Fact sheet for company ${row.slug}. This is your only source. You have no tools.`,
  '',
  row.sheet,
  '',
  `Answer the question in your instructions: would you take a closer look at this stock?`,
  `Give the single number from the sheet that decided it, and one sentence of reasoning.`,
  `(independent pass ${pass}; you have no knowledge of any other pass)`,
].join('\n')

const adjudicatePrompt = (row, votes) => [
  `Fact sheet for company ${row.slug}.`,
  '',
  row.sheet,
  '',
  'Three independent triage seats read this same sheet and split 2-1:',
  '',
  ...votes.map((v, i) => [
    `PASS ${i + 1}: ${v.verdict.toUpperCase()}`,
    `  decisive number: ${v.decisive_number}`,
    `  reason: ${v.reason}`,
  ].join('\n')),
  '',
  'Rule on the record yourself. Do not count votes.',
].join('\n')

// Pipeline, not a barrier: a name whose three passes agree is settled and
// needs no adjudication, so it must not wait on the slowest sheet in the
// cohort before the next stage starts.
const triage = (row, pass) => agent(triagePrompt(row, pass), {
  label: `triage:${row.slug}:${pass}`,
  phase: 'Triage',
  agentType: 'screen-triage',
  model: SONNET,
  schema: VERDICT,
})

const settled = await pipeline(
  packet,
  async (row) => {
    if (RULE === 'TWO_NO') {
      // One pass. A yes stands; a no is only a no when a second pass agrees.
      const first = await triage(row, 1)
      if (!first) return { row, votes: [] }
      if (first.verdict === 'yes') return { row, votes: [first] }
      const second = await triage(row, 2)
      return { row, votes: second ? [first, second] : [first] }
    }
    const votes = await parallel(
      Array.from({ length: PASSES }, (_, i) => () => triage(row, i + 1))
    )
    return { row, votes: votes.filter(Boolean) }
  },
  async ({ row, votes }) => {
    if (RULE === 'TWO_NO') {
      // A dead seat must never become a silent cut: with no verdict at all
      // the name is dropped and reported, and a lone unconfirmed no is not
      // a no. The rule cuts only on two no's.
      if (!votes.length) {
        log(`${row.slug}: no verdict returned; DROPPED`)
        return { slug: row.slug, verdict: null, route: 'incomplete', votes }
      }
      if (votes[0].verdict === 'yes') {
        return { slug: row.slug, verdict: 'yes', route: 'first-pass-yes', votes }
      }
      if (votes.length < 2) {
        log(`${row.slug}: a no the second pass never confirmed; DROPPED`)
        return { slug: row.slug, verdict: null, route: 'unconfirmed-no', votes }
      }
      const confirmed = votes[1].verdict === 'no'
      return { slug: row.slug, verdict: confirmed ? 'no' : 'yes',
               route: confirmed ? 'two-no' : 'rescued', votes }
    }
    // A seat that died leaves fewer than three votes. Scoring that name off
    // two passes would quietly give it a different error bar from every
    // other name, so it is reported and dropped from the settled set.
    if (votes.length < PASSES) {
      log(`${row.slug}: only ${votes.length}/${PASSES} passes returned; DROPPED`)
      return { slug: row.slug, verdict: null, route: 'incomplete', votes }
    }
    const yes = votes.filter((v) => v.verdict === 'yes').length
    if (yes === PASSES || yes === 0) {
      return { slug: row.slug, verdict: yes === PASSES ? 'yes' : 'no', route: 'unanimous', votes }
    }
    const ruling = await agent(adjudicatePrompt(row, votes), {
      label: `adjudicate:${row.slug}`,
      phase: 'Adjudicate',
      model: OPUS,
      agentType: 'screen-adjudicator',
      schema: VERDICT,
    })
    return {
      slug: row.slug,
      verdict: ruling?.verdict ?? null,
      route: ruling ? 'adjudicated' : 'adjudicator-died',
      votes,
      ruling,
    }
  }
)

const rows = settled.filter(Boolean)
const keeps = rows.filter((r) => r.verdict === 'yes')
const splits = rows.filter((r) => r.route === 'adjudicated')
const dropped = rows.filter((r) => r.verdict === null)

const rescued = rows.filter((r) => r.route === 'rescued')
const reads = rows.reduce((n, r) => n + r.votes.length, 0) + splits.length
log(`${asOf}: rule ${RULE}, ${rows.length} sheets, ${keeps.length} kept, ${reads} reads (${(reads / (rows.length || 1)).toFixed(2)} per name)`)
if (RULE === 'TWO_NO') log(`${asOf}: ${rescued.length} names a second pass rescued from a first-pass no`)
else log(`${asOf}: ${splits.length} split 2-1`)
if (dropped.length) log(`${asOf}: ${dropped.length} names produced no verdict and are NOT in the keep list`)

return {
  asOf,
  rule: RULE,
  counts: {
    sheets: rows.length,
    unanimous: rows.filter((r) => r.route === 'unanimous').length,
    split: splits.length,
    rescued: rescued.length,
    kept: keeps.length,
    dropped: dropped.length,
    reads,
  },
  keeps: keeps.map((r) => r.slug),
  rows,
}
