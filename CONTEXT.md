# Context: what this project is, how it got here, and how to carry on

Written on 14 Nov 2026 so that someone who clones this repository, or an AI assistant working in it, starts with what the people who built it knew. [README.md](README.md) says what the thing does and how to set it up. This file says why, what was decided, what was learned the hard way, and what is open.

## What it is for

An entry for **AEM Guides Garage Week, Winter 2026**: idea 5 on the team's idea page, "AI Link, Reference and Key Healer". The idea text:

> When Guides detects a broken link, conref, keyref or key definition, AI uses the topic context and repository relationships to identify the most likely intended target. The author compares the candidates and approves the repair.
> Key capabilities: cover links, conrefs, keyrefs and key definitions; rank likely replacement targets using semantic context; explain why each target may be correct; preview affected outputs and dependent content before applying the fix.

Dates: ideas finalised 17 Nov 2026; garage week 30 Nov to 4 Dec 2026, in person; presentation and demo 10 Dec 2026. Teams of at most four.

Judging criteria, in the organisers' words: agentic workflow (task decomposition, degree of autonomy), agent orchestration for multi-agent solutions, evals and error handling, diversity of samples (it must not work for one scenario only), release readiness, a polished demo.

## Decisions, with dates

| When | Decision | Why |
|---|---|---|
| 13 Nov 2026 | Build idea 5. Drop the "Conflicting facts" rule that was prototyped first; another team has that idea. Its code is removed from the branches. | One idea, done properly |
| 13 Nov | The agent runs through the `claude` command line tool by default, and through the Claude API with `--backend sdk` | No key needed for the default; the owner's own key for the API |
| 14 Nov | The repair must be reachable from the editor's Health check panel, not only from a script | The author works there |
| 14 Nov | A planner agent above finder and reviewer agents, instead of a fixed pipeline only | The criteria ask for orchestration and autonomy. See "What the measurement says" below before claiming more |
| 14 Nov | **The agent never writes to the repository by itself.** It proposes; a person presses "Fix all", "Apply to all N" or "Replace link" | A wrong conref silently publishes wrong content |
| 14 Nov | **Repair or ask is decided by comparing text**, not by the model's confidence: word for word the same text is repaired, any change is a question | Three runs disagreed on three targets before; after it, none |
| 14 Nov | **The agent does not start by itself when someone renames an id or key.** It runs from a Health check only | The owner decided against it ("ye to nhi karenge"). Do not build or propose a rename-time trigger |
| 14 Nov | The "Fix all" button keeps the product's plain blue style; only the AI entry point looks like the product's AI Assistant button | The owner asked for it |
| 14 Nov | Repairs in topics are written as the editor's own Track Changes marks | The owner's idea; every repair is then visible in the document and can be accepted or rejected there |
| 14 Nov | Everything shown in the editor uses the editor's own components, icons and highlight | "Editor UI se consistent honi chahiye" |
| 14 Nov | **External (web) links are out.** The rule that checked them, its repair agent, its evaluation and its documents were removed from all three code bases | The owner: not impactful enough for the idea. Do not bring it back unasked |

## How the owner wants this worked on

These came up as corrections and are worth keeping to.

- **State measured numbers, not round claims.** "A thousand links in a minute" was the wish; the check takes about two and a half minutes, and that is what the documents say.
- **Do not overstate what the AI adds.** AEM's report already shows "Used in", and Find and Replace exists. The agent saves the looking-up and the deciding, not the replacing. Of the 34 causes in the large sample, 19 are settled by version history without any AI.
- **Explain with one concrete example**, in plain words. The owner reads Hinglish most easily.
- **Only realistic author flows count** as findings: no contrived input.
- **Do not change what was not asked for.**
- **Keys and passwords never go into a file or a chat.** A key is set in the owner's own terminal. The local AEM uses the SDK's default login and is bound to `127.0.0.1` for that reason.
- **Commit when asked; never push without being asked.**

## How it is built

