# AI Autofix Patterns for Rule-Based Findings (code, prose, structured content)

Research date: 19-Nov-2026. Each claim has a source link. Where I could only see search snippets and not the full page, the claim is marked "(snippet)".

## 1. GitHub Copilot Autofix (CodeQL): generation, context, validation, rates, limits

### Takeaway
Autofix is the clearest published design. It sends a narrow context (rule help, alert message and location, data-flow snippets with line numbers), asks for "before/after" blocks rather than diffs, and repairs the edits with fuzzy matching and a parser and type check. Offline, a fix counts only if the alert is gone, no new alert appears and tests still pass. GitHub has published speed figures but no absolute acceptance rate.

### Cited Findings
- Context sent to the model: the CodeQL query help, the alert message and location, code snippets along the data-flow path with line numbers, and each file's imports and top-level definitions. The model may only edit code that is in the prompt. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Output format: Markdown with fix instructions, "before/after" edit blocks with context lines, and a list of dependencies. Raw diffs were abandoned because the model got line numbers wrong. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Post-processing: fuzzy matching corrects indentation, semicolon and comment mismatches, then parser, name-resolution and type checks run. Edits that cannot be repaired are flagged. New dependencies are checked against the registry for existence and for malicious or vulnerable packages. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Success criteria in the offline harness: the alert is removed, no new CodeQL alerts appear, there are no syntax errors, and test outcomes are unchanged. The harness ran on more than 1,400 alerts from 63 CodeQL queries (JS/TS). The team says it tripled the success rate while cutting LLM compute 6x, but gives no absolute rate. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Suggestions are cached for reuse, and responses pass a harmful-content filter. Telemetry tracks the share of alerts with a suggestion, the share committed as-is, the share dismissed, and fix rates with and without a suggestion. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Beta results (2024): median 28 minutes to fix a PR alert with Autofix vs 1.5 hours manually (about 3x). XSS took 22 minutes vs almost 3 hours (7x) and SQLi 18 minutes vs 3.7 hours (12x). — [GitHub blog, Aug 2024](https://github.blog/news-insights/product-news/secure-code-more-than-three-times-faster-with-copilot-autofix/) (snippet); [TechTarget](https://www.techtarget.com/cybersecurity/news/366603045/GitHub-Copilot-Autofix-tackles-vulnerabilities-with-AI)
- Current docs describe two modes. (a) Copilot Autofix gives one suggested change per alert. It is on by default with CodeQL and uses no AI credits. (b) Agentic autofix explores the codebase, validates by re-running CodeQL, and opens a draft PR. It consumes AI credits and Actions minutes. Validation cannot confirm fixes for custom queries, the security-extended suite or third-party tools. Users must review the changes, and admins can disable the feature per enterprise, org or repo. — [GitHub Docs](https://docs.github.com/en/code-security/concepts/code-scanning/copilot-autofix-for-code-scanning)
- Usage metrics (Autofix usage, MTTR) appear on the Security Overview dashboard. Their accuracy was improved in Dec 2025. — [GitHub changelog, Dec 2025](https://github.blog/changelog/2025-12-16-more-accurate-copilot-autofix-usage-metrics-on-security-overview); [changelog Jun 2025](https://github.blog/changelog/2025-06-17-mean-time-to-remediate-metric-for-codeql-pull-request-alerts-now-included-on-the-security-overview-dashboard)
- A competitor (Pixee) states that GitHub has not published merge-rate data for Autofix. This is vendor marketing. — [Pixee](https://www.pixee.ai/compare/pixee-vs-github-copilot)

### Inferences
- These patterns map directly onto Schematron findings:
  - Rule help goes into the prompt: the Schematron assert text plus a human description.
  - Send only the context node, not the whole topic.
  - Ask for the replacement element, not a diff.
  - Repair the output with fuzzy anchoring.
  - Parse and DTD-validate the result.
  - Re-run the same Schematron and confirm the finding is gone and nothing new appears.
- Cache the suggestion per (rule, normalized element) to save cost.

### Gaps
- No absolute acceptance or fix rate for Autofix is published.
- Exact model and prompt are not published.

## 2. Other tools: Snyk, SonarQube, Semgrep, Ruff/ESLint, prose tools

### Takeaway
Every vendor keeps detection rule-based and uses AI only for the fix. Each one gates the AI with a rule allowlist (Sonar), a rescan (Snyk), a secondary review chain that yields a confidence score with an admin threshold (Semgrep), or a safe/unsafe split (Ruff).

### Cited Findings
- SonarQube AI CodeFix: detection stays rule-based, and AI generates fixes only for rules Sonar has "certified" as eligible. Rules are added to the service once they pass certification. — [Sonar docs, rules for AI CodeFix](https://docs.sonarsource.com/sonarqube-server/2025.2/user-guide/rules/rules-for-ai-codefix). I found no published accuracy figure.
- Snyk DeepCode AI Fix: Snyk researchers built a vulnerability/fix dataset with human labeling to evaluate fixes, and candidate fixes are rescanned for the original issue and for new ones. The often-quoted "about 80%" accuracy is a marketing figure. Production merge rate is not published. — [arXiv 2402.13291](https://www.arxiv.org/pdf/2402.13291); [Corgea review](https://corgea.com/learn/auto-remediation-tools) (snippet). I could not extract the paper text to confirm its numbers.
- Semgrep Assistant: a secondary review prompt chain checks whether the autofix is valid and whether the finding is still present. Problem likelihoods (for example, breaking another file) are combined into a confidence rating. Admins set the minimum confidence shown. Rule-level confidence is also an input. — [Semgrep blog 2023](https://semgrep.dev/blog/2023/assistant-public-beta/); [Semgrep docs](https://semgrep.dev/docs/semgrep-assistant/overview); [Semgrep 2025 "96% agree"](https://semgrep.dev/blog/2025/building-an-appsec-ai-that-security-researchers-agree-with-96-of-the-time/) (96% is triage agreement, not fix acceptance)
- Ruff (deterministic): every fix is labeled safe (behavior preserved) or unsafe (may change behavior or remove comments). Only safe fixes are applied by default. Unsafe fixes need `--unsafe-fixes` or per-item "Quick fix". Per-rule `extend-safe-fixes` and `extend-unsafe-fixes` settings exist, and rule docs must carry a "Fix safety" section. — [Ruff v0.1.0 blog](https://astral.sh/blog/ruff-v0.1.0); [Ruff linter docs mirror](https://git.joshthomas.dev/mirrors/ruff/raw/tag/0.13.3/docs/linter.md)
- Prose GEC research: when told simply to "correct errors", LLMs overcorrect and rewrite well-formed spans, which lowers precision and can distort meaning. Minimal-edit benchmarks weight precision because a wrong change is worse than a missed one. Mitigations include edit-level majority voting over several samples (training-free), edit-wise preference optimization, and prompt and batching tuning. — [arXiv 2506.13148](https://arxiv.org/pdf/2506.13148); [arXiv 2605.13624](https://arxiv.org/pdf/2605.13624); [arXiv 2609.10810](https://arxiv.org/pdf/2609.10810) (snippets)

### Inferences
- A layered design fits Schematron:
  - Tier 1 is a rule-defined deterministic fix (Schematron QuickFix/SQF where it exists), labeled safe or unsafe.
  - Tier 2 is an AI fix, only for an allowlist of rule IDs with proven quality, in the style of Sonar's certification.
  - Show a computed confidence (validation passed, edit size) rather than the model's self-rating.
- Overcorrection is the main risk for prose-like rules. Constrain the model to minimal edits, diff-highlight every change, and reject outputs whose text changes extend beyond the flagged span.

### Gaps
- I found no primary sources on Grammarly, LanguageTool, Vale+AI or Microsoft Editor internals in this pass.
- I did not search ESLint's fix vs. suggestion split (fix = safe/auto, suggestions = manual).

## 3. LLM repair of structured (XML/JSON) content and guardrails

### Takeaway
Constrained decoding and schema validation with retry are the established guardrails for structure. Published benchmarks cover generation into a schema more than repair of an existing document. I found no XML/DITA-specific repair benchmark.

### Cited Findings
- JSONSchemaBench (Jan 2025, EPFL/Microsoft) tests 10K real-world JSON schemas across 6 constrained-decoding frameworks (Guidance, Outlines, llama.cpp, XGrammar, OpenAI, Gemini). Constrained decoding was up to 50% faster, and the best framework supported 2x as many schemas as the worst. Downstream task quality improved by up to 4%. Complex schemas remain hard. — [arXiv 2501.10868](https://arxiv.org/abs/2501.10868v2)
- The Springdrift runtime generates XML validated against XSD with retries. It argues that heuristic JSON-repair rules accumulate special cases, and lists common LLM output defects: missing commas, unescaped quotes, truncation. — [arXiv 2604.04660](https://arxiv.org/pdf/2604.04660) (snippet)
- One benchmark paper's repair prompt restricts the model to syntax fixes and leaves content unchanged. — [arXiv 2605.18824](https://arxiv.org/pdf/2605.18824) (snippet)

### Inferences
- For DITA, structure is checked cheaply and deterministically: parse, then DTD validate, then Schematron re-run. A retry loop with the validator error fed back, capped at 1-2 retries, is the standard pattern.
- Meaning change is the hard guardrail. Compare the text content before and after outside the targeted span, and require it to be identical.

### Gaps
- I found no measured accuracy for LLM repair of DITA/XML against Schematron.
- SLOT (EMNLP 2025, schema-mapping small models) was seen only secondhand.

## 4. Cost control and triggering

### Takeaway
Vendors control cost with on-demand or per-alert triggering, caching, and small context windows. Agentic multi-file fixing is billed separately.

### Cited Findings
- Copilot Autofix caches suggestions. Narrowing the context gave a 6x compute reduction. — [GitHub blog, Jun 2024](https://github.blog/2024/06/fixing-security-vulnerabilities-with-ai/)
- Single-alert Autofix uses no AI credits, while agentic autofix is triggered explicitly per alert or campaign and costs credits and Actions minutes. — [GitHub Docs](https://docs.github.com/en/code-security/concepts/code-scanning/copilot-autofix-for-code-scanning)
- Batching several items into one prompt is studied for minimal-edit GEC. A larger context window was associated with fewer overcorrections. — [arXiv 2609.10810](https://arxiv.org/pdf/2609.10810) (title/snippet only)

### Inferences
- Generate fixes on demand per finding (the "Suggest fix" click), or in batches of findings per rule.
- Cache by hash of (rule ID, element XML).
- Skip the AI when a deterministic fix exists.
- Measure: share of findings with a suggestion, validation pass rate, accepted-as-is, edited, dismissed (the same set as GitHub's telemetry), and MTTR.

### Gaps
- No published per-fix cost figures from any vendor.
