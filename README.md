# AI Link, Reference and Key Healer (garage-week prototype)

AEM Guides Garage Week, Winter 2026, wiki idea #5.

Content Health can tell an author that a reference is broken. This prototype also says what to change it to, and can make the change.

It covers references inside the repository: `href`, `conref`, `keyref` and `conkeyref` whose target file, element or key no longer exists, and the `href` of a key definition.

Links to the web are out of scope. A first version checked and repaired those too; it was taken out on 14 Nov 2026 because it added little to the idea, and the repository is simpler without it.

## Start here

| You want to | Read |
|---|---|
| Understand what this is and what is measured | this file, from "The wiki's four capabilities" down |
| Run the agent on a folder of DITA, without AEM | "Run without AEM" below (two minutes) |
| Run the full demo inside AEM Guides | "Prerequisites" and "Set up AEM" below, then [docs/RUN.md](docs/RUN.md) |
| Give the demo | [docs/DEMO.md](docs/DEMO.md) |
| Know why things are the way they are, and what is open | [CONTEXT.md](CONTEXT.md) |
| See what to build next, and the bugs found so far | [docs/ROADMAP.md](docs/ROADMAP.md) |

## What is in this repository, and what is not

In it: the repair agents (Python), the samples and their generators, the evaluations with their saved results, the tests and the documents.

Not in it: the product code. The Content Health rule (Java, repository `starling`) and the report panel (TypeScript, repository `xmleditor`) are changes on a local branch named `garage/fact-conflict-rule` in Adobe's internal repositories. [CONTEXT.md](CONTEXT.md) lists the commits. Without them the agents still run on a folder; the AEM demo needs them.

## Run without AEM

Needs Python 3.9 or newer and the `claude` command line tool, signed in. Nothing to install: the code uses the standard library only.

```bash
python3 -m unittest discover -s tests
```

```bash
python3 refcheck.py samples/ref-demo/v2
```

```bash
python3 refheal.py samples/ref-demo/v2
```

The first runs the 54 tests (no network, no model). The second lists the 11 broken references of the small sample. The third repairs them with the fixed pipeline and writes a report and a patch to `out-refs/`.

The evaluations call the model and take minutes:

```bash
python3 samples/gen_large.py samples/large-demo
```

```bash
python3 planeval.py --runs 3
```

```bash
python3 rankeval.py --runs 2
```

To use the Claude API instead of the `claude` tool: `python3 -m venv .venv && .venv/bin/pip install anthropic`, set `ANTHROPIC_API_KEY` in your own terminal (never in a file, never in a chat), and add `--backend sdk`.

## Prerequisites for the AEM demo

Everything below was set up on one Mac (Apple silicon, macOS). All of it listens on `127.0.0.1` only.

| What | Version used | Why |
|---|---|---|
| Access to Adobe's internal git and Artifactory | | to clone and build `starling`, `xmleditor` and `ckeditor` |
| AEM as a Cloud Service SDK, author quickstart | 2026.10.29251 | the local AEM. From Adobe Software Distribution; you accept its licence yourself |
| Java 21 | Zulu 21.0.13 | runs the AEM SDK |
| Java 8 | Zulu 8.0.512 | builds `starling`. Java 11 is not used |
| Maven | 3.9 | builds `starling`, with a `settings.xml` that points at the internal Artifactory |
| Node.js | 18.20 | builds and serves `xmleditor` |
| Python | 3.9 or newer | the agents |
| `claude` command line tool, signed in | | the model behind the agents (or a Claude API key, see above) |
| About 12 GB of free memory | | AEM is started with `-Xmx4g`; the editor build and Maven need the rest |

Folders the notes assume, all in the home folder: `~/aem-sdk/author` (the quickstart jar), `~/starling`, `~/xmleditor`, `~/ckeditor`, and this repository.

## Set up AEM

Do these once, in this order. Each step says what goes wrong if it is skipped.

**1. Get the product code on the branch.** Clone `starling` and `xmleditor` and check out `garage/fact-conflict-rule` in both (or apply the commits listed in [CONTEXT.md](CONTEXT.md) to a current `develop`). Clone `ckeditor` next to `xmleditor`: the editor's dev page loads it even when the new editor is used.

**2. Build Guides** with Java 8:

```bash
cd ~/starling && mvn -Paemaacs,uuid,env-aem65 -Denv=aem65 -DskipTests install
```

The `aemaacs` profile matters. Without it the bundles ask for package versions the SDK does not export, and they stay "Installed" instead of "Active".