```
AEM Guides, Content Health job
  Broken links rule (Java)            sends the map's files, their previous versions, AEM's own list of
        |                             broken references and the files outside the map that use them
        v
  sidecar  sidecar.py --serve 8766    POST /heal-refs, /feedback, /applied; GET /progress, /memory
        |
        v
  planner agent      (refplan.py)     tools: overview, investigate, decide, apply_and_recheck, finish
     |- version history and rules     code, no model: a rename is proved from the previous version
     |- finder agents (refheal.py)    one per broken target, up to 8 at once; tools: find_files, outline,
     |                                find_elements, find_keys, previous_version
     |- reviewer                      one model call on another model, without the finder's reasoning
     |- text comparison               code: same text -> repair, changed text -> ask
     `- choice per reference          one model call when two pieces could be meant
        |
        v
  editor, Health check panel (TypeScript)
     live list of agents at work, plan, rows with repair and source, compare box with candidates
     and per-output counts, Fix all / Apply to all / Replace link, Repaired list, Track Changes marks
```

What the agent keeps between checks, in `out/` next to the sidecar (not in git):

| File | Holds |
|---|---|
| `author-answers.json` | accepted repairs, the renames learned from them, candidates passed over, kinds of source edit that did not hold |
| `agent-findings.json` | what finder and reviewer concluded, reused while the broken value, its old text and the file it lives in are unchanged |
| `last-fix-all.json` | what the last "Fix all" wrote, read by the next check |

## The product code

On a local branch `garage/fact-conflict-rule` (the name is left over from the dropped rule) in Adobe's internal repositories `starling` and `xmleditor`. Nothing was pushed. Module `core/content-health` in `starling`; folder `src/controllers/widgets/content_health_report` and three widget views in `xmleditor`.

`starling`, on top of `6e4234c29f`:

| Commit | What |
|---|---|
| `f198c0de9c`, `535a9fe192` | an external links rule and the dropped rule; both removed again later |
| `cf16b07a29` | removes the dropped rule |
| `46cfa42ef6` | Broken links rule asks a reference repair advisor |
| `e264c86fc7` | carries the planner's plan and choices |
| `1d55f0fa91` | ranked candidates, previous versions from JCR, the key definition the report misses |
| `707f9fd09b` | sends AEM's own findings and outside usage; asks the advisor also when the report is empty |
| `d9b3094336` | removes the external links rule, its checker and its advisor client |

`xmleditor`, on top of `3e4ffca619`:

| Commit | What |
|---|---|
| `5f736df1ac`, `54ff7d172a`, `c1b0c1de0c` | first rows with a suggestion; removal of the dropped rule |
| `e5a8cb6bd5`, `6a33b3898d` | repairs in the report, Fix all, the AI entry point |
| `0b3453937e` | compare box with candidates |
| `9040a03ae9` | tells the sidecar what Fix all wrote and what the author chose; forget an answer |
| `aab9966c3b` | live list of the agents at work |
| `98042962aa` | repairs as Track Changes marks; the Repaired list |
| `5c4199c21b` | per-output counts from DITAVAL filters |
| `4b3e8b0715` | removes external links from the editor; a row's "Replace link" takes its finding off the list and the counts; four "Fix all" bugs fixed (see docs/ROADMAP.md) |

## What was learned about AEM Guides

Each of these cost time. They are facts about the local AEM on 14 Nov 2026, not guesses.

1. **References are stored as `GUID-….dita#topic/id`**, not as paths. The scanner maps the names both ways.
2. **`keys="a b"` is read as one key named "a b"**, not as two names for one key as DITA defines it. The Broken links report keeps flagging the references and the map panel lists one key. Possibly a product bug; nobody has confirmed it.
3. **The Broken links report does not list a key definition whose `href` points at a renamed id.** The agent's own scan finds it, and the rule reports it when the repair is proved.
4. **Six saves at once fail about one time in four** (`profile is null`). "Fix all" saves three files at a time and tries four times.
5. **AEM indexes a saved file later.** A check started at once reports the saved references as broken. "Fix all" waits 30 seconds.
6. **Key references are forgotten slowly.** After keys were renamed back in the map, the report listed the 198 references to them for more than ten minutes, then dropped them by itself. The agent therefore waits 30 minutes before it concludes that a repair "did not hold".
7. **A map's key space is rebuilt when the map is saved through the Guides asset API**, not when it is overwritten by an upload. The loader saves the map once for that reason.
8. **The Guides far must be installed after the SDK's first start.** Before it, the repository breaks.
9. **Feature flag overrides need `dxml.publishing.local.dev.mode=true`.**
10. **Build with the `aemaacs` profile**, or the bundle stays "Installed".
11. **The editor's highlight holds one element at a time.** Marking every repair in a topic at once is done through Track Changes marks instead: `<?tcx-delete content="…" reviewer reviewid time?>` and `<?tcx-insert-start …?>…<?tcx-insert-end?>`.
12. **Output presets come from `/bin/guides/presets?mapPath=…&type=PATH`** (`localPresets`, `globalPresets`), each with `ditaValType`, `ditaValPathList`, `cpName`. Reading the map's `jcr:content/presets` node returns nothing for the default presets.
14. **A repaired file that is open in a tab keeps showing its old content**, and saving that tab undoes the repair. The repair closes the tab, as the editor's own Find and Replace in files does, and leaves a file with unsaved edits alone.
15. **Uploading a new asset to `folder/.createasset.html` fails** (the asset would be named `folder//file`); it only works when the asset exists. The loader posts to `folder.createasset.html` for files at the top.
16. **Repeated "Fix all" and reset on one AEM changes what version history proves.** A "Fix all" that put an id back leaves a version in which the old id carries the new text. The loader deletes the sample's folders before loading.
13. **A report shown after a page reload is the stored one**, older than any repair made since. The panel now leaves out findings whose reference was repaired after the report started.

