# What to build next, seen from the writer's desk

Written 14 Nov 2026. A plan, not a record: nothing here is built unless it says so.

The question asked was: think like a technical writer at a company such as KONE, SWIFT or JPMorgan Chase. What hurts, and how would the agents help?

**A caution first.** Nobody on this project has seen how those three companies write their documentation, or whether they use AEM Guides the way this plan assumes. The three writers below are **types** of documentation team, named after the kind of company, built from what is generally true of equipment makers, standards bodies and banks. Every "they have" below is an assumption to check with a real team before building.

## Three writers

**The equipment writer** (a lift and escalator maker). Installation and maintenance manuals for many product variants, in thirty or more languages. Safety notes are reused by conref in hundreds of topics. A missing warning is a liability, not a typo. Every changed source topic costs a translation.

**The standards writer** (a financial messaging standard). Message definitions, field rules and usage guidelines, published in dated releases that members implement against. Terms are controlled; a term is a key. A published release must not change. Readers quote section numbers.

**The bank writer** (procedures and controls in a regulated bank). Operating procedures, control descriptions, policy. Every change needs to show who made it, who approved it and why, sometimes years later. Two people must agree on a change.

## What each of them would ask of the agents today, and what they would find

| Their question | Today | Gap |
|---|---|---|
| Equipment: "A safety note was removed. Which manuals lose a warning, in which languages?" | The row says the note is gone and what it said. Per output it says how many references are published | No notion that the content is a safety note; nothing about languages; no way out offered |
| Equipment: "If I fix 220 topics, do I pay to translate 220 topics again?" | Not considered | The planner does not weigh translation cost when it chooses between rewriting references and one edit at the source |
| Standards: "Is this reference broken in the release we published in May, or only in the working copy?" | The check runs on the map as it is now | No baseline or release awareness |
| Standards: "The key for a term was renamed. Which other standards books use it?" | Files outside the map that point into the changed files are counted | Other maps are named, not repaired; keys used across maps are not followed |
| Bank: "Show the auditor every reference that was changed, who accepted it, and the evidence" | Each repair is a version with a comment, and a line in the audit record with who settled it and who accepted it | No report of it; no second approver; "who" is the agent's name, not the person who pressed the button |
| All three: "The content is gone. What do I do now?" | "No repair found", with the old text | The agent stops where the writer's work starts |

## The plan, in the order it would help

Each item: the problem in the writer's words, what the agents would do, what it needs, and how we would know it works.

### 1. A way out when the content is gone  (all three)

**Built on 14 Nov 2026** (`wayout.py`, `way_out.ts`); see the README. Scored on ten made-up pieces on 15 Nov 2026 (`wayouteval.py`): 10 of 10 in two runs. Not yet done: the same on real content, with a writer's choices.

*"109 of my references point at something a colleague deleted. Telling me so is not help."*

The finder already knows what the piece was and that nothing replaces it. The planner would then propose one of three ways out, with its reason, and never apply it by itself:

- **Put the piece back** where it lived, from the previous version: one edit, every reference works again. Right when the removal was a mistake.
- **Remove the references**: right when the text is out of date. The sample has one: a notice that an old settings page "is still available until the end of the year".
- **Keep the text in the topics that still need it**, as plain content: right when the shared piece was removed but some topics still depend on the sentence.

Needs: a new kind of edit in the report (an element put back, an element removed), both as Track Changes marks. Measure: on the sample's three removed pieces, does the proposed way out match what a writer picks; and it must never choose "remove" for a warning (see 2).

### 2. Safety content is never handled quietly  (equipment)

**Partly built on 14 Nov 2026**: safety content is recognised and "remove the references" is neither offered nor accepted for it. Built on 15 Nov 2026: a save in the editor that removes safety content which topics reach through a key or an xref asks first (`safety_gate.ts`; idea taken from Fonto, which lets an application guard a referenced node against deletion). Not built: a renamed warning with unchanged text is still repaired by "Fix all", and removed warnings are not moved to the top of the report.

*"If a warning disappears from a manual, I need to hear about it before anyone else does."*

