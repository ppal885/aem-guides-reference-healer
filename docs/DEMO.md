# Demo script (about 5 minutes)

**One line:** Content Health tells you a reference is broken. This tells you what it should be, and fixes the safe ones for you.

Before the demo: start the three pieces (`RUN.md`), run `./samples/load_large_demo.sh`, and open `/content/dam/large-demo/atlas_guide.ditamap` in the editor.

**Clear what the agents remember, or there is nothing to watch.** With findings and decisions from an earlier run the first check comes back in about 15 s without one agent working. From this folder: `rm -f out/agent-findings.json out/author-answers.json out/last-fix-all.json out/audit-log.jsonl`. Then reload the editor tab: after the loader every file has a new id, and a tab that was open during it answers clicks with "Given asset id or path are invalid".

**Make the Health check panel tall before you start** (drag its top edge up to about half the window). At its default height the plan or the compare box fills it and the rows are out of sight.

Timed on 15 Nov 2026 with nothing remembered: the first check took 3 min 11 s.

## 1. The problem (30 s)

- Someone tidies up the shared content: renames a few ids and keys, rewords a note, deletes an old paragraph.
- 220 topics reuse those pieces. Nobody told them. 1,251 references are now broken.
- Today the report lists 1,251 rows. An author opens each topic and works out what the reference used to mean.

## 2. One check (3 min, start it and talk over it)

Run Health check with the preset "Broken references demo". About three minutes. While it runs the panel lists who is working, row by row: the scanner, version history, the planner, each finder agent with a spinner while it searches and a green tick with its answer when the reviewer has checked it, then the planner's decisions and its re-check on a copy. Read two or three rows aloud as they turn green, and say who is working:

- A **planner agent** got the whole job. It looks at everything that is broken and decides what to do.
- It hands the hard ones to **finder agents**, and a **reviewer agent** checks each answer.
- It applies its plan to a copy, checks again, and only then reports.

## 3. What the planner did (1.5 min)

Read the bar above the rows ("1,251 findings checked: 710 repairs ready, 432 to review, 109 without a repair"), then press "AI repair plan". The wording differs from run to run; the decisions do not. Read three of its steps aloud:

- "Decided to repair 710 references. Why: the version history proves the same content now lives under a new name, so the references follow your colleague's rename instead of undoing it." Nobody programmed that sentence; it weighed two options.
- "Decided to ask you about … references. Why: … its wording differs from what these topics showed before." It found the target and still did not apply it.
- "For 46 references whose content is gone I suggest putting the piece back. Why: this is a warning … a warning should not silently disappear." And for 63 others it suggests removing them, because the notice was time-limited.

## 3b. Compare before you accept (45 s)

Click the repair text on the "trial-resource-limits" row. A paragraph was split in two, so the agent gives two candidates (about 80% and 12%), each with what it shows now and why, the 51 files a repair changes, and per output how many of those references it publishes ("AEM Sites: publishes 46 of 51; filtered out: 5 by audience="internal"": that output leaves internal content out, so the repair does not reach it there). Turn on "Only in <topic>" and give that one topic the second candidate; then open another row of the group and pick the first for all the rest. Run the check again later: it does not ask a second time about the ones answered for all.

## 4. Fix all (1 min)

Press "Fix all", then confirm. 220 files, saved into their working copies (the editor shows their version with a star; no version is made). The 710 rows leave the list at once and the bar says the check starts again in 30 seconds (do not click in the list meanwhile, or it waits for you to press Regenerate). Its plan starts with what became of the repairs: "Since the last Fix all: N repairs saved and resolve."

What is left: the references the planner asked about and the ones with nothing to point at. Those are the ones worth an author's time.

## 4b. Content that is gone (45 s)

Open a "No repair found" row. The planner suggests a way out and says why: for the paragraph about the old settings page ("until the end of the year") it suggests removing the 63 references; for the caution note it suggests putting it back, and removing is not offered because it is safety content. Press "Put it back (1 edit)" twice: one edit in `warnings.dita`, and the rows of both ways that reach the note leave the list.

## 4c. The record (20 s)

Open "Repaired", press "Download audit record": one line per changed reference, with who accepted it, what settled it and the text before and after. Run the check again: it comes back in about 15 s, because nothing the planner saw has changed.

## 4d. Before publishing (20 s, optional)

Open the map console, press Generate on "AEM Sites". The editor asks first: how many broken references the last check found, and how many of them this output publishes after its filter. Press Cancel.

## 5. Where it stops (30 s)

The planner cannot write to the repository; it works on a copy, and a person presses "Fix all". Code checks each of its decisions. If it fails, the report still comes with the cautious default.

## If asked

- **Why are the repairs not tracked changes?** They were. 220 topics then had to be opened and accepted, which is the work this was meant to save. The audit record and the "Repaired" list say what changed.
- **Is this in the product?** It runs in a local AEM built from a branch: inside the real Content Health job, in the real report panel, with the real editor. It is a prototype, not reviewed or merged.
- **What does the planner add over a fixed pipeline?** Not accuracy on this sample: the fixed pipeline also made no wrong repair, in half the time. The planner adds the plan with reasons, the re-check on a copy, the memory of answers, and the look back at what the last "Fix all" did.
- **Why did it ask about 432?** It repairs by itself only when the text at the new target is word for word what the reference showed before. Any change of wording is a question, with both texts.
- **How accurate is it?** `planeval.py` ran the planner three times on this sample and compared all 1,251 answers each time with the known right answer: no wrong repair, no wrong proposal, nothing missed, and the same split in every run (710 repaired, 432 asked, 109 gone). The sample is generated. With two plausible targets (`rankeval.py`, nine cases) the right one was first for 9 of 9 in both runs. On the public DITA-OT docs: 32 really broken references, 14 repaired, 7 for review, 6 without a repair. See `EVAL-REFS.md`.
- **What happens when it is wrong?** Only repairs that passed every check are applied by "Fix all". Every changed file gets a version, so it can be reverted. The rest wait for an author.
- **What does it cost?** Renames proven by version history cost nothing. Finder agents run once per broken target, not once per reference: 15 times here, in parallel. The planner itself took 7 steps.
- **How do references break at all, if the editor refuses to delete a reused element?** It refuses for `conref` only. Uploads, key changes in maps, elements reached through keys or `xref`, and moved files break them; this sample breaks them by upload.
- **Is one minute for a thousand links real?** No. The first check with the planner takes about three minutes here; an unchanged map after that about 15 s; check, fix and re-check together about five. With 1,000 different broken targets it would take far longer.
