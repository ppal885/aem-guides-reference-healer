# Running the working demo on this Mac

Everything runs locally and listens on this machine only.

| Piece | Where | Port |
|---|---|---|
| AEM author (SDK 2026.10.29251) with Guides built from the branch | `~/aem-sdk/author` | 4502 |
| Editor dev server (xmleditor, same branch) | `~/xmleditor` | 9002 |
| Repair sidecar: `POST /heal-refs` | `sidecar.py --serve 8766` | 8766 |

## Start

Three terminal tabs, in this order:

```bash
~/aem-sdk/author/start-demo.sh
```

```bash
python3 -u sidecar.py --serve 8766    # in this repository's folder
```

```bash
cd ~/xmleditor && PATH="$HOME/.local/bin:$PATH" NODE_OPTIONS=--dns-result-order=ipv4first AEM_GUIDES_URL=http://localhost:4502/ AEM_GUIDES_USERNAME=admin AEM_GUIDES_PASSWORD=admin npm run watch_aem -- --host 127.0.0.1
```

AEM takes about two minutes; wait for `http://localhost:4502` to show the login page. The local AEM uses the SDK's default `admin` / `admin` login, which is why it is bound to this machine only.

The sidecar uses the `claude` CLI by default. To run the agent on the Claude API instead, set the key in that terminal (never in a file) and start it with `.venv/bin/python sidecar.py --serve 8766 --backend sdk`.

## Demo: broken references inside the repository (Broken links rule)

The sidecar on port 8766 serves `POST /heal-refs`. AEM is pointed at it by
`-Dguides.contenthealth.refrepair.url=http://127.0.0.1:8766/heal-refs` in `~/aem-sdk/author/start-demo.sh`.

- Sample: `samples/ref-demo/v1` (clean) and `v2` (an author renamed a reused note, a section and a key,
  and removed a reused paragraph). In AEM it is at `/content/dam/ref-demo`, already in the broken state.
- Open `router_guide.ditamap` in the editor, run Health check with "Broken links". Each of the 11 rows
  shows a repair, a repair to review, or why no repair is offered. "Replace link" applies it as an unsaved edit.

## Demo: 1,251 broken references, a planner agent, repaired in bulk

- Sample: `samples/gen_large.py` writes `samples/large-demo` (220 task topics that reuse shared files and one map
  of keys by conref, conkeyref, keyref and xref, plus one key definition that points at a section). `v2` is the
  set after a clean-up of the shared content: ids and keys renamed, pieces reworded, two notes merged into one,
  one paragraph split in two, two pieces moved to new files, two removed. 1,251 references break; they come
  from 34 ids and keys.
- Load or reset it in AEM: `./samples/load_large_demo.sh` (about two minutes). It ends up at `/content/dam/large-demo`.
- Open `atlas_guide.ditamap` in the editor, run Health check with "Broken links" (about two minutes). While it
  runs, the panel shows what the agents are doing.
- The "AI repair plan" button opens the planner's account in short steps. The line under it gives the counts.
- Click the repair text of a row to compare: what the reference showed before, the ranked candidates with what
  each shows now and why, the files and outputs a repair changes, and one button per candidate. The row with
  "trial-resource-limits" has two candidates.
- "Apply to all N" on a row answers one of the planner's questions for every reference of that target. The
  answer is remembered in `out/author-answers.json`; the next check uses it without asking.
- "Fix all" applies the ready repairs (press twice: the second press confirms), saves a version of each file,
  waits 30 s for AEM to index the saved files, and runs the check again.

Measured on this machine, 14 Nov 2026, `claude` CLI backend:

| Step | Time | Result |
|---|---|---|
| Health check with the planner, 227 files | 126 to 166 s | 1,251 broken, from 34 ids and keys |
| of which proved by code from version history | | 19 |
| of which handed to finder agents by the planner | | 15: 12 found under a new name or place, 3 removed for good |
| Kinds repaired in one run | | xref href 277, conref 515, keyref 238, conkeyref 220, key definition href 1 |
| Fix all (measured on the earlier 1,199 version of the sample) | about 15 s | 839 references in 220 files; the automatic re-check left exactly the 360 the planner had not applied |

Planner eval, three runs on the same input, every answer compared with what `gen_large.py` changed
(`python3 planeval.py --runs 3`): wrong repairs 0, wrong proposals 0, missed 0 in each run; applied by itself
909, 895, 840; asked the author 233, 247, 302; 31 of 34 targets decided the same way in all three runs.

## What had to be set up, and why

- **Java 21** for the AEM SDK (`~/.local/zulu21...`). Java 8 builds starling, Java 11 is not used.
- **Guides package** is built from the branch: `mvn -Paemaacs,uuid,env-aem65 -Denv=aem65 -DskipTests install` in `~/starling`, then `all/target/*-starling-allfar.far` goes into `crx-quickstart/install` **after** the first start. Putting it there before the first start breaks the repository.
- **Feature flags.** Content Health and the new editor are off by default locally. `start-demo.sh` turns them on with `-Dguides.featureflag.overrides={"CONTENT_HEALTH":true,"MARKUP_EDITOR":true}`; that override only works with `dxml.publishing.local.dev.mode=true` in the "DXML: Publish Workflow Configuration" OSGi config, which is set.
- **`~/ckeditor`** (BlueJay/ckeditor) next to `~/xmleditor`: the dev page loads it even when the new editor is used.
- **Dev server on 127.0.0.1.** By default it listens on the network and serves the home folder; `--host 127.0.0.1` stops that.
- **Demo content** was uploaded with the Assets HTTP API: `/content/dam/ref-demo` and `/content/dam/large-demo` (see below).

## To redeploy after a backend change

```bash
cd ~/starling/core && mvn -Paemaacs,uuid,env-aem65 -Denv=aem65 -pl content-health -am install -DskipTests
```

Then upload `content-health/target/content-health-5.3.0-SNAPSHOT.jar` in the OSGi console (`/system/console/bundles`, Install/Update, start the bundle). The `aemaacs` profile matters: without it the bundle asks for package versions the running AEM does not export and stays "Installed". Run the unit tests separately:

```bash
cd ~/starling/core && mvn -Puuid,env-aem65 -Denv=aem65 -pl content-health install -Dtest='**/contenthealth/**/*Test' -DfailIfNoTests=false -Dsurefire.failIfNoSpecifiedTests=false
```


## What the agent learns between checks (added 14 Nov 2026)

The sidecar keeps two files in `out/`:

- `author-answers.json`: accepted repairs, the renames learned from them, candidates passed over, and kinds of edit at the source that did not hold. `GET http://127.0.0.1:8766/memory` shows it. Delete the file for a clean demo.
- `last-fix-all.json`: what the last "Fix all" wrote. The next check reads it and says in the plan what became of those repairs.

To try it: run the check, press "Fix all", let the check run again. The plan then starts with "Since the last Fix all: N repairs saved and resolve." References AEM has not re-indexed are listed as "AEM reports this reference as broken, but its target exists"; after keys were renamed back in the map this took more than ten minutes to clear.


`./samples/load_large_demo.sh` also uploads one topic to `/content/dam/large-demo-outside` that reuses a warning of the map. The plan then says "1 file outside this map also points into the files that changed".

Evaluations: `python3 planeval.py` (planner), `python3 planeval.py --mode pipeline` (fixed pipeline, for comparison), `python3 rankeval.py` (ranking), `python3 refeval.py <folder> --mode planner` (seeded breaks in a real repository).