The scanner would recognise safety content: `note` with `type` warning, danger or caution, and hazard statements. For such a target: never repaired without a person, even when the text is word for word the same; a removed one goes to the top of the report, with the outputs that lose it; "remove the references" is not offered.

Needs: a small classification in the scanner and one rule in the planner's checks. Measure: mark some of the sample's notes as warnings; zero of them may be applied by "Fix all".

### 3. Count the translation cost  (equipment)

*"Fixing it in 220 topics means 220 topics go back to translation in 30 languages."*

For each group the planner would know how many topics a repair touches and, from AEM, in how many languages those topics exist. It then prefers the one edit at the source when that avoids touching translated topics, and says so: "one edit instead of 220 topics, which exist in 12 languages".

Needs: the language copies of a topic from AEM (to find out how; not explored). Measure: the planner's choice between source and references, with and without the language count, on a sample that has language copies.

### 4. Releases and baselines  (standards)

*"Do not touch what members already implemented."*

The check would run against a baseline as well as the working copy and say which broken references exist in the published release (nothing to do but note it) and which only in the working copy (repair now). Repairs apply to the working copy only.

Needs: the rule already receives a baseline id when one is chosen; the advisor ignores it. Measure: a sample with a baseline; no proposed edit may touch a labelled version.

### 5. One term, many books  (standards)

*"The key was renamed. Twelve books use it."*

Today the agents see one map and name the files outside it. They would run over the maps that share the changed files, one after the other within the budget, reuse what they found for the first map, and report per book.

Needs: a list of maps from AEM's reference index (the rule already asks it for outside files); the findings cache already makes the second map cheap. Measure: time and correctness on two maps that share the sample's shared files.

### 6. An audit report and a second approver  (bank)

**The report is built (14 Nov 2026)**: per reference, with the person who accepted it, as a CSV download; see the README. The second approver is not built.

*"In two years someone will ask why this sentence changed."*

A downloadable record per check: each reference, what it was, what it became, the text before and after, who settled it (version history, which agent, which earlier answer), the agent's reason, **the person who accepted it** and when. And an option that a repair needs a second person: one proposes with "Apply to all", another accepts the Track Changes marks.

Needs: the editor knows the signed-in user; the sidecar gets it with the feedback. Accept and Reject on the marks work (tried 14 Nov 2026). Measure: the record of one "Fix all" against the versions AEM made.

### 7. Finish what is half done

