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
| Bank: "Show the auditor every reference that was changed, who accepted it, and the evidence" | Each repair is a version with a comment, and a Track Changes mark with who settled it | No report of it; no second approver; "who" is the agent's name, not the person who pressed the button |
| All three: "The content is gone. What do I do now?" | "No repair found", with the old text | The agent stops where the writer's work starts |

## The plan, in the order it would help

Each item: the problem in the writer's words, what the agents would do, what it needs, and how we would know it works.

### 1. A way out when the content is gone  (all three)

*"109 of my references point at something a colleague deleted. Telling me so is not help."*

The finder already knows what the piece was and that nothing replaces it. The planner would then propose one of three ways out, with its reason, and never apply it by itself:

- **Put the piece back** where it lived, from the previous version: one edit, every reference works again. Right when the removal was a mistake.
- **Remove the references**: right when the text is out of date. The sample has one: a notice that an old settings page "is still available until the end of the year".
- **Keep the text in the topics that still need it**, as plain content: right when the shared piece was removed but some topics still depend on the sentence.

Needs: a new kind of edit in the report (an element put back, an element removed), both as Track Changes marks. Measure: on the sample's three removed pieces, does the proposed way out match what a writer picks; and it must never choose "remove" for a warning (see 2).

### 2. Safety content is never handled quietly  (equipment)

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

*"In two years someone will ask why this sentence changed."*

A downloadable record per check: each reference, what it was, what it became, the text before and after, who settled it (version history, which agent, which earlier answer), the agent's reason, **the person who accepted it** and when. And an option that a repair needs a second person: one proposes with "Apply to all", another accepts the Track Changes marks.

Needs: the editor knows the signed-in user; the sidecar gets it with the feedback. Accept and Reject on the marks must be tried first: they were not. Measure: the record of one "Fix all" against the versions AEM made.

### 7. Finish what is half done

- Condition presets, `ditavalref` and flagging in the per-output counts.
- The planner's decisions remembered like the findings, so a second check is seconds, not 55.
- The 40-target budget tried on a set with hundreds of targets.
- A switch to write repairs without Track Changes marks, for teams that do not use them.

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

Seen and not fixed:

- In a narrow panel "Replace link" is half hidden at the right edge and easy to miss.
- The live progress line comes from one sidecar for all maps: while two checks run, each panel shows the other's line.
- After "Fix all" with an edit at the source, AEM lists the key references for more than ten minutes.