## What the measurement says

Read the "Measured" table and the limits in the README. The short version, to keep answers honest:

- On the 1,251-reference sample the planner made **no wrong repair in three runs**, with the same split every time: 710 repaired, 432 asked, 109 gone.
- **The fixed pipeline without the planner was just as accurate and about twice as fast** on that sample. What the planner adds is the plan with reasons, the re-check on a copy, the memory, the look back at the last "Fix all", and the budget. Say that, not "more accurate".
- Ranking: 9 of 9 on nine cases the authors of this project wrote themselves.
- Real content: 15 of 15 seeded breaks in the public DITA-OT documentation, in 47 minutes before there was a budget. Not repeated since.
- Nobody has measured time saved for an author.

## State on 14 Nov 2026

- Tests: 59 here, 599 in the editor's Content Health folders, and the Java module's tests pass.
- The local AEM holds `/content/dam/large-demo` (after a "Fix all": 492 findings left), `/content/dam/large-demo-outside`, `/content/dam/ref-demo`.
- All four capabilities of the idea text have been seen working inside AEM.

## Open, in the order it would help a customer

1. **Content that was deleted** (109 references in the sample): built on 14 Nov 2026. `wayout.py` works out the possible ways (put it back, keep the text in the topics, remove the references), the planner suggests one, the author applies it from the compare box (`way_out.ts`). Removing is never offered for safety content. Open: the planner's suggestion is not scored by an evaluation yet (three removed pieces are too few to call it measured), and a way out that was applied is not remembered for the next check.
2. **A switch to write repairs without Track Changes marks** is missing. (Accept and Reject on the marks were tried on 14 Nov 2026 in the editor's "Tracked changes" panel: Reject put the old, broken reference back and removed the repaired one; Accept kept the repaired one. Both leave the topic with unsaved edits, as any edit does.)
3. **The second check still takes 55 seconds**, because the planner decides again. Its decisions could be remembered like the findings.
4. **Scale.** The budget of 40 targets per check is unit-tested only. References to files a build generates count as broken when content comes as plain files.
5. **Condition presets, `ditavalref`, flagging and baselines** are not evaluated for the per-output counts.
6. **The live list and the memory go through a local sidecar.** In the product they belong to the report job and the Guides AI service.
8. **The branch name** `garage/fact-conflict-rule` no longer says what is on it.
9. The small sample `ref-demo` was uploaded to AEM by hand; there is no loader for it.

## Where things are

| Need | Look at |
|---|---|
| Set up and run | [README.md](README.md), [docs/RUN.md](docs/RUN.md) |
| Give the demo | [docs/DEMO.md](docs/DEMO.md) |
| The planner and its tools | `refplan.py` |
| The ways out for removed content, and the safety rule | `wayout.py` (editor: `way_out.ts`) |
| Finder, reviewer, rules, the fixed pipeline | `refheal.py` |
| What counts as broken | `refcheck.py` |
| The sidecar and the model call | `sidecar.py`, `agentloop.py`, `claudeapi.py` |
| The numbers | `eval/`, [docs/EVAL-REFS.md](docs/EVAL-REFS.md) |
| What to build next, and the bugs found | [docs/ROADMAP.md](docs/ROADMAP.md) |