- Condition presets, `ditavalref` and flagging in the per-output counts.
- ~~The planner's decisions remembered like the findings~~ Built on 14 Nov 2026: a second check of an unchanged map takes 11 to 13 s in AEM instead of 55, and the check after "Fix all" 15 s.
- ~~The 40-target budget tried on a set with hundreds of targets~~ Tried on 21 Nov 2026 on a customer export with 2,298 broken targets: 40 per check, most references first, and the token limit of 300,000 held (223,695 and 287,622 in two checks).
- ~~A switch to write repairs without Track Changes marks~~ Decided on 15 Nov 2026: no marks at all; the audit record, the "Repaired" list and the versions say what changed.
- ~~The panel calls the sidecar's own address~~ Built on 15 Nov 2026: it calls AEM, which checks the login and signs the audit entry.
- ~~An audit entry that cannot be sent is lost without a word~~ Built on 15 Nov 2026: kept in the browser session, said to the author, sent again.
- ~~Two maps checked together overwrite each other's stored files~~ Built on 15 Nov 2026: lock, one-step file replace, "Fix all" record per map.
- ~~A model that does not answer is not said plainly~~ Built on 15 Nov 2026: warning as the first line of the plan.
- ~~No record of tokens or cost~~ Built on 15 Nov 2026: `usage.py`, the last line of the plan, `out/usage-log.jsonl`.
- ~~Topic text reaches the model without being marked as data~~ Built on 15 Nov 2026: the data rule in every prompt; `injecteval.py` (reviewer only, 0 of 8 steered with and without the rule).
- ~~Images and keys that point at images~~ Built on 15 Nov 2026 (asset list and dangling paths from AEM, rules only). Open: an image that was renamed as well as moved goes to the finder agent, which finds it by path words only; not measured.
- ~~Duplicate ids~~ Decided on 15 Nov 2026: flagged with where references land, never renamed. A repair that lands on a duplicated id waits for review.
- Seen on 15 Nov 2026: after a key's definition is repaired in the map, AEM keeps listing the topics' references to that key until each topic is saved again. The row now says so; the panel does not save those topics.
- ~~After a repair the newest version of a file could have no comment, and reverting to the version before changed nothing~~ Fixed on 15 Nov 2026 for the repairs. Cause, measured on `samples/image-demo`: a version made in the same moment as the save races with AEM's processing of the file, and AEM then adds a second version with the same content and no comment. With no pause: the map 2 of 9 tries, the topic 5 of 7. With the version made 1.5 s after the save: the map 0 of 9, the topic 0 of 8. A run now saves all its files first, waits 1.5 s and then makes their versions; a single repair saves, waits and versions. Tried in the editor: "Fix all" and one more repair gave the topic 1.0, 1.1, 1.2 and the map 1.0, 1.1, each repair with its comment; the Version history dialog listed all of them, and "Revert to selected version" put the map back. Not fixed, and not ours: the editor's own "Save as new version" has the same race (seen once on the map: 1.3 with the comment, 1.4 without). Measured only on files with images; the large sample was not measured again.
- From the product's code (GUIDES-39579, read on 15 Nov 2026): a conref the editor inserts gets an id of its own from the open document's ids, so new conrefs do not add duplicate ids. The Duplicate IDs note says when a copy is a conref.
- ~~The reviewer agent judged by the id and the sentence alone~~ Built on 15 Nov 2026: it is shown what the broken target said before, and told to judge meaning. On `samples/hard-demo` it rejects 24 of 24 decoys (20 before). The wrong proposal seen in 2 of 9 planner runs after that was something else and is fixed (16 Nov 2026): the step that chooses a candidate per reference took the old file's topic for 48 links, by their sentence; it is now skipped when the first candidate holds the old text. The planner undoing 9 proven renames at the source in about 1 run of 6 is closed as well (16 Nov 2026): code refuses it that edit for a rename the version history proves; 4 runs after that gave the same decision for 34 of 34 targets.
- ~~References to keys that a map never defined are searched for by agents and reported as if removed~~ Built on 15 Nov 2026: a rule, no model. Open: a map that defines some keys and misses others still sends the missing ones to a finder agent, which can only say "none" (measured on 21 Nov 2026: no such case on the customer export with 2,298 broken targets, which has no key references, nor in the large sample, where every broken key was renamed; not built, since a finder can also catch a misspelt key); and nothing offers to write the missing key definitions (for links to the web the agent would have to invent the address, which it must not).
- Streaming, as of 16 Nov 2026: the API backend streams each model request and uses the final message; not tried against the live API. Not built: repairs arriving in the panel one by one while a check runs. The health check job in AEM waits for the whole answer of the agents, so that needs a change in the job and in the panel.
- Still open in the agents: search is by keyword, not by meaning, and ignores `xml:lang`; finder and reviewer read the same text; the version history rule also reads versions the repairs made; everything is measured on samples made for this project; evaluations are run by hand; the cost on the large sample and on the API backend is not measured; no retry on a rate limit; "Fix all" takes no lock on the files it saves (the AI Assistant's save does); it does leave alone a file that is open with unsaved edits, and says which.
- Where this would live in the product: detection and the list stay in the Content Health Report; the agents would run on the AI Assistant's platform (it already has whole-map tools: resolve_map, get_where_used, search_content, version history and diff, and an approved save with lock, version and Schematron gate) instead of this sidecar. Read in `src/extensions/kea` on 15 Nov 2026; not built.
- Open from the same review: author answers are shared by all maps (measured on 21 Nov 2026: all 14 stored answers name their target by a GUID, which is one file in the whole repository, so sharing them is right; only an answer about a key or a relative path could be wrong in another map, and there is none); the whole map goes to the agents in one request; when the model cannot be reached the check quietly falls back to the rules.

## Not planned, on purpose

- **Starting by itself when someone renames an id or key.** Decided against on 14 Nov 2026.
- **Links to the web.** Removed on 14 Nov 2026.
- **Applying anything without a person.** The agents propose.

## Bugs found on 14 Nov 2026 by trying patterns such teams would have

Fixed, with tests:

| Where | What went wrong | Who would hit it |
|---|---|---|
| Scanner | A `keyref` with an `href` beside it, or a `conkeyref` with a `conref`, was reported as broken when the key was undefined, although DITA then uses the fallback and the output is fine | Anyone who writes fallbacks, which careful teams do |
| Scanner | A key defined by pointing at another key was not followed, so a missing element behind it was not reported | Teams with layered key maps |
| Scanner, on a folder | `my%20topic.dita` was looked up as a file with that literal name and reported missing | Anyone with spaces in file names |
| Scanner, on a folder | A file named `.DITA` in capitals was not read, so breaks into it were missed | Old content |
| "Fix all" | A reference written as an example inside a comment or a code sample was rewritten too | API and standards documentation, which shows XML in code samples |
| "Fix all" | A tag with its attributes on several lines was skipped without a word, and its row still moved to "Repaired" | Hand-formatted XML |
| "Fix all" | An element with two broken references got one change inside another | `xref` with `keyref` and `href` |
| "Fix all" | A reference inside an element that was itself repaired kept its old value | Nested reuse |
| Report | A row's "Replace link" left the row in the list and the counts unchanged | Everyone |

Found while checking that everything built so far really works (14 Nov 2026), and fixed:

| What | Fix |
|---|---|
| A repaired topic that was open in a tab kept showing the old, broken reference; the row said "Repaired". Saving the tab would have undone the repair | The repair closes the file's tab. A file open with unsaved edits is not touched and is named in the message |
| A row's "Replace link" made an unsaved edit in the open topic, which did nothing when the topic was not locked, and still moved the row to "Repaired" | It now saves like every other repair, then opens the topic at the element |
| The "Repaired" list showed an empty line | Two rows from two page loads had the same key. A repaired row's key is now its reference |
| Resetting the sample did not finish on a clean folder | The loader posted the map to an address that only works when the map exists |
| Counts drifted after several "Fix all" and reset rounds (758 ready instead of 710) | Old versions stayed in AEM's history. The loader removes the sample's folders first |

Found in the editor's version history (15 Nov 2026), and worked around:

| What | Fix |
|---|---|
| Comparing two versions of a repaired topic showed both sides, but did not mark the repaired reference as added or deleted | The comparison comes from a library outside the editor's repository (`xmlDiff` in `@rh/jui-app`). It treats two elements as one changed element only when `href` or `data` differs, so a changed `conref`, `keyref` or `conkeyref` is not a change to it. The version history dialog now gives both documents a temporary attribute that carries those references and takes it out of the result (`controllers/dialogs/reference_change_marks.ts`). Seen in AEM: the old key text struck through in red, "Starter plan" in green. The real fix belongs in the library: add the reference attributes to its `pathAttrs` |

Found by using the panel the way a tester would, on a second copy (15 Nov 2026), and fixed:

| What | Fix |
|---|---|
| After a row's "Replace link" the topic opened somewhere else, without the outline around the repaired element | The outline is shown again once the editor has drawn the saved topic |
| "1 files are open with edits that are not saved", without saying which | "1 file is open with edits that are not saved: migration_archive_17.dita. Save or close it, then press "Fix all" again." |
| That message said to apply again, and the "Fix all" button was gone until the next check | The button stays for the repairs that were not written; seen as "Fix all (3)" |
| "Confirm: change 1 files", "Repaired 3 references in 1 files" | Singular for one |
| A row's "Replace link" did not say that the topic has other open references | It does, like a row of the "Repaired" list |

Tried and found working: Cancel during a check; "Fix all" with one topic open and unsaved (that file is left alone, the other 219 are written); the check after it (544, then 541); no row action past the edge of the list at 760 px.

Not looked at in that round: whether Cancel also stops the agents in the sidecar; changing the map during the wait; a file locked by another author.

Found in a full rehearsal on a second copy of the sample (15 Nov 2026), and fixed:

| What | Fix |
|---|---|
| "Save anyway" and "Generate anyway" were the default buttons of their questions, so Enter did the risky thing | A copy of the product's confirmation dialog with Cancel as the default (`content_health_confirmation`) |
| A topic opened from the "Repaired" list showed other references in red and it looked as if the repair had failed | A notice says how many references of that topic are still in the findings |
| After one topic got its own candidate, the compare box still said "Use 1 for all 51" and "change 51 files" | The box counts the rows that are left |

Timed in that rehearsal: "Fix all" saved 220 files in 16 s; one topic's own answer about 9 s; "Put it back" settled 46 rows in one press.

Fixed on 15 Nov 2026, the wait after "Fix all":

| What | Fix |
|---|---|
| For the 30 seconds before the next check the list still showed the repaired references as open, with "Replace link", while "Repaired (710)" listed them too, and the bar still said "710 repairs ready" | The saved repairs leave the list at once and the bar counts what is left |
| The only sign of the wait was the text on a disabled button, and the rows did nothing when pressed | The bar says "The repairs are saved. Checking again in 30 seconds, when AEM has indexed them."; the rows that are left can be used |
| After 30 seconds the check started and replaced the list, also when the author had opened the "Repaired" list or a compare box in the meantime | A check does not start under an author who used the list; the bar then says "Regenerate the report to see what is left" |
| A check the author started during the wait was followed by a second one; a map opened during the wait got the check | Neither starts now |

Fixed on 15 Nov 2026: after the sample was reset, the "Repaired" list kept in the browser stayed, and a click on one of its rows said "Given asset id or path are invalid". When the server has no report for a map, the panel now forgets the list it kept for that map. What stays: an editor tab that was open during the reset still holds files under their old ids and must be reloaded; the loader says so when it ends.

Seen first, fixed later the same day:

| What | Fix |
|---|---|
| In a narrow panel "Replace link" was half hidden at the right edge | The row now stays inside its list cell (its padding was added to a 100% width), the title and the suggestion give way first, and the summary buttons wrap. Measured in a 262 px wide list: every row's last action ends inside the list |
| The live progress came from one place for all maps, so two checks showed each other's line | AEM sends the map's path; the sidecar keeps progress per map and the panel asks for its own (`GET /progress?map=`). Seen: while one map's check ran, another map's progress stayed empty |
| After "Fix all" with an edit at the source, AEM listed the key references for more than ten minutes, as findings | AEM's speed is not ours to change. Those references are now marked as waiting: they are counted in one line ("198 more are repaired and waiting for AEM to index the change") and not listed as findings. Seen in AEM after a "Fix all" with ten edits at the source |

## What other editors do (looked up on the web, 15 Nov 2026; not tried)

| Tool | What it has | Here |
|---|---|---|
| Oxygen XML Author | Renaming or moving a file or an id updates the references at that moment; "Search references" first | Not built; decided against a trigger on rename on 14 Nov 2026 |
| Oxygen AI Positron | "Fix" from a validation message, agentic since 2026, over a whole project; AI edits as tracked changes under the AI's name; accept part of the changes per file | Similar: plan tried on a copy, Track Changes marks. Built on 15 Nov 2026: a candidate for one topic of a group ("Only in <topic>") |
| Oxygen completeness check | DITAVAL filters during validation; links from relationship tables | Per-output counts; relationship tables not read |
| Fonto | Live check for cross-references to elements that are gone; an application can stop a referenced node from being cut | The save gate for safety content |
| Heretto | Quality report before a release; a report of invalid keyrefs and conkeyrefs | Report plus repair. Built on 15 Nov 2026: generating an output asks first when the map's last check found broken references, with the count this output publishes (`publish_gate.ts`) |

Not found in that search: an editor whose AI finds the intended target of a broken reference from the version history and the text it showed before. That is "not found", not "does not exist".
