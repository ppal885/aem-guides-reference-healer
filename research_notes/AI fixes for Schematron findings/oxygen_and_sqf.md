# Oxygen XML and Schematron Quick Fix (SQF): rule-defined and AI-generated fixes

Researched 2026-11-19. Most sources are vendor-authored (Syncro Soft/Oxygen); treat capability claims as documented vendor facts, not independent evaluations.

## 1. SQF spec: operations, status, implementations, limits

### Takeaway
SQF is a Schematron extension for declaring fixes next to assert/report messages. It has 4 core operations (add, delete, replace, stringReplace) plus user-entry, call-fix, groups and parameters. It is a W3C **Community Group** draft, not a W3C standard. Oxygen and Escali are the implementations.

### Cited Findings
- The First Draft (April 2015) is from the "Quick-fix support for XML" W3C Community Group. Editors: Nico Kutscherauer and Octavian Nadolu (Oxygen). It says it is "not a W3C Standard nor is it on the W3C Standards Track" — [SQF spec draft](https://schematron-quickfix.github.io/sqf/publishing-snapshots/April2015Draft/spec/SQFSpec.html)
- Elements: `sqf:fix` (id, `use-when`, role), `sqf:add` (position after/before/first-child/last-child), `sqf:delete`, `sqf:replace`, `sqf:stringReplace` (regex over text nodes), `sqf:user-entry` (user supplies a parameter value), `sqf:call-fix` (+`sqf:with-param`), `sqf:group`, `sqf:fixes` (global fixes), `sqf:description`/`sqf:title`, `sqf:param`, `sqf:keep` — [SQF spec draft](https://schematron-quickfix.github.io/sqf/publishing-snapshots/April2015Draft/spec/SQFSpec.html)
- Limits stated in the spec:
  - Conflicts inside one fix are resolved by the first activity element.
  - Conflicts between different fixes "cannot be resolved automatically" and should produce a warning.
  - Running more than one fix on the same error at once is not permitted.
  - An XSLT-only implementation may change unrelated serialization (XML declaration, CDATA).

  [SQF spec draft](https://schematron-quickfix.github.io/sqf/publishing-snapshots/April2015Draft/spec/SQFSpec.html)
- Second Draft (8 March 2018) changes:
  - Added Generic QuickFixes.
  - Made the `sqf:fix` content model more flexible for call-fix.
  - Added a localisation concept and `@flags` on stringReplace.
  - Replaced `sqf:keep` with `sqf:copy-of`.
  - Implementations planned in Oxygen 20.0 and the Escali Oxygen Plugin 0.2.0.

  [W3C CG announcement](https://www.w3.org/community/quickfix/2018/03/08/release-second-draft-of-schematron-quickfix-specification)
- Oxygen documents the four basic operations as Add, Delete, Replace and String Replace:
  - Add with empty element content inserts the element's required content.
  - String Replace uses Java regex with `@flags`.

  [Oxygen 28.1 SQF operations](https://www.oxygenxml.com/doc/versions/28.1/ug-editor/topics/sqf-operations.html)
- Escali (data2type, Kutscherauer) is the open-source SQF engine, with a web implementation, a CLI and an Oxygen plugin. Oxygen's 2016 slides list "Schematron Quick Fixes in Other Documents" (fixing external documents) as a feature — [sqf.test.data2type.de](https://sqf.test.data2type.de); [XML Prague 2016 slides](https://archive.xmlprague.cz/2016/files/presentations/SQF.pdf); [Oxygen 2016 slides](https://mail.oxygenxml.com/events/2016/Sch-SQF.pdf)

### Inferences
- No new spec draft after 2018 was found, so the spec looks dormant and is maintained in practice by its two implementers.
- SQF is deterministic and author-defined. A fix exists only if a rule author wrote one, which is the coverage gap AI fixes would fill.

### Gaps
- No post-2018 spec activity found. Whether any non-Oxygen/Escali tools (e.g., Schxslt, Saxon-based CMSs) implement SQF was not confirmed.
- Details of the multi-document mechanism (`@doc`-style targeting) were not verified in current docs.

## 2. How Oxygen shows Schematron errors and quick fixes

### Takeaway
SQF fixes are offered on validation errors in Text and Author modes and in the Results pane. Oxygen docs that would cover preview, fix-all and post-fix revalidation for SQF were not retrievable (404 or truncated).

### Cited Findings
- SQF fixes "are displayed on validation errors" in Text and Author modes. Typical uses are inserting required elements or fixing IDs to a naming convention — [Oxygen 27.1 SQF topic](https://www.oxygenxml.com/doc/versions/27.1/ug-editor/topics/schematron-quick-fixes.html)
- Related Oxygen topics exist for "User Entry SQF Operation", "Restricting Quick Fix Operations" and "Generate Multiple Similar Quick Fixes" — [Oxygen 28.1 SQF operations](https://www.oxygenxml.com/doc/versions/28.1/ug-editor/topics/sqf-operations.html)

### Inferences
- From prior knowledge, not re-verified here: Oxygen relies on its continuous validate-as-you-type, so a fix is re-checked implicitly rather than by an explicit "re-validate" step.

### Gaps
- No source confirmed an SQF "apply to all occurrences / multiple files" batch UI, a preview diff for SQF, or explicit revalidation after an SQF fix.

## 3. Oxygen AI Positron: fixing validation/Schematron errors

### Takeaway
Positron fixes validation errors in four ways:
- **AI Positron Fix**: right-click a problem in the Results pane. Multi-select batching works in recent versions.
- **Fix Validation Problems**: an agent action on the whole document.
- **Fix-and-revalidate loop**: the agent validates its own output and feeds errors back to the LLM.
- **Rule-embedded AI**: XPath functions inside Schematron/SQF (`ai:verify-content`, `ai:transform-content`).

Changes are reviewed via diff, tracked changes or accept/reject. No accuracy figures are published.

### Cited Findings
- **Fix Validation Problems** (v4.1, Intelligent Agents category): validates the current document and suggests fixes for all issues. It is also in Web Author. Changes can be previewed before saving to disk — [AI Positron what's new](https://mail.oxygenxml.com/ai_positron/whats_new.html); [WhatTheyThink 4.1 release](https://whattheythink.com/news/122701-syncro-soft-announces-release-oxygen-ai-positron-assistant-41/)
- **AI Positron Fix**: right-click a validation problem in the Results pane. With Oxygen 26.1+ it uses RAG over the current document. Multi-select was added in a later release (5.0 per search snippet). The 8.3 release (30 June 2026) notes it again: "resolve them in a single operation" — [Positron what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html); [Oxygen Author doc](https://oxygenxml.com/doc/ug-author/topics/ai_positron.html)
- **Feedback loop**: after Positron saves content, XML validation runs automatically and problems are reported back to the LLM to self-correct. Users can prompt "Fix validation and terminology problems in the generated content before saving". The DITA Agent can validate map completeness with a custom Schematron — [Oxygen blog "Vibing with AI Positron", 1 Nov 2025](https://blog.oxygenxml.com/topics/vibing_with_ai_positron.html)
- Safeguards cited in that post:
  - All AI changes are viewable and revertible.
  - Command-line tool calls need user approval.
  - Git is recommended for history.
  - The author calls the tool "powerful and imperfect".

  [Vibing with AI Positron](https://blog.oxygenxml.com/topics/vibing_with_ai_positron.html)
- **Review UX**:
  - Preview opens the built-in diff (Text or Author mode). Proposed changes across all files can be previewed with a per-file choice, and "Reject changes" reverts all.
  - 8.2 (2026): a Desktop "Review Changes" sandbox tracks copy/move/rename. Content Fusion shows AI-modified files in the chat with an original vs updated comparison.
  - 8.4 (21 Sep 2026): AI edits merge into the open document as **tracked changes** when Track Changes is on (Desktop/Web Author 28.1, Content Fusion 9.2).

  [Positron what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html); [oxygen-user ANN](https://mailman.oxygenxml.com/hyperkitty/list/oxygen-user@oxygenxml.com/thread/M3VINE476I4HPGWABU3NKQLZYZANCW7X/)
- **Schematron tool for agents**: 8.4 (21 Sep 2026) added a `validate_with_schematron` tool that "applies existing Schematron rules or generates new ones from your requirements". It needs Oxygen 29+ and early access from support. 8.4 also added `validate_and_check_for_completeness` for DITA maps/DITA-OT projects (on by default in DITA Agent). 8.3 added development skills for XSLT, XSD, Schematron and XSpec — [Positron what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)
- **AI inside Schematron/SQF**:
  - Namespace `http://www.oxygenxml.com/ai/function`.
  - Functions: `ai:verify-content(instruction, content)` returns xs:boolean (for use in assert/report); `ai:transform-content` returns a string (for use in `sqf:replace`); `ai:invoke-action` runs a configured action.
  - Examples: shorten a shortdesc over 50 words; detect passive voice and rewrite it in active voice.
  - Response caching is on by default. A configurable request threshold triggers a confirmation dialog.

  [Oxygen blog, O. Nadolu, 30 Jun 2025](https://blog.oxygenxml.com/topics/ai_xpath_functions.html); [Markup UK 2023](https://markupuk.org/2023/webhelp/ar10s06.html); [Oxygen 2024 slides](https://www.oxygenxml.com/events/2024/XPathAIExtensionFunctions.pdf)
- **Models**: there are frequent model additions. 8.4 added Claude Sonnet 5 / Opus 5, GPT-5.6, Gemini 3.5–3.8 Flash and Grok 4.x. 8.5 (4 Nov 2026) added GPT-6.x and Claude Sonnet/Haiku 5.5 — [Positron what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)
- **Enterprise/private**:
  - Direct connections to OpenAI, Claude, Gemini, Grok, Amazon Bedrock, Azure (incl. Claude on Azure AI Foundry) or an org's private LLM.
  - Admins can manage models per connection, and team owners can block providers/models (8.5).
  - Hooks intercept AI events (8.3).
  - Max-context-window setting for Azure/Bedrock (8.4).

  [Positron add-on page](https://oxygenxml.com/addons/AI_Positron.html); [what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)
- **Cost**:
  - Positron Service plans: trial of 500k credits for 1 month; Explorer $19/mo (2M credits); Professional $49/mo (10M); Expert $99/mo (25M).
  - Enterprise direct-provider subscription is $16.50/mo billed annually.
  - 8.4 shows the percentage of credits used and the reset date.

  [Oxygen buy page](https://www.oxygenxml.com/ai_positron_service/buy.html); [Desktop buy page](https://www.oxygenxml.com/ai_positron_desktop/buy2.html); [what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)

### Inferences
- Oxygen's pattern has three parts, all relevant for AEM Guides:
  - Deterministic SQF when a rule author supplied a fix.
  - LLM fixes keyed to a specific validation problem, with RAG context and a diff/track-changes review.
  - An agent loop that re-validates output and retries.
- `ai:transform-content` in `sqf:replace` is a hybrid: the rule author scopes *where* and *what* to fix, and the LLM supplies the text. This keeps fixes anchored to a Schematron finding.

### Gaps
- No published accuracy or fix-success rate for AI Positron Fix or Fix Validation Problems.
- Exact context payload is not documented in what I read: whether the error message, rule text, schema or surrounding XML are sent.
- Whether the single-problem AI Positron Fix re-validates before showing the result is not confirmed. Only the agent save-path loop is documented.
- The full what's-new page (262k chars) was only partly read, so earlier-version details may be missing.

## 4. AI generation of Schematron rules / SQF from natural language

### Takeaway
Yes, as of 8.4 (Sep 2026), in early access. Earlier, Oxygen pushed natural-language checks evaluated at validation time (`ai:verify-content`) rather than generating rules.

### Cited Findings
- `validate_with_schematron` "generates new ones from your requirements" (Oxygen 29+, early access) — [Positron what's new](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)
- 8.3 Schematron development skill — [same](https://www.oxygenxml.com/ai_positron/whatisnew5.0.html)
- 2023 webinar "Leveraging the Power of AI and Schematron for Content Verification and Correction" — [Oxygen event](https://mail.oxygenxml.com/evs2023-8.html)

### Gaps
- No documentation on the quality of generated rules, on whether generated SQF is included, or on testing/validation of generated rules (XSpec skill hints at it but is unconfirmed).

## 5. Known limits / user complaints

### Takeaway
Little independent criticism was found. The limits on record are vendor-stated.

### Cited Findings
- Vendor-stated limits:
  - Context window means the project prompt should stay short.
  - Tool-calling LLMs are required.
  - Search depends on indexing (remote CMS resources need an option enabled), and grep works on local disk only.
  - The author advises against using AI for all writing.

  [Vibing with AI Positron](https://blog.oxygenxml.com/topics/vibing_with_ai_positron.html)
- AI XPath functions in validation incur per-request cost/latency. Hence the caching and the request-threshold confirmation — [AI XPath functions blog](https://blog.oxygenxml.com/topics/ai_xpath_functions.html)
- The SQF spec forbids running multiple fixes on one error at once and cannot auto-resolve cross-fix conflicts — [SQF spec](https://schematron-quickfix.github.io/sqf/publishing-snapshots/April2015Draft/spec/SQFSpec.html)
- An independent hands-on review exists but was not read: [I'd Rather Be Writing, first look at Positron](https://idratherbewriting.com/blog/first-look-at-oxygen-xml-positron-assistant)

### Inferences
- `ai:verify-content` in a Schematron rule makes validation nondeterministic and costly, so results can vary run to run. Caching mitigates this only for identical inputs.

### Gaps
- No forum or user complaint threads were reviewed (Oxygen forum, Reddit). No accuracy benchmarks were found.
