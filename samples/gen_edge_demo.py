#!/usr/bin/env python3
"""Writes samples/edge-demo: edge cases of the case matrix (eval/cases.json) to try in AEM.

  - a table cell copied into two topics (copies-11): one piece, a conref in each cell;
  - the same cell drifted in a third topic ("business day" for "day"): listed in "Keep copies";
  - an SVG image without alt text (alt-09): drawn to a PNG by the editor for the model.

    python3 samples/gen_edge_demo.py samples/edge-demo
    ./samples/load_edge_demo.sh

Made-up product ("Ledgerline"); no customer content.
"""
import os
import sys

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
CELL = "Ask the controller to approve the close before the end of the business day."
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="200" viewBox="0 0 640 200">'
       '<rect width="640" height="200" fill="white"/>'
       '%s<text x="320" y="30" font-family="Arial" font-size="18" text-anchor="middle">Approval of a close</text></svg>')
BOXES = "".join('<rect x="%d" y="70" width="150" height="60" rx="8" fill="#e8eef7" stroke="#1f3a5f" stroke-width="3"/>'
                '<text x="%d" y="106" font-family="Arial" font-size="18" text-anchor="middle">%s</text>' % (x, x + 75, t)
                for x, t in ((30, "Requested"), (245, "Approved"), (460, "Closed")))
ARROWS = '<path d="M180 100 H240 M395 100 H455" stroke="#1f3a5f" stroke-width="3"/>'


def table(cell):
    return ('<table><tgroup cols="2"><colspec colname="c1"/><colspec colname="c2"/><thead><row><entry>Step</entry>'
            '<entry>Who</entry></row></thead><tbody><row><entry colname="c1">Approve</entry><entry colname="c2">%s</entry>'
            '</row></tbody></tgroup></table>' % cell)


def topic(name, title, body):
    return HEAD + '<topic id="%s"><title>%s</title><body>%s</body></topic>\n' % (name, title, body)


def files():
    return {
        "topics/close_month.dita": topic("close_month", "Close the month", "<p>Who does what.</p>" + table(CELL)),
        "topics/close_quarter.dita": topic("close_quarter", "Close the quarter", "<p>Who does what.</p>" + table(CELL)),
        "topics/close_year.dita": topic("close_year", "Close the year", "<p>Who does what.</p>"
                                        + table(CELL.replace("business day", "day"))),
        "topics/approval.dita": topic("approval", "How a close is approved", "<p>A close is requested, approved and "
                                      'then closed.</p><p><image href="../images/approval.svg"/></p>'),
        "images/approval.svg": SVG % (BOXES + ARROWS),
        "edge_guide.ditamap": ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                               '"map.dtd">\n<map><title>Ledgerline edge cases</title>%s</map>\n' % "".join(
                                   '<topicref href="topics/%s.dita"/>' % n for n in
                                   ("close_month", "close_quarter", "close_year", "approval"))),
    }


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge-demo")
    for path, text in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    print("wrote %s" % root)
