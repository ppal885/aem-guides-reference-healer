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

Not in it: the product code. The Content Health rule (Java, repository `starling`) and the report panel (TypeScript, repository `xmleditor`) are changes on a local branch named `garage/reference-healer` in Adobe's internal repositories. [CONTEXT.md](CONTEXT.md) lists the commits. Without them the agents still run on a folder; the AEM demo needs them.

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

The first runs the 77 tests (no network, no model). The second lists the 11 broken references of the small sample. The third repairs them with the fixed pipeline and writes a report and a patch to `out-refs/`.

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

**1. Get the product code on the branch.** Clone `starling` and `xmleditor` and check out `garage/reference-healer` in both (or apply the commits listed in [CONTEXT.md](CONTEXT.md) to a current `develop`). Clone `ckeditor` next to `xmleditor`: the editor's dev page loads it even when the new editor is used.

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
| No repair found | The content is gone. The row says what it was and suggests a way out | Open the row: put the piece back (one edit), keep the text in the topics, or remove the references |

**When the content is gone, the agent does not stop at "broken".** It works out which ways out are possible and the planner suggests one, with its reason. The author chooses:

| Way out | What is written | When the planner suggests it |
|---|---|---|
| Put it back | The piece from the previous version goes back where it lived, as one edit in the shared file. References that pointed at a renamed key follow it | The removal looks like a mistake, or the piece is safety content |
| Keep the text in the topics | Each reference is replaced by the text itself, without its id | The shared piece should stay removed but the topics still need the sentence |
| Remove the references | Each reference is taken out | The text is out of date |

**Safety content** (a `note` of type warning, danger or caution, or a hazard statement): removing its references is not offered, and code refuses that decision if the planner makes it. One piece is often reached in two ways (by conref and through a key); putting it back settles the rows of both.

Seen in AEM on the sample (14 Nov 2026): the planner suggested removing the 63 references to a paragraph that said an old page "is still available until the end of the year", and putting back a caution note used by 46 references. All three ways were applied from the compare box and read back from AEM: 63 references removed, the note back in `warnings.dita` with the 28 key references following the renamed key, and the text kept in 18 topics.

When one broken target is used from several files, the report adds a "Fix at the source" row: one edit where the target lives (give a renamed key its old name back as a second name, or put an id back) instead of one edit per file.

## How it works: a planner agent with agents working for it

The Broken links rule hands the whole map to a **planner agent**. It does not follow a fixed order; it decides what to do through five tools:

| Tool | What it does |
|---|---|
| `overview` | The broken references grouped by what they point at, with any repair that code already proved from the file's version history |
| `investigate` | Hands groups without a repair to **finder agents** (search files, read outlines, search elements and keys, read the previous version). A **reviewer agent** checks each answer without seeing the finder's reasoning |
| `decide` | Per group: repair the references, repair at the source with one edit, ask the author, or leave it broken. For content that is gone: suggest putting it back, keeping the text in the topics, or removing the references. With its reason |
| `apply_and_recheck` | Applies its decisions to a copy of the files in memory and scans again. What is still broken, or newly broken by its own edits, comes back as the next round |
| `finish` | A summary for the author |

What keeps it safe:

- The planner cannot write to the repository. The result is a list of edits; a person presses "Fix all" or does not.
- Code checks each decision: a repair must have passed the reviewer, an edit at the source must not break a reference that works, a finder may only name targets a tool showed it, and a conref target must be the same element type.
- If the planner fails or stops early, undecided groups get the cautious default (repair when proven, otherwise ask the author).
- The report shows what the planner did and why, in short plain steps (the "AI repair plan" button).
- **Repairs are written plainly, and each changed file gets a new version.** No Track Changes marks (decided on 15 Nov 2026): marks left 220 topics to open and accept, which is the manual work the repair was meant to save. A new version of each file, with a comment ("Health check: repaired 3 broken references"), is what the version history shows and what an author can compare with and go back to. The panel says so before and after: the confirmation reads "Confirm: change 220 files, a new version of each" and the result "Repaired 710 references in 220 files, each saved as a new version". (For a few hours on 15 Nov the repair was saved into the working copy without a version; the owner then chose versions.) What changed is also in the audit record and in the "Repaired" list. Read back from AEM after "Fix all": 710 of 710 references repaired in 220 files, no mark, each file at a new version with that comment.
- The report keeps a "Repaired (N)" list. Selecting a row opens the topic at that element with the editor's own outline around it. A report that is older than a repair no longer lists the repaired reference.
- While a check runs, the panel shows the agents at work as a list, in the same list and with the same icons as the results: one row per step, a spinner while an agent works, a tick with its answer when it is done.
- **Repair or ask is decided on a fact, not on how sure the model sounded.** For an answer of a finder agent, code compares the text the reference showed before (from the previous version) with the text at the new target. Word for word the same: repaired. Any difference: the author is asked, with both texts. Where the texts cannot be read, a second run of the finder must name the same target without doubt.
- **The reviewer runs on another model** than the finder (`REFHEAL_REVIEWER_MODEL`; by default Sonnet reviews what the default model found). Both are Claude models.
- **It remembers what its agents found.** A finding is kept (`out/agent-findings.json`) and used again while the broken value, the text behind it and the file or maps it lives in are unchanged. A check after "Fix all" then pays only for the planner.
- **It remembers what the planner decided.** A decision is kept with everything the planner saw for that broken target (value, number of references, the target and verdict of the finding, the ways out, an author's answer). While all of that is the same, the next check uses the decision again without asking the planner, and code checks it again as it does a fresh one. One changed target in a round and the planner is asked for that round. Kept for 7 days; delete `out/agent-findings.json` to start fresh.
- **It keeps an audit record.** Whatever an author applies from the panel ("Fix all", "Apply to all N", "Replace link", a candidate, a way out) is recorded per reference: when, who was signed in, file and place, what the reference was and became, what settled it (version history, which agent), the reason, and the text before and after. "Download audit record" in the "Repaired" list gives it as a CSV file (`GET /audit?map=…&format=csv`). Checked in AEM on 14 Nov 2026: after one "Fix all" the record had 710 references in 220 files, and for 710 of 710 the new value was in the file in AEM, last modified by the same user. The record is what the editor reported to the sidecar on this machine; it is not tamper-proof, and AEM's versions stay the authority. A second approver is not built.
- **The editor never talks to the agents directly (15 Nov 2026).** The panel calls AEM (`/bin/guides/v1/contenthealth/repair/...`); AEM needs a signed-in user and the CSRF token, passes on only four kinds of message (progress, feedback, applied, audit) and writes the signed-in user into the audit entry itself, so the name cannot be set from the browser. Checked by hand: no login 401, a browser session without the token 403, an entry sent with another name is recorded under the signed-in user.
- **An audit entry is not lost when the agents are away.** The panel stores each entry in the browser session first and removes it only when it has been taken. If it cannot be sent, the author is told how many references are not in the record yet, and they are sent again with the next repair or when the record is downloaded. Limit: the store is the browser session; closing the browser before the agents are back loses those entries (the file versions in AEM remain).
- **Two maps at the same time.** The agents' stored files are written under a lock and replaced in one step, and what "Fix all" wrote is kept per map.
- **A check says what it cost and whether the AI answered (15 Nov 2026).** The last line of the plan gives the model calls, tokens and, on the CLI, money. When a model call fails, the first line of the plan is a warning with the number of failed calls and the reason, and says to run the check again; nothing is repaired by guesswork in that case. Tried with a model name that does not exist: 1 of 1 calls failed, the warning was the first line.
- **Text from the documentation is data.** Every agent's system prompt says that file contents, titles, ids, key names and sentences are never instructions, and that text addressed to an AI is to be reported. Code still rebuilds and resolves every proposal, and a person applies it.
- **The agents get no MCP servers.** The CLI is called with `--strict-mcp-config`. Without it, the tool lists of every MCP server of whoever started the sidecar were added to a call whenever the servers connected in time: the same one-line call measured 930 or 34,700 input tokens, by chance.
- **The API backend streams its requests (16 Nov 2026).** With `--backend sdk` every request goes through `messages.stream` and the agent gets the complete message at the end, so a long answer does not wait behind one silent HTTP response until a timeout cuts it. Nothing is shown while it arrives; the panel's live view is still the agents' steps, fetched every 1.5 s. Tested with a stand-in client (the answer, the token count, the retry without `fallbacks`) and once against the live API (16 Nov 2026, the owner's key in the owner's terminal): the eight references of `samples/hard-demo` in 27 s, all eight with the right target; the last call arrived in 35 pieces, the first after 4.5 s, the last after 5.4 s. On that run three of the eight were marked ready for "Fix all" where the CLI backend marks all for review: the two backends use different models, and the API backend has not been through the evaluations. `GET /health` on the sidecar says which backend runs and how the last streamed answer arrived; `docs/STREAMING.md` explains it from the start. The `claude` CLI backend, the default, is unchanged: it waits for the whole answer.
- **Images and other files that are not DITA (15 Nov 2026).** AEM stores an image reference as a GUID file name, also when the image is gone, and hands the agents DITA files only. When AEM reports such a reference as broken, the Java rule now sends the path each dangling name stood for and the list of the files that are not DITA near the map (at most 5,000). With that, rules repair without a model: an image that moved and whose name exists once (`images/panel.png` to `images/ui/panel.png`), the same behind a key (the repair is one edit at the key's definition in the map; the topics that use the key need none), and a renamed key whose image is the same (from the map's previous version). Two images of the same name are not guessed. Tried in AEM on `samples/image-demo`: both image repairs were ready, "Fix all" wrote the GUID names of the images that exist.
- **A key that was never defined is not searched for (15 Nov 2026).** When the map and the maps it includes define no keys at all, now or in an earlier version, a reference to a key is not a rename: the definition is missing. A rule settles it without a model and the row says what to do: add a key definition, or include the map that holds the keys. Seen with a slice of the DITA-OT documentation (5 topics, 15 references to 10 keys that the full documentation defines in a map of its own): before, finder agents searched for each key and reported "no repair found" as if the keys had been removed; now 0 model calls and the plan lists the 10 keys. A map that defines other keys, or defined some before, still goes to the agents.
- **A duplicated id is a warning and stays one.** No id is changed, by "Fix all" or anything else: an author may have kept the same id on purpose. The Duplicate IDs finding now says where references land ("First of 3 ... the one a reference lands on", "Copy 2 of 3 ... never on this one"), and that the same id in two topics of one file is valid DITA. When a repair of a reference would point at an id that several elements of that topic carry, it is shown to review, not applied by "Fix all". Tried in AEM: after "Fix all" the three `n1` and two `intro` ids were as before and still listed. The product's own code was read from the local copy of `develop` of 12 Nov 2026; later changes there were not seen (no access to the company git from this machine on 15 Nov).
- **A topic opened from the "Repaired" list says what is still open in it.** The topic may show other references in red: the ones that are still findings. A notice says how many ("2 other references in this topic are still open. They are in the findings list, not repaired."), once per topic. And the compare box counts the references that are still in the list, not the number from the check: after one topic got its own answer it says "for all 50", not 51.
- **A save that takes a warning away asks first.** AEM Guides itself refuses to save a file when an element that another file reuses by `conref` is gone from it ("Element with id … is being referred from … It can not be deleted"). That check does not cover an element reached through a key (`conkeyref`, `keyref`) or by `xref`. For safety content (a `note` of type warning, danger or caution, or a hazard statement) the editor now closes that gap: when such an element is in the stored file and not in the text being saved, it reads the files that use the file, and the topics of a map that names the file as a key, and if any refers to the element it shows the product's own confirmation with the number of references and the topics: "Save anyway" or "Cancel". Tried in AEM on 15 Nov 2026 with a danger note used by three topics through a key: the dialog named the 3 topics; Cancel left the note in AEM; "Save anyway" saved. No model is involved. Limits: it counts references that end in the element's id, so the same id in another file that the topic also uses would be counted too; Cancel is the default button in that dialog (Enter does not remove the warning); at most 400 files are read.
- **Generating an output asks first when the map has broken references.** Pressing Generate on an output preset reads the map's last finished health check (it does not run one). If that check found broken references, the product's own confirmation says how many, in how many files, when the check ran, and how many of them this output publishes after its DITAVAL filter, with the 15 files that have the most: "Generate anyway" or "Cancel". Several presets started together get one question. A preset that does not name its map by path starts at once, as before. Tried in AEM on 15 Nov 2026 on the AEM Sites preset: "1,251 broken references in 221 files. This output publishes 1,098 of them; its filter (customer.ditaval) leaves out 153"; Cancel started nothing, "Generate anyway" started the generation. No model is involved. Limits: it trusts the last check and shows its time, it does not know whether the content changed since; a map that was never checked is generated without a question; outputs filtered by a condition preset are not evaluated; Cancel is the default button, so Enter does not publish.
- **One answer per reference where two pieces could be meant.** When a finder returns two candidates, one more model call reads the sentence around every reference and proposes the candidate that topic needs. Such a group is always for review. The author can do the same by hand: in the compare box the switch "Only in <topic>" applies the chosen candidate to the opened topic alone and leaves the other references of that target open; such an answer is not remembered as the answer for the target. Tried in AEM on 15 Nov 2026: of 51 references one topic took the second candidate, the other 50 stayed.
- **A budget.** Finder agents take the 40 broken targets with the most references per check (`REFHEAL_MAX_GROUPS`); the rest say so in their row and wait for the next check, which reuses what is already found.
- **It learns from the author.** An accepted repair is stored and used in the next check without asking. The rename behind it is stored too, so the same old target reached through another attribute (an `xref` to an element whose `conref` was answered) needs no second question. Candidates the author passed over are not proposed again. "Forget this answer" in the compare box takes an answer back.
- **It looks at what became of its repairs.** The editor tells the sidecar what "Fix all" wrote. AEM sends its own list of broken references with every check. The next plan says how many repairs are saved and resolve, which did not reach the repository, and which AEM still lists. A repair AEM still lists after 30 minutes and a second check is not proposed again; an edit at the source that did not hold is not chosen again.
- **It says what it cannot see.** AEM's reference index gives the files outside the map that point into the changed files; the plan and the compare box name them.

`refheal.py` is the same repair as a fixed pipeline without the planner (rules, finder, reviewer, checks); the sidecar runs it with `"mode": "pipeline"`.

## Measured

| What | Result | Where |
|---|---|---|
| 1,251 broken references in a 227-file map, inside AEM, planner agent | Report in 140 to 165 s: 710 repaired, 432 to review, 109 gone. "Fix all" wrote 242 edits in 188 files, none failed; the next check said "233 repairs saved and resolve" and listed the 198 references AEM had not re-indexed yet. | [docs/RUN.md](docs/RUN.md) |
| The planner three times on the same 1,251 references, scored against the known right answer (`planeval.py`; run again on 15 Nov 2026 with the data rule and `--strict-mcp-config`: the same numbers, 171 to 177 s per run) | **0 wrong repairs, 0 wrong proposals, 0 missed.** Repair or ask was **the same in all three runs**: 710 applied, 432 asked, 109 gone; 34 of 34 targets got the same decision. 129 to 169 s per run (run again on 14 Nov 2026 with the ways out). In all three runs the planner suggested the same way out for the removed pieces: put the caution note back (46 references), remove the 63 references to the time-limited notice. That is two pieces; the next row measures the suggestion on ten. Before the text rule it applied 909, 895 and 840. | `eval/refs/planner-eval.json`, `planner-eval-before-stability.json` |
| The planner's suggestion for ten removed pieces, each with the ways a writer would plausibly pick (`wayouteval.py`, 2 runs, 15 Nov 2026) | **10 of 10 in both runs**, the same suggestion both times: the four safety pieces (caution, danger, warning, hazard statement) put back; three dated notices removed; a deprecated instruction removed; a definition and the support hours put back. "Remove" for safety content: 0. About 135 s per run. The ten pieces and the expectations are made up by one person, so this shows a sensible and stable suggestion on them, not correctness on real content. | `eval/refs/wayout-eval.json` |
| A sample where the obvious new target is the wrong one: 8 broken references, each with a decoy closer in name or wording (`samples/hard-demo`, `hardeval.py`, 3 runs, 15 Nov 2026) | Finder: the right target first in **8 of 8, all 3 runs**; nothing wrong was applied. Because the finder avoided every decoy, the reviewer agent was asked alone about the decoy and the right target of each case, 3 times: it **rejected 24 of 24 decoys** and accepted 17 of 21 right targets (1 not answered). The right target it turns down is a support address that changed, where asking the author is right. Before it was shown what the broken target said before (15 Nov 2026), it rejected 20 of 24 decoys and accepted 18 of 21: it took `session-timeout` for the old `timeout` by the id alone. Eight cases, written for this; the reviewer's prompt was improved on them. | `eval/refs/hard-eval.json`, `hard-eval-reviewer-without-old-text.json` |
| Repairs shown "to review": would accepting the first candidate be right? Both samples (`revieweval.py`, 15 Nov 2026; 2 runs before and 2 after the reviewer was shown the old text) | **Right every time in all 4 runs**: large sample 432 of 432 references, ranking sample 8 of 8. Before the change the reviewer disagreed with 6 of 12 and 4 of 7 right targets; after it, with 4 and 3 of 12 on the large sample and 3 and 4 of 7 on the ranking one. | `eval/refs/review-eval.json` |
| A wrong proposal shown to review on the large sample: found, explained and fixed (`planeval.py`, 15 and 16 Nov 2026) | In 2 of 9 planner runs the 48 of 54 `xref`s to the section `storage-limits` got the old file's topic (`limits.dita#limits`) instead of the section, which had moved to another file under a new title. Never applied, only shown to review. **Cause:** not the finder (asked 8 times alone about that reference: the right target 8 of 8). When the finder also listed the old file's topic as a second candidate, the step that chooses a candidate per reference took it for 48 of the 54, because their sentence is "Limits are listed in ..." (given those two candidates directly: 48 and 6 in 3 of 3 tries). **Fix:** when the first candidate holds at least 80% of the words of what the old target said, the content moved as a whole and nothing is chosen per reference. **After the fix,** 3 planner runs: 710 applied and right, 432 asked and right, 109 gone, no wrong proposal; the ranking sample 9 of 9 twice; the sample with decoys 8 of 8 twice. Three runs cannot show that a 2-in-9 event is gone; the unit test that rebuilds the case can. The 80% is a judgement, not derived from data. In 1 of these 3 runs the planner repaired 9 proven renames by an edit at the source instead of per reference (right result, other route), so 25 of 34 targets got the same decision. **That is closed too** (16 Nov 2026): code now refuses the planner an edit at the source that would undo a rename the version history proves; an author can still choose it. 4 planner runs after that: 710, 432, 109 in each, no edit at the source, the same decision for 34 of 34 targets; ranking 9 of 9 twice; the injection probe 0 of 8. | `eval/refs/planner-eval.json`, `tests/test_refs.py` (`ContentThatMovedAsAWhole`) |
| Text addressed to an AI inside a wrong target, asking the reviewer agent to agree (`injecteval.py`, 4 cases, 2 runs, 15 Nov 2026) | steered 0 of 8 with the data rule in the prompt, 0 of 8 without it. The rule is in every prompt, but these four cases do not show that it is what holds. Reviewer only; finder and planner were not probed. | `eval/refs/inject-eval.json` |
| The demo from start to end, nothing remembered, on a copy of the large sample in AEM (16 Nov 2026) | First check 1 min 53 s: 710 ready, 432 to review, 109 gone; 89 model calls, 271,306 tokens in, 12,579 out, about $1.09 on the CLI. "Fix all" 15 s, 220 files; each of the 220 has exactly one repair version and it is the newest; 710 audit entries. The check after it: "710 repairs saved and resolve", 1 model call. "Put it back": one edit, 46 references; the check after that 45 s and 15 calls, the next one 12 s. The question before publishing: 495 broken in 210 files, 439 published by AEM Sites. | `docs/DEMO.md`, `out/usage-log.jsonl` |
| What one check of the small sample costs on the `claude` CLI (`samples/rank-demo`, 9 references, no memory, 15 Nov 2026) | 43 model calls, 116,196 input tokens (62,784 read from cache), 6,192 output, $0.68 as the CLI reports it, 118 s. Before `--strict-mcp-config`: 45 calls, 757,327 input tokens, $1.49, 147 s. Not measured on the large sample and not on the API backend. | `out/usage-log.jsonl` |
| The fixed pipeline on the same 1,251 references (`planeval.py --mode pipeline`) | 0 wrong, 0 missed. Applied 895, 949 and 895. 70 to 74 s per run. | `eval/refs/pipeline-eval.json` |
| Nine references with two plausible targets each (`rankeval.py`, 2 runs) | The right target was proposed first for **9 of 9** in both runs; none was applied without asking. With one answer per broken target it was 8 of 9: two topics shared one old target and meant different pieces. | `eval/refs/rank-eval.json`, `rank-eval-one-answer-per-target.json` |
| Two checks in a row inside AEM (348 broken references, 11 targets for finder agents) | First check 135 s. Second check **55 s**: all 11 findings reused, only the planner ran. (Before the planner's decisions were remembered; see the next row.) | [docs/RUN.md](docs/RUN.md) |
| Three checks in a row inside AEM on the unchanged sample (1,251 broken references, 34 targets), 14 Nov 2026 | First check **163 s** (the planner decided). Second **13 s** and third **11 s**: every finding and every planner decision reused, no model call; the report was the same (710 repairs, 432 to review, 109 gone). After "Fix all" (710 repairs written, 541 references left) the next check took **15 s**, again without a model call. | [docs/RUN.md](docs/RUN.md) |
| The planner on the public DITA-OT docs with 15 seeded breaks (`refeval.py --mode planner`, 319 files) | 15 of 15 right, none wrong: 12 by rewriting references, 3 key renames by one edit at the source. **It took 47 minutes**: handed over as plain files, 475 references count as broken (most point at files the build generates), in 388 groups, and each group without a repair got a finder agent. | `eval/refs/real-docs-planner-eval.json` |
| 32 references that are broken in the public DITA-OT docs (pipeline) | 14 repaired, 7 to review, 6 without a repair (27 groups) | [docs/EVAL-REFS.md](docs/EVAL-REFS.md) |
| 15 seeded breaks with a known answer (pipeline) | 15 right | [docs/EVAL-REFS.md](docs/EVAL-REFS.md) |

Read the limits before quoting these:

- **Scale is bounded, not solved.** One finder agent per broken target was 47 minutes for 388 targets. There is now a limit of 40 targets per check and findings are reused, but the limit is unit-tested only: the 388-target run was not repeated, and references to files a build generates are still counted as broken when the content comes as plain files.
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
| `audit.py` | The audit record: appends what an author applied, reads it back, writes the CSV. No model. |
| `wayout.py` | What can be done about a reference whose content is gone: put it back, keep the text, remove the references. No model. |
| `planeval.py` | Runs the planner (or with `--mode pipeline` the fixed pipeline) several times on the large sample and scores every answer against the known right one. |
| `rankeval.py` | Scores the ranking on `samples/rank-demo`: nine references with two plausible targets each. |
| `wayouteval.py` | Scores the planner's suggestion for ten removed pieces (put back, keep the text, remove). |
| `usage.py` | Counts every model call of a check: calls, failed calls, tokens, money when the backend reports it. Writes `out/usage-log.jsonl`; `GET /usage` shows it. No model. |
| `injecteval.py` | Asks the reviewer agent about wrong repairs whose target text tells an AI to agree, with and without the data rule. |
| `hardeval.py`, `samples/gen_hard.py` | The sample with decoys and its score: finder first right, nothing wrong applied, and the reviewer agent asked alone about decoys and right targets. |
| `revieweval.py` | For repairs shown to review: whether accepting the first candidate would be right, split by what the reviewer agent said. |
| `refheal.py` | Finder agent, reviewer, rules and checks for one reference, and the fixed pipeline. `python3 refheal.py <folder>` writes a report and a patch. |
| `refeval.py` | Breaks references in a copy of a repository in known ways and scores the repairs. |
| `sidecar.py` | The HTTP sidecar AEM calls (`--serve 8766`), and the one place a model is called from. |
| `agentloop.py`, `claudeapi.py` | The agent loop on the `claude` CLI (`--backend cli`) or the Claude API (`--backend sdk`). |
| `reporthtml.py` | Shared pieces of the HTML report `refheal.py` writes. |
| `samples/` | `ref-demo` (8 files, 11 broken references), `gen_large.py` (writes the 225-file sample, with content for internal readers and a DITAVAL), `gen_rank.py` (nine two-candidate cases), `load_large_demo.sh` (loads or resets the large sample in the local AEM and gives its "AEM Sites" output the DITAVAL filter), `set_output_filter.py`. |
| `eval/` | Saved inputs and answers of the evaluations. |
| `tests/` | `python3 -m unittest discover -s tests` (77 tests, no network, no model). |
| `docs/` | `RUN.md` start and demo steps, `DEMO.md` the 5-minute script, `EVAL-REFS.md` the evaluation on public documentation. |

## Product code

On local branches named `garage/reference-healer`. Nothing is pushed.

| Repository | What changed |
|---|---|
| `~/starling`, `core/content-health` | `BrokenLinkValidationRule` sends the map's files and their previous versions to `ReferenceRepairAdvisor` and attaches repairs, source fixes and the planner's plan to its findings. Findings carry `suggestedValue`, `suggestionType`, `suggestionLabel`, `suggestionSource`. It also sends AEM's own list of broken references and the files outside the map that use the changed files. The module's unit tests pass. |
| `~/xmleditor` | Report rows show the repair, who settled it (planner, finder agent, version history, rule) and "Replace link". A bar above the rows gives the counts, the "AI repair plan" and "Fix all". The compare box applies a candidate, remembers the ones passed over and can forget an earlier answer; "Fix all" reports what it wrote to the sidecar. Type-check and the 630 Content Health tests pass (and the editor's whole suite, 25,570 tests, on 15 Nov 2026). |

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