**3. Start AEM once, empty.** Put the quickstart jar at `~/aem-sdk/author/aem-author-p4502.jar` and create `~/aem-sdk/author/start-demo.sh`:

```bash
#!/bin/zsh
cd "$(dirname "$0")"
export JAVA_HOME="<your Java 21 home>"
exec "$JAVA_HOME/bin/java" -Xmx4g -Djava.awt.headless=true \
  -Dorg.apache.felix.http.host=127.0.0.1 \
  -Dguides.contenthealth.refrepair.url=http://127.0.0.1:8766/heal-refs \
  '-Dguides.featureflag.overrides={"CONTENT_HEALTH":true,"MARKUP_EDITOR":true}' \
  -jar aem-author-p4502.jar -nointeractive -nobrowser -nofork -a 127.0.0.1 -r author,local
```

Run it and wait until `http://localhost:4502` shows the login page (several minutes the first time). The SDK's login is the default `admin` / `admin`; that is why it is bound to this machine only. Do not expose the port.

**4. Install Guides after that first start.** Copy `~/starling/all/target/*-starling-allfar.far` into `~/aem-sdk/author/crx-quickstart/install/`. Putting it there before the first start breaks the repository; start again from an empty folder if that happened.

**5. Turn the local developer mode on.** In the OSGi configuration console (`/system/console/configMgr`), open "DXML: Publish Workflow Configuration" and set `dxml.publishing.local.dev.mode` to true. The feature flag override in the start script only works with it; without it the Health check panel and the new editor do not appear.

**6. Check the bundle.** `/system/console/bundles`, search `content-health`: it must be "Active".

**7. Build and serve the editor** with Node 18:

```bash
cd ~/xmleditor && npm install
```

```bash
cd ~/xmleditor && NODE_OPTIONS=--dns-result-order=ipv4first AEM_GUIDES_URL=http://localhost:4502/ AEM_GUIDES_USERNAME=admin AEM_GUIDES_PASSWORD=admin npm run watch_aem -- --host 127.0.0.1
```

`--host 127.0.0.1` matters: by default the dev server listens on the network. The editor is then at `http://localhost:9002/`.

**8. Start the sidecar** that AEM calls for repairs:

```bash
python3 -u sidecar.py --serve 8766
```

**9. Load the sample:**

```bash
python3 samples/gen_large.py samples/large-demo
```

```bash
./samples/load_large_demo.sh
```

It uploads the 227 files in their clean state, then the clean-up that breaks 1,251 references, one topic outside the map, and a DITAVAL filter on the map's "AEM Sites" output. About three minutes.

**10. Make a Health check preset.** In the editor open `/content/dam/large-demo/atlas_guide.ditamap`, open the Health check panel from the status bar, and create a preset with the rule "Broken links". Run it. The first check takes about two and a half minutes.

To put a changed backend into the running AEM: build `content-health` (step 2 with `-pl content-health`), then upload `core/content-health/target/content-health-5.3.0-SNAPSHOT.jar` in `/system/console/bundles` with "Install/Update" and start it.

What is not written down here, because it was done by hand once: uploading the small sample `ref-demo` to `/content/dam` (the same Assets HTTP API calls as in `load_large_demo.sh`).

## The wiki's four capabilities

| Capability in the idea | Where it is |
|---|---|
| Cover links, conrefs, keyrefs and key definitions | `xref`/`href`, `conref`, `keyref`, `conkeyref`, and the `href` of a key definition, all seen repaired inside AEM. AEM's Broken links report does not list a key definition whose target id was renamed; the healer's own scan finds it and the rule reports it when the repair is proven. |
| Rank likely replacement targets using semantic context | Finder agents read the sentence around the reference, the previous version and the candidate elements, and return up to three targets with a likelihood each. Checked in code: a tool must have shown the target, and the rewritten reference must resolve. |
| Explain why each target may be correct | Every candidate carries its reason; a doubt is stated as a caveat; the planner gives a reason for each decision. |
| Preview affected outputs and dependent content before applying | Click a finding's repair: what the reference showed before it broke, what each candidate shows now, the references and files a repair changes (also files outside the map), and **per output of the map how many of those references it publishes**, read from the output preset's DITAVAL filter. Seen in AEM: "AEM Sites: publishes 42 of 48; filtered out: 6 by audience="internal" (customer.ditaval). PDF: publishes all 48 (no filter)." |

## What an author sees

In the editor's Health check panel, each broken reference comes with one of three answers:

| Answer | Meaning | What the author can do |
|---|---|---|
| Repair | Every check passed | "Replace link" on the row, or "Fix all" for all of them |
| Repair to review | A target was found, with a stated doubt | Read the doubt, then "Replace link" |
| No repair found | The content is gone; the row says why | Decide what the topic should say instead |

When one broken target is used from several files, the report adds a "Fix at the source" row: one edit where the target lives (give a renamed key its old name back as a second name, or put an id back) instead of one edit per file.

## How it works: a planner agent with agents working for it

The Broken links rule hands the whole map to a **planner agent**. It does not follow a fixed order; it decides what to do through five tools:

| Tool | What it does |
|---|---|
| `overview` | The broken references grouped by what they point at, with any repair that code already proved from the file's version history |
| `investigate` | Hands groups without a repair to **finder agents** (search files, read outlines, search elements and keys, read the previous version). A **reviewer agent** checks each answer without seeing the finder's reasoning |
| `decide` | Per group: repair the references, repair at the source with one edit, ask the author, or leave it broken. With its reason |
| `apply_and_recheck` | Applies its decisions to a copy of the files in memory and scans again. What is still broken, or newly broken by its own edits, comes back as the next round |
| `finish` | A summary for the author |

What keeps it safe:

- The planner cannot write to the repository. The result is a list of edits; a person presses "Fix all" or does not.
- Code checks each decision: a repair must have passed the reviewer, an edit at the source must not break a reference that works, a finder may only name targets a tool showed it, and a conref target must be the same element type.
- If the planner fails or stops early, undecided groups get the cautious default (repair when proven, otherwise ask the author).
- The report shows what the planner did and why, in short plain steps (the "AI repair plan" button).
- **Every repair in a topic is written as a tracked change**, in the format of the editor's own Track Changes: the old element as a deletion, the repaired one as an insertion, under the name of what settled it ("AI finder agent", "Version history"). The author sees each repair in the document and accepts or rejects it with the editor's review tools. Seen in AEM on 48 references; a check afterwards (388 findings, as expected) did not trip over the marks. Maps, and ids or key names put back, are rewritten plainly.
- The report keeps a "Repaired (N)" list. Selecting a row opens the topic at that element with the editor's own outline around it. A report that is older than a repair no longer lists the repaired reference.
- While a check runs, the panel shows the agents at work as a list, in the same list and with the same icons as the results: one row per step, a spinner while an agent works, a tick with its answer when it is done.
- **Repair or ask is decided on a fact, not on how sure the model sounded.** For an answer of a finder agent, code compares the text the reference showed before (from the previous version) with the text at the new target. Word for word the same: repaired. Any difference: the author is asked, with both texts. Where the texts cannot be read, a second run of the finder must name the same target without doubt.
- **The reviewer runs on another model** than the finder (`REFHEAL_REVIEWER_MODEL`; by default Sonnet reviews what the default model found). Both are Claude models.
- **It remembers what its agents found.** A finding is kept (`out/agent-findings.json`) and used again while the broken value, the text behind it and the file or maps it lives in are unchanged. A check after "Fix all" then pays only for the planner.
- **One answer per reference where two pieces could be meant.** When a finder returns two candidates, one more model call reads the sentence around every reference and proposes the candidate that topic needs. Such a group is always for review.
- **A budget.** Finder agents take the 40 broken targets with the most references per check (`REFHEAL_MAX_GROUPS`); the rest say so in their row and wait for the next check, which reuses what is already found.
- **It learns from the author.** An accepted repair is stored and used in the next check without asking. The rename behind it is stored too, so the same old target reached through another attribute (an `xref` to an element whose `conref` was answered) needs no second question. Candidates the author passed over are not proposed again. "Forget this answer" in the compare box takes an answer back.
- **It looks at what became of its repairs.** The editor tells the sidecar what "Fix all" wrote. AEM sends its own list of broken references with every check. The next plan says how many repairs are saved and resolve, which did not reach the repository, and which AEM still lists. A repair AEM still lists after 30 minutes and a second check is not proposed again; an edit at the source that did not hold is not chosen again.
- **It says what it cannot see.** AEM's reference index gives the files outside the map that point into the changed files; the plan and the compare box name them.

`refheal.py` is the same repair as a fixed pipeline without the planner (rules, finder, reviewer, checks); the sidecar runs it with `"mode": "pipeline"`.

## Measured

