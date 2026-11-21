# For an AI assistant working in this repository

Read [CONTEXT.md](CONTEXT.md) first. It holds the decisions, the owner's working rules, what was learned about AEM Guides, and what is open. [README.md](README.md) has the setup and the measurements.

The rules that matter most:

- Never put a key, token or password into a file, a commit or a chat. Keys are set in the owner's own terminal.
- Commit only when asked. Never push without being asked.
- Report measured numbers. When a number is not measured, say so.
- Do not claim the planner is more accurate than the fixed pipeline: on the large sample it is not (`eval/refs/pipeline-eval.json` against `planner-eval.json`).
- The agent proposes; a person applies. Do not add a path where the agent writes to the repository by itself, and do not add a trigger that starts it when content is renamed.
- Anything shown in the editor uses the editor's own components, icons and highlight.

Before you say a change works:

```bash
python3 -m unittest discover -s tests
```

For a change in how repairs are decided, also run `python3 planeval.py --runs 3` and `python3 rankeval.py --runs 2` (they call the model and take minutes) and update the "Measured" table in the README with what came out. For a change in a system prompt, also run `python3 injecteval.py --runs 2`.

For a change in what a Fix or a Share writes (editor `fix_all.ts`, `copy_apply.ts`, `copy_bulk.ts`, `copy_keys.ts`), run it on a sample in local AEM and then `python3 aftercheck.py --map <the map>`: it runs the map's check in AEM and fails when AEM's own report calls something the Fix wrote broken. On 19 Nov 2026 a Fix that looked right in the editor left 360 references AEM called broken, unseen for three days.
