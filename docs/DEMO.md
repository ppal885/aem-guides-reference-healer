# Demo script (about 5 minutes)

**One line:** Content Health tells you a reference is broken. This tells you what it should be, and fixes the safe ones for you.

Before the demo: start the three pieces (`RUN.md`), run `./samples/load_large_demo.sh`, and open `/content/dam/large-demo/atlas_guide.ditamap` in the editor.

## 1. The problem (30 s)

- Someone tidies up the shared content: renames a few ids and keys, rewords a note, deletes an old paragraph.
- 220 topics reuse those pieces. Nobody told them. 1,251 references are now broken.
- Today the report lists 1,251 rows. An author opens each topic and works out what the reference used to mean.

## 2. One check (2 min, start it and talk over it)

Run Health check with "Broken links". About two minutes. While it runs the panel lists who is working, row by row: the scanner, version history, the planner, each finder agent with a spinner while it searches and a green tick with its answer when the reviewer has checked it, then the planner's decisions and its re-check on a copy. Read two or three rows aloud as they turn green, and say who is working:

- A **planner agent** got the whole job. It looks at everything that is broken and decides what to do.
- It hands the hard ones to **finder agents**, and a **reviewer agent** checks each answer.
- It applies its plan to a copy, checks again, and only then reports.

## 3. What the planner did (1.5 min)

Read the bar above the rows, then open "What the planner did". Read two of its steps aloud:

- "Repair the references for 23 groups: ... I rewrite the references instead of renaming at the source, because that would undo a colleague's rename." Nobody programmed that sentence; it weighed two options.
- "Ask the author for 7 groups: ... the quota and region-lock notes were merged into one note, so every topic would publish a sentence it did not have before." It found the target and still did not apply it.
- "Leave broken: slow-operation was a note that read ...; pointing at another warning would publish the wrong text."

## 3b. Compare before you accept (45 s)

Click the repair text on the "trial-resource-limits" row. A paragraph was split in two, so the agent gives two candidates: 80% and 15%, each with what it shows now and why, the 51 files a repair changes, and per output how many of those references it publishes ("AEM Sites: publishes 42 of 48; filtered out: 6 by audience="internal"": that output leaves internal content out, so the repair does not reach it there). Pick one for all 51. Run the check again later: it does not ask a second time.

## 4. Fix all (1 min)

Press "Fix all", then confirm. About 190 files, each saved as a new version. The check runs again by itself, and its plan starts with what became of the repairs: "Since the last Fix all: N repairs saved and resolve."

What is left: the references the planner asked about and the ones with nothing to point at. Those are the ones worth an author's time.

## 4b. Content that is gone (45 s)

Open a "No repair found" row. The planner suggests a way out and says why: for the paragraph about the old settings page ("until the end of the year") it suggests removing the 63 references; for the caution note it suggests putting it back, and removing is not offered because it is safety content. Press "Put it back (1 edit)" twice: one tracked insertion in `warnings.dita`, and the rows of both ways that reach the note leave the list.

## 4c. The record (20 s)

Open "Repaired", press "Download audit record": one line per changed reference, with who accepted it, what settled it and the text before and after. Run the check again: it comes back in about 15 s, because nothing the planner saw has changed.

## 5. Where it stops (30 s)

The planner cannot write to the repository; it works on a copy, and a person presses "Fix all". Code checks each of its decisions. If it fails, the report still comes with the cautious default.

## If asked

- **Is this in the product?** It runs in a local AEM built from a branch: inside the real Content Health job, in the real report panel, with the real editor. It is a prototype, not reviewed or merged.
- **What does the planner add over a fixed pipeline?** Not accuracy on this sample: the fixed pipeline also made no wrong repair, in half the time. The planner adds the plan with reasons, the re-check on a copy, the memory of answers, and the look back at what the last "Fix all" did.
- **Why did it ask about 432?** It repairs by itself only when the text at the new target is word for word what the reference showed before. Any change of wording is a question, with both texts.
- **How accurate is it?** `planeval.py` ran the planner three times on this sample and compared all 1,251 answers each time with the known right answer: no wrong repair, no wrong proposal, nothing missed, and the same split in every run (710 repaired, 432 asked, 109 gone). The sample is generated. With two plausible targets (`rankeval.py`, nine cases) the right one was first for 8 and second for 1. On the public DITA-OT docs: 32 really broken references, 14 repaired, 7 for review, 6 without a repair. See `EVAL-REFS.md`.
- **What happens when it is wrong?** Only repairs that passed every check are applied by "Fix all". Every changed file gets a version, so it can be reverted. The rest wait for an author.
- **What does it cost?** Renames proven by version history cost nothing. Finder agents run once per broken target, not once per reference: 15 times here, in parallel. The planner itself took 7 steps.
- **Is one minute for a thousand links real?** No. The check with the planner takes about two minutes here; check, fix and re-check together about five. With 1,000 different broken targets it would take far longer.