| What | Result | Where |
|---|---|---|
| 1,251 broken references in a 227-file map, inside AEM, planner agent | Report in 140 to 165 s: 710 repaired, 432 to review, 109 gone. "Fix all" wrote 242 edits in 188 files, none failed; the next check said "233 repairs saved and resolve" and listed the 198 references AEM had not re-indexed yet. | [docs/RUN.md](docs/RUN.md) |
| The planner three times on the same 1,251 references, scored against the known right answer (`planeval.py`) | **0 wrong repairs, 0 wrong proposals, 0 missed.** Repair or ask was **the same in all three runs**: 710 applied, 432 asked, 109 gone; 34 of 34 targets got the same decision. 127 to 143 s per run. Before the text rule it applied 909, 895 and 840. | `eval/refs/planner-eval.json`, `planner-eval-before-stability.json` |
| The fixed pipeline on the same 1,251 references (`planeval.py --mode pipeline`) | 0 wrong, 0 missed. Applied 895, 949 and 895. 70 to 74 s per run. | `eval/refs/pipeline-eval.json` |
| Nine references with two plausible targets each (`rankeval.py`, 2 runs) | The right target was proposed first for **9 of 9** in both runs; none was applied without asking. With one answer per broken target it was 8 of 9: two topics shared one old target and meant different pieces. | `eval/refs/rank-eval.json`, `rank-eval-one-answer-per-target.json` |
| Two checks in a row inside AEM (348 broken references, 11 targets for finder agents) | First check 135 s. Second check **55 s**: all 11 findings reused, only the planner ran. | [docs/RUN.md](docs/RUN.md) |
| The planner on the public DITA-OT docs with 15 seeded breaks (`refeval.py --mode planner`, 319 files) | 15 of 15 right, none wrong: 12 by rewriting references, 3 key renames by one edit at the source. **It took 47 minutes**: handed over as plain files, 475 references count as broken (most point at files the build generates), in 388 groups, and each group without a repair got a finder agent. | `eval/refs/real-docs-planner-eval.json` |
| 32 references that are broken in the public DITA-OT docs (pipeline) | 14 repaired, 7 to review, 6 without a repair (27 groups) | [docs/EVAL-REFS.md](docs/EVAL-REFS.md) |
| 15 seeded breaks with a known answer (pipeline) | 15 right | [docs/EVAL-REFS.md](docs/EVAL-REFS.md) |

Read the limits before quoting these:

- **Scale is bounded, not solved.** One finder agent per broken target was 47 minutes for 388 targets. There is now a limit of 40 targets per check and findings are reused, but the limit is unit-tested only: the 388-target run was not repeated, and references to files a build generates are still counted as broken when the content comes as plain files.
- **The second check still takes 55 s** in AEM, because the planner itself runs again and decides again.
- **On this sample the planner is not more accurate than the fixed pipeline, and it is about twice as slow.** Both made no wrong repair. What the planner adds is not accuracy here: the plan with reasons, the re-check on a copy, the memory, and the look back at the last "Fix all".
- **The text rule makes it stricter.** It applies 710 where it applied 840 to 909 before. The difference is content whose wording changed a little (a moved paragraph that gained the word "atlasctl", a section with a new title). Those are now questions.
- **How it repairs still varies.** In one of three runs the planner chose nine edits at the source for references it rewrote one by one in the others. What is applied and what is asked did not vary.
- **Ranking is measured on nine cases I wrote, twice.** Real content is not measured, and the choice per reference was seen to split a group only in that sample.
- **Learning that a repair "did not hold" is only unit-tested.** In AEM the references AEM still listed went away by themselves after more than ten minutes, so the 30-minute rule never fired.
- **AEM is slow to forget key references.** After keys were renamed back in the map, the Broken links report listed the 198 references to them for more than ten minutes. The panel counts them as "repaired and waiting for AEM to index the change" and does not list them as findings.
- **"Affected outputs" evaluates DITAVAL filters on an output preset, and nothing else.** A condition preset is named and not evaluated. Flagging rules, a DITAVAL referenced from inside the map (`ditavalref`), key-based conditions and baselines are not looked at. The count is of references, not of pages. The DITAVAL rule is the plain one: an element is dropped when every value of one of its condition attributes is excluded.
- The 1,251-reference sample is generated from templates. It has renamed, reworded, moved, merged, split and removed content, but real content is messier.
- Key scopes are read in a simple way: a key in a scope counts as defined under its plain and its qualified names everywhere, so a reference from outside the scope to the plain name is not flagged. The end of a conref range (`conrefend`) is checked like a conref; whether AEM's report lists it has not been tried.

## Files

