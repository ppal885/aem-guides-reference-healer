# How CCMS and content-quality tools fix rule-based findings (with AI)

Research date: 2026-11-19. Scope: a short pass (about 10 tool calls). Many vendor pages were not fetched in full, and those are listed under Gaps.

## Does the product run Schematron or rule checks, and does it offer quick fixes?

### Takeaway
Schematron with deterministic Schematron Quick Fixes (SQF) is mature in Oxygen, which is also the editor inside several CCMSs. Paligo runs Schematron (built-in and custom) as a save gate. For Tridion Docs, Heretto, Componize, XDocs and Fluid Topics, this pass found no documentation of Schematron quick fixes.

### Cited Findings
- **Paligo:** has three validation layers: DocBook-based XML Schema (on by default), "recommended rules" shipped as a Schematron file, and uploadable custom Schematron. When several layers are enabled, a topic saves only if it passes all of them. These are documented behaviors. — [Paligo docs: Editor Settings / validation](https://docs.paligo.net/en/validation.html)
- **Oxygen:** supports Schematron Quick Fixes (SQF), which are rule-authored, deterministic fixes. — [Oxygen SQF docs](https://mail.oxygenxml.com/doc/versions/27.0/ug-developer/topics/schematron-quick-fixes.html)
- **Oxygen:** applying SQF to many files at once has been discussed on the user forum. — [Oxygen forum](https://forum.oxygenxml.com/post75657.html); [Apply all SQF](https://forum.oxygenxml.com/post36495.html)
- **Heretto:** offers a HyperSTE integration for style and inclusive language, which needs a separate HyperSTE license. — [Heretto help: HyperSTE integration](https://help.heretto.com/en/heretto-ccms/integrations/authoring-integrations/hyperste-integration)
- **Acrolinx (now Markup AI):** is a rule- and guideline-based checker with a Sidebar that shows issue cards. It is integrated in Oxygen and AEM (including AEM Guides). In AEM integration 3.1.0, suggestions cannot be auto-inserted, so users must edit the text manually. — [Markup AI support results](https://support.markup.ai/hc/en-us/articles/24053730060690-Sidebar-Release-Notes)

### Inferences
- The industry baseline is: a rule raises the finding, and a deterministic quick fix applies when one was authored. AI fills the gap where no quick fix was authored.

### Gaps
- No docs were found on Schematron support or quick fixes for Tridion Docs, Componize, Bluestream XDocs or Fluid Topics.
- The MadCap Flare Analyzer was not researched.

## Does it offer AI fixes for rule, style or terminology violations, and does it re-check the output?

### Takeaway
Oxygen AI Positron is the closest analogue to "AI fix for a Schematron finding". It generates a fix from the validation message and supports multi-select fixing as of V8.3 (2026). Heretto Etto fixes "some" DITA validation errors in a single topic on prompt. Acrolinx and Markup AI use AI to rewrite flagged sentences. None of these sources document an automatic re-validation of the AI output.

### Cited Findings
- **Oxygen AI Positron Fix (added in Oxygen 26.0, Oct 2023):**
  - Trigger: right-click a validation problem in the Results pane.
  - The fix is generated from the validation message and uses the custom Schematron messages, so no separate SQF has to be written.
  - Sources (vendor slides and reseller pages): [Oxygen AI-powered dev slides 2025](https://www.oxygenxml.com/events/2025/ai_powered_development_part_1.pdf); [ComponentSource news 2023](https://www.componentsource.com/news/2023/10/31/boost-your-xml-productivity-ai-assistant)
- **AI Positron 7.0:** the Fix action corrects invalid or non-well-formed XML through quick fix triggers. — [ComponentSource releases](https://www.componentsource.com/product/oxygen-ai-positron-assistant-enterprise/releases/2880091)
- **AI Positron V8.3 (listed 2026-06-30):**
  - The Fix action can run on multiple selected validation problems.
  - Adds the XPath functions `ai:chat()` and `ai:resolve-action()`.
  - Source is a reseller listing, which needs vendor confirmation. — [ComponentSource V8.3](https://www.componentsource.com/de/product/oxygen-ai-positron-enterprise/releases/2970751)
- **AI functions inside Schematron and SQF:**
  - `ai:verify-content(instruction, content)` lets AI act as a validation check.
  - `ai:transform-content(instruction, content)` can be used inside an SQF replace step.
  - This enables rule-defined findings with AI-generated fixes. — [Oxygen blog: AI XPath functions](https://blog.oxygenxml.com/topics/ai_xpath_functions.html); [2023 webinar slides](https://mail.oxygenxml.com/events/2023/SchematronAndOpenAIi.pdf)
- **MadCap IXIA CCMS** ships AI Positron (version 7.2), mainly promoted for finding duplicate content to reuse. Schematron fixing is not mentioned in the post. — [MadCap blog](https://madcapsoftware.com/blog/madcap-ixaccms-ai-positron)
- **Heretto Etto:**
  - Can check for DITA validation errors and fix "some" of them.
  - Trigger: a natural-language prompt on the selected content or element.
  - Works on one topic at a time. It cannot fix errors that depend on other files, and it cannot create files or links.
  - These are documented behaviors. — [Heretto help: Etto](https://help.heretto.com/heretto-ccms/create/etto-the-heretto-copilot)
- **Acrolinx / Markup AI "Get Suggestion":**
  - Produces an AI rewrite per issue card.
  - When there are several issues in one sentence, it rewrites the whole sentence. When there are several issues in a paragraph, it replaces the whole paragraph.
  - Sources: [Markup AI support](https://support.markup.ai/hc/en-us/articles/18247945921298); [Acrolinx AI launch PR](https://www.streetinsider.com/Business+Wire/Acrolinx+Launches+New+AI+Capabilities+To+Unlock+Enterprise+Content+Potential/23369874.html)
- **Markup AI for Heretto:** a sidebar shows clickable suggestions, and the writer accepts each one. Source is vendor marketing (2026). — [Markup AI Heretto](https://markup.ai/?p=3823)
- **Tridion Docs AI:** offers Smart Tagging (an NLP taxonomy) and a GenAI "Draft Companion". No validation-fix feature was found. — [RWS Tridion and AI](https://rws.com/content-management/tridion/tridion-and-ai)
- **AEM Guides (public docs):** the AI Assistant offers smart suggestions and reusable-content suggestions, scoped to the current viewport.
  - Thresholds: tag-level 0.6 and file-level 0.7 by default.
  - Data handling: "external AI tools are not used" for smart suggestions.
  - No public "Content Health" AI fix was found. — [AEM Guides smart suggestions](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/ai-assistant-aem/authoring-ai-based-smart-suggestions); [Configure AI Assistant](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-guide/cs-ig/web-editor-configs-cs/conf-smart-suggestions)

### Inferences
- Acrolinx's whole-sentence or whole-paragraph rewrite shows that fixes grouped by context are a real pattern, and that they make the diff larger.
- Re-validating the AI output against the original rule appears to be undocumented everywhere. That is a differentiation opportunity for Content Health.

### Gaps
- No source states that any product re-runs Schematron on an AI fix before offering it.
- Paligo, Componize, XDocs, Document360 (Eddy AI) and Fluid Topics: no AI-fix documentation was found in this pass.

## What is the review and apply experience (preview, diff, accept/reject, audit, version)?

### Takeaway
Fixes are offered as suggestions and a person accepts them. Etto writes suggestions as tracked changes with Accept, Reject and Revise. Positron points to Oxygen's XML-aware diff. Acrolinx uses replace on an issue card.

### Cited Findings
- **Etto:**
  - Its output is inserted as suggested changes.
  - **Accept** applies the changes and closes the window. **Reject** removes them. **Revise** removes them but keeps the prompt.
  - Unaccepted suggestions stay as suggested changes.
  - Repeating a prompt can give different results. — [Heretto help: Etto](https://help.heretto.com/heretto-ccms/create/etto-the-heretto-copilot)
- **Positron:** users "see exactly what changed" through Oxygen's XML-aware visual diff. — [Oxygen AI Positron page](https://www.oxygenxml.com/aipositron/index.html)
- **Acrolinx:**
  - Known failure modes include suggestions that failed to apply while the card vanished (since fixed).
  - Google Sheets replacements can overwrite manual edits.
  - In Oxygen, cards grey out after Get Suggestion.
  - Sources: [Sidebar release notes](https://support.markup.ai/hc/en-us/articles/24053730060690-Sidebar-Release-Notes); [Sheets overwrite](https://support.markup.ai/hc/en-us/articles/10221284651794-Why-do-replacements-from-the-Sidebar-overwrite-my-manual-edits-in-Google-Sheets)

### Inferences
- An apply step must detect stale anchors (content edited after the suggestion was made). Acrolinx's bugs show what happens otherwise.

### Gaps
- No product's audit-log or versioning treatment of accepted AI fixes was found documented.

## Governance: human-in-the-loop, data handling, cost and limits

### Takeaway
Human review is explicitly required: Heretto's docs recommend a human review all AI output. Heretto publishes token quotas. Oxygen lets enterprises bring their own LLM. Older Oxygen material cites a free tier of 250 requests per user per month, which may be outdated.

### Cited Findings
- **Etto limits and data handling:**
  - 16k input and 4,096 output tokens per request.
  - Essential plan: 600k input and 150k output tokens per customer per month. Pro plan: the same amounts per user per month.
  - Data stays in Heretto's infrastructure, is not used for training, and is not retained between sessions. Logs roll over and are deleted.
  - A human should review all AI content. — [Heretto help: Etto](https://help.heretto.com/heretto-ccms/create/etto-the-heretto-copilot)
- **Positron providers:** supports OpenAI, Claude, Gemini, Grok, Bedrock, and a private LLM instance. The Enterprise add-on connects to your own AI account. — [Oxygen AI Positron](https://www.oxygenxml.com/aipositron/index.html)
- **Positron free tier:** 250 requests per user per month, from a 2023 slide deck that may be stale. — [Oxygen 2023 slides](https://mail.oxygenxml.com/events/2023/SchematronAndOpenAIi.pdf)
- **AEM Guides smart suggestions:** no data retained beyond the session, and no external AI tools used. — [Experience League](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/ai-assistant-aem/authoring-ai-based-smart-suggestions)

### Gaps
- Acrolinx/Markup AI pricing and credit model: not found.
- Cost data for Tridion, Paligo and Document360: not found.

## Published accuracy or acceptance-rate numbers

### Takeaway
No published accuracy or acceptance-rate numbers for AI fixes of rule or validation findings were found for any product in scope.

### Cited Findings
- Heretto itself says Etto fixes only "some" validation errors and that results are non-deterministic. This is a qualitative statement with no figures. — [Heretto help: Etto](https://help.heretto.com/heretto-ccms/create/etto-the-heretto-copilot)

### Gaps
- No acceptance rates were found from Acrolinx case studies, Oxygen, or RWS. Further searching of case studies and analyst posts (DITAWriter, Content Wrangler) was not completed in this pass.
