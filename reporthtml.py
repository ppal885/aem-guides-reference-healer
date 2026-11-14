"""Shared pieces of the HTML report (garage-week PoC)."""
import html

CSS = """
:root{--bg:#f6f6f4;--card:#fff;--text:#1c1c1a;--muted:#62625e;--line:#e2e1dc;--accent:#1d5fb8;
--bad:#b3261e;--bad-bg:#fcebea;--ok:#1f6b3a;--ok-bg:#e6f3ea;--warn:#8a5a00;--warn-bg:#fbf0d9;--info-bg:#e8f0fb;--code:#f1f0ec}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--text:#ecebe6;--muted:#a3a29b;--line:#34342f;--accent:#8ab4f8;
--bad:#f2b8b5;--bad-bg:#4a1f1c;--ok:#a8dab5;--ok-bg:#1c3a26;--warn:#f3d38a;--warn-bg:#40300c;--info-bg:#1c2c44;--code:#2a2a27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:24px;margin:0 0 4px;font-weight:600}h2{font-size:18px;margin:36px 0 12px;font-weight:600}
.sub{color:var(--muted);margin:0 0 20px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:26px;font-weight:600;line-height:1.2}.stat span{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:0 0 14px}
.url{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
.old{color:var(--bad);text-decoration:line-through}.new{color:var(--ok)}
.pill{display:inline-block;font-size:12px;padding:2px 9px;border-radius:999px;font-weight:500;white-space:nowrap}
.p-fix{background:var(--ok-bg);color:var(--ok)}.p-review{background:var(--warn-bg);color:var(--warn)}
.p-none{background:var(--code);color:var(--muted)}.p-bad{background:var(--bad-bg);color:var(--bad)}.p-info{background:var(--info-bg);color:var(--accent)}
.row{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.muted{color:var(--muted);font-size:13px}.reason{margin:10px 0 0}
ul.checks{list-style:none;padding:0;margin:10px 0 0;font-size:13px;color:var(--muted)}ul.checks li::before{content:"✓ ";color:var(--ok)}
ul.checks li.no::before{content:"✕ ";color:var(--bad)}
details{margin-top:12px;font-size:13px}summary{cursor:pointer;color:var(--accent)}
ol.steps{margin:10px 0 0;padding-left:20px}ol.steps li{margin-bottom:8px}
.tool{font:12px ui-monospace,Menlo,monospace;background:var(--code);padding:1px 6px;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}th{border-top:0;color:var(--muted);font-weight:500}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow:auto;font:12px/1.5 ui-monospace,Menlo,monospace;max-height:420px}
.add{color:var(--ok)}.del{color:var(--bad)}.wrap{overflow-x:auto}
"""


def e(value):
    return html.escape(str(value if value is not None else ""))



def _patch_html(patch, limit=160):
    lines = patch.splitlines()
    out = []
    for line in lines[:limit]:
        css = "add" if line.startswith("+") and not line.startswith("+++") else (
            "del" if line.startswith("-") and not line.startswith("---") else "")
        out.append('<span class="%s">%s</span>' % (css, e(line)))
    if len(lines) > limit:
        out.append('<span class="muted">… %d more lines in fixes.patch</span>' % (len(lines) - limit))
    return "\n".join(out)