| File | What it is |
|---|---|
| `refcheck.py` | Index of files, ids, keys and references; finds what does not resolve. Works on a folder or on files sent by a server (AEM's GUID file names included). |
| `refplan.py` | The planner agent, its tools and its memory of author answers. This is what AEM calls. |
| `planeval.py` | Runs the planner (or with `--mode pipeline` the fixed pipeline) several times on the large sample and scores every answer against the known right one. |
| `rankeval.py` | Scores the ranking on `samples/rank-demo`: nine references with two plausible targets each. |
| `refheal.py` | Finder agent, reviewer, rules and checks for one reference, and the fixed pipeline. `python3 refheal.py <folder>` writes a report and a patch. |
| `refeval.py` | Breaks references in a copy of a repository in known ways and scores the repairs. |
| `sidecar.py` | The HTTP sidecar AEM calls (`--serve 8766`), and the one place a model is called from. |
| `agentloop.py`, `claudeapi.py` | The agent loop on the `claude` CLI (`--backend cli`) or the Claude API (`--backend sdk`). |
| `reporthtml.py` | Shared pieces of the HTML report `refheal.py` writes. |
| `samples/` | `ref-demo` (8 files, 11 broken references), `gen_large.py` (writes the 225-file sample, with content for internal readers and a DITAVAL), `gen_rank.py` (nine two-candidate cases), `load_large_demo.sh` (loads or resets the large sample in the local AEM and gives its "AEM Sites" output the DITAVAL filter), `set_output_filter.py`. |
| `eval/` | Saved inputs and answers of the evaluations. |
| `tests/` | `python3 -m unittest discover -s tests` (54 tests, no network, no model). |
| `docs/` | `RUN.md` start and demo steps, `DEMO.md` the 5-minute script, `EVAL-REFS.md` the evaluation on public documentation. |

## Product code

On local branches named `garage/fact-conflict-rule` (the name is left over from a rule that was dropped). Nothing is pushed.

| Repository | What changed |
|---|---|
| `~/starling`, `core/content-health` | `BrokenLinkValidationRule` sends the map's files and their previous versions to `ReferenceRepairAdvisor` and attaches repairs, source fixes and the planner's plan to its findings. Findings carry `suggestedValue`, `suggestionType`, `suggestionLabel`, `suggestionSource`. It also sends AEM's own list of broken references and the files outside the map that use the changed files. The module's unit tests pass. |
| `~/xmleditor` | Report rows show the repair, who settled it (planner, finder agent, version history, rule) and "Replace link". A bar above the rows gives the counts, the "AI repair plan" and "Fix all". The compare box applies a candidate, remembers the ones passed over and can forget an earlier answer; "Fix all" reports what it wrote to the sidecar. Type-check and the 588 Content Health tests pass. |

The rules reach the agent through a local HTTP sidecar. A product version would call the Guides AI service instead.

## Known gaps

UI and UX:

- The live progress while a check runs is read by the editor straight from the local sidecar (`/progress?map=`, one per map). In the product it has to come from the report job.
- The compare box (before, candidates, affected files and outputs) is plain text with one button per candidate. A proper side-by-side view would be better.
- "Apply to all N" and "Use N for all" remove the rows at once; the author presses Regenerate at the end to confirm against the repository.
- The planner's plan is plain numbered text.
- The plan travels as one extra finding, so the issue count in the panel header is one too high.


- "Replace link" also edits a topic that is not locked, and does nothing in the old (CKEditor) editor.
- "Fix all" saves through the editor's API from the browser. AEM rejected about a quarter of the saves when six ran at once (`profile is null`); it now saves three at a time and retries. A server-side job would be the right home for this.
- After "Fix all" the report waits a fixed 30 s before checking again, because AEM indexes saved files a little later.
- **AEM Guides reads `keys="a b"` as one key named "a b"**, not as two names for one key as DITA defines it (seen 14 Nov 2026: the Broken links report keeps flagging the references and the map panel lists it as one key). So in AEM the edit at the source for a key is "rename it back", offered only when nothing uses the new name. Worth checking whether this is a product bug.
- AEM rebuilds a map's key space when the map is saved through the Guides asset API, not when it is overwritten by an upload. `load_large_demo.sh` saves the map once for that reason.
- The planner's own re-check follows the DITA rules, not AEM's. The second-name case above passed its check and failed in AEM. The real check is AEM's report after "Fix all".
- The reference healer repairs the files of one map. Files outside it that use the same target are named, not repaired.
- "Fix all" applied nine edits at the source (keys renamed back in the map). The files changed; AEM's report needed more than ten minutes to drop the references.
- The memory is one JSON file next to the sidecar, shared by everyone who uses it. A product version needs it per repository and with an owner.
- With an advisor configured the Broken links rule calls it on every check, also when AEM's report is empty.
