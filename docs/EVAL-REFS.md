# Evaluation of the reference healer (wiki idea 5), 13 Nov 2026

Healer: `refheal.py` (scan, rules, finder agent, reviewer). Model backend for these runs: the local `claude` CLI. The Claude API backend runs the same loop but has not been used on these sets.

Content: the public DITA Open Toolkit documentation (github.com/dita-ot/docs, commit 1124c11): 322 DITA files, 2,338 references (1,335 keyref, 356 conkeyref, 449 href, 198 conref).

## Run 1: the references that are broken in the real repository

The scanner found 32 broken references (27 distinct problems), mostly in old release notes that point at files and keys which were later renamed or removed. A further 345 references point at files the build generates (listed in `.gitignore`) and are not counted.

| Outcome | Problems | How |
|---|---|---|
| Repair, ready to apply | 14 | 6 by a rule (no model), 8 by the agent |
| Repair, needs review | 7 | agent; held back by the reviewer, a caveat, or confidence below high |
| No repair | 6 | agent |

Check: the patch with the 14 ready repairs applies cleanly to the repository, and a fresh scan of the patched copy reports 16 broken references instead of 32.

How right the 14 are: 6 come from a rule with one possible answer; 6 rest on a rename that git history records (for example `installing-client` to `installing`, `log-files` to `logging`, `DITA_v1-3-support.dita` to `dita-v1-3-support.dita`); 2 (`languages` to `globalization-languages`, `features-in-docs` to `docs-dita-features`) were judged by title only, by the same reviewer who wrote the tool. No maintainer of that documentation has looked at them.

Four of the six "no repair" answers are content references to list items and a note that no longer exist in the renamed file. The agent found the rename and declined, because the conref would still not resolve.

## Run 2: seeded breaks with a known right answer

A copy of the repository without its git history, so the history tool is not available. 15 breaks, 3 of each kind, random seed 7. References already broken before seeding are not scored.

| Kind of break | Right | Wrong | Missed | Settled by a rule |
|---|---|---|---|---|
| File renamed | 3 | 0 | 0 | 0 |
| File moved to another folder | 3 | 0 | 0 | 3 |
| Element id renamed | 3 | 0 | 0 | 0 |
| Key renamed | 3 | 0 | 0 | 0 |
| File deleted (right answer: none) | 3 | 0 | 0 | 0 |
| Total | 15 | 0 | 0 | 3 |

Two of the 15 right answers were marked "needs review" and would not be applied without a person.

## Why 15 of 15 says less than it seems

- The seeded renames are mechanical: `x.dita` to `x-guide.dita`, an id gets `-details`, a key gets `-topic`. The new name still contains the old one, so name search finds it. A real rename such as `building-output` to `publishing` shares no word; in run 1 the agent solved those through git history, which this run did not have.
- The random pick landed mostly on release-note files.
- 15 cases, one seed, one documentation set, one run. The agent is not deterministic.

A harder seeded set (renames that share no word with the old name, without history) is the next evaluation to build.

## Not covered

- Key scopes, conref ranges (`conrefend`) and conref push are not understood by the scanner.
- Two other public sets were scanned but not evaluated: the Oxygen user guide reports 654 undefined keys and the OASIS DITA specification 26, which is the scanner not seeing how those projects define their keys, not broken content.
- Nothing here runs inside AEM. In the product the detection would come from the existing Broken links rule; only the healing would be new.
