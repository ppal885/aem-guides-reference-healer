#!/usr/bin/env python3
"""Writes samples/alt-demo: made-up images in made-up topics, to check how alt texts are found and
suggested. Needs Pillow (`pip install pillow`, in the link-healer .venv).

  - a sign-in dialog (no alt), used in two topics;
  - a "Close period" dialog with its button (no alt);
  - a bar chart of postings per month (alt "chart": generic);
  - a flow diagram Draft -> Review -> Posted (alt is the file name);
  - the product logo (a good alt already: not listed);
  - a decorative divider line (no alt; the right answer is "decorative");
  - a settings screen whose sentence talks about the time zone field (no alt).

truth.json says, for each image, the words a right alt has (any one of each list) and whether it
is decorative.

    python3 samples/gen_alt_demo.py samples/alt-demo
    ./samples/load_alt_demo.sh

Made-up product ("Ledgerline"); no customer content.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

TOPIC = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
TASK = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n'


def font(size):
    for name in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                 "/Library/Fonts/Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def window(title, w=640, h=400):
    img = Image.new("RGB", (w, h), "#f4f5f7")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 44], fill="#1f3a5f")
    d.text((16, 12), title, fill="white", font=font(20))
    return img, d


def field(d, x, y, label, value="", w=360):
    d.text((x, y), label, fill="#222", font=font(16))
    d.rectangle([x, y + 24, x + w, y + 60], outline="#888", fill="white")
    d.text((x + 8, y + 32), value, fill="#555", font=font(16))


def button(d, x, y, text, primary=True):
    d.rounded_rectangle([x, y, x + 150, y + 42], 6, fill="#2a6edb" if primary else "white", outline="#2a6edb")
    d.text((x + 18, y + 11), text, fill="white" if primary else "#2a6edb", font=font(17))


def images(folder):
    os.makedirs(folder, exist_ok=True)
    img, d = window("Ledgerline - Sign in")
    field(d, 140, 80, "Work email", "name@example.com")
    field(d, 140, 170, "Password", "••••••••")
    button(d, 140, 270, "Sign in")
    d.text((320, 282), "Forgot password?", fill="#2a6edb", font=font(15))
    img.save(os.path.join(folder, "signin.png"))

    img, d = window("Close period - March 2026", 640, 300)
    d.text((40, 80), "Closing locks every journal entry in March 2026.", fill="#222", font=font(17))
    d.text((40, 110), "Open entries: 0     Pending approvals: 0", fill="#222", font=font(17))
    button(d, 300, 220, "Close period")
    button(d, 470, 220, "Cancel", primary=False)
    img.save(os.path.join(folder, "close_dialog.png"))

    img = Image.new("RGB", (640, 380), "white")
    d = ImageDraw.Draw(img)
    d.text((170, 12), "Postings per month, 2026", fill="#222", font=font(20))
    values = [("Jan", 120), ("Feb", 150), ("Mar", 210), ("Apr", 260), ("May", 300)]
    for i, (month, v) in enumerate(values):
        x = 80 + i * 105
        d.rectangle([x, 330 - v, x + 60, 330], fill="#2a6edb")
        d.text((x + 14, 338), month, fill="#222", font=font(16))
        d.text((x + 12, 330 - v - 22), str(v), fill="#222", font=font(15))
    d.line([60, 330, 600, 330], fill="#222", width=2)
    img.save(os.path.join(folder, "postings_chart.png"))

    img = Image.new("RGB", (700, 200), "white")
    d = ImageDraw.Draw(img)
    for i, step in enumerate(["Draft", "Review", "Posted"]):
        x = 30 + i * 240
        d.rounded_rectangle([x, 70, x + 170, 130], 10, outline="#1f3a5f", width=3, fill="#e8eef7")
        d.text((x + 50, 88), step, fill="#1f3a5f", font=font(20))
        if i < 2:
            d.line([x + 175, 100, x + 235, 100], fill="#1f3a5f", width=3)
            d.polygon([(x + 235, 92), (x + 235, 108), (x + 245, 100)], fill="#1f3a5f")
    d.text((240, 20), "Journal entry states", fill="#222", font=font(18))
    img.save(os.path.join(folder, "entry_flow.png"))

    img = Image.new("RGB", (300, 90), "white")
    d = ImageDraw.Draw(img)
    d.ellipse([10, 15, 70, 75], fill="#2a6edb")
    d.text((90, 28), "Ledgerline", fill="#1f3a5f", font=font(30))
    img.save(os.path.join(folder, "logo.png"))

    img = Image.new("RGB", (600, 12), "white")
    d = ImageDraw.Draw(img)
    d.line([0, 6, 600, 6], fill="#c8ccd2", width=2)
    img.save(os.path.join(folder, "divider.png"))

    img, d = window("Settings - Company")
    field(d, 40, 70, "Company name", "Ledgerline Demo Ltd")
    field(d, 40, 160, "Time zone", "(UTC+05:30) Asia/Kolkata")
    field(d, 40, 250, "Fiscal year starts", "April")
    button(d, 450, 340, "Save")
    img.save(os.path.join(folder, "settings.png"))


def topic(name, title, body, kind="topic"):
    head = TOPIC if kind == "topic" else TASK
    return head + '<%s id="%s"><title>%s</title><body>%s</body></%s>\n' % (kind, name, title, body, kind) if kind == "topic" else \
        head + '<task id="%s"><title>%s</title><taskbody>%s</taskbody></task>\n' % (name, title, body)


def files():
    return {
        "topics/sign_in.dita": topic("sign_in", "Sign in to Ledgerline",
                                     '<p>Enter your work email and password, then select Sign in.</p>'
                                     '<p><image href="../images/signin.png"/></p>'
                                     '<p><image href="../images/divider.png"/></p>'),
        "topics/first_steps.dita": topic("first_steps", "First steps",
                                         '<p>Everyone starts at the sign-in screen.</p>'
                                         '<fig><title>The sign-in screen</title><image href="../images/signin.png"/></fig>'
                                         '<p><image href="../images/logo.png"><alt>Ledgerline logo</alt></image></p>'),
        "topics/close_period.dita": topic("close_period", "Close a period", '<steps><step><cmd>Open Periods and select '
                                          'Close period.</cmd><info><p>Check that no entries are open, then confirm with '
                                          'Close period.</p><p><image href="../images/close_dialog.png"/></p></info></step>'
                                          '</steps>', kind="task"),
        "topics/reports.dita": topic("reports", "Posting reports",
                                     '<p>The number of postings grew every month this year.</p>'
                                     '<p><image href="../images/postings_chart.png"><alt>chart</alt></image></p>'),
        "topics/entry_states.dita": topic("entry_states", "Journal entry states",
                                          '<p>An entry moves from draft to review to posted.</p>'
                                          '<p><image href="../images/entry_flow.png"><alt>entry_flow.png</alt></image></p>'),
        "topics/settings.dita": topic("settings", "Company settings",
                                      '<p>Set the time zone before the first period is closed: periods close at midnight '
                                      'in that time zone.</p><p><image href="../images/settings.png"/></p>'),
        "alt_guide.ditamap": ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                              '"map.dtd">\n<map><title>Ledgerline images</title>%s</map>\n' % "".join(
                                  '<topicref href="topics/%s.dita"/>' % n for n in
                                  ("sign_in", "first_steps", "close_period", "reports", "entry_states", "settings"))),
    }


TRUTH = {
    "signin.png": {"listed": True, "uses": 2, "words": [["sign in", "sign-in", "login", "log in"], ["email", "password"]]},
    "close_dialog.png": {"listed": True, "uses": 1, "words": [["close period"], ["march", "confirm", "dialog", "lock"]]},
    "postings_chart.png": {"listed": True, "uses": 1, "words": [["posting"], ["month", "grow", "increas", "rising", "jan", "may"]]},
    "entry_flow.png": {"listed": True, "uses": 1, "words": [["draft"], ["review"], ["post"]]},
    "logo.png": {"listed": False},
    "divider.png": {"listed": True, "uses": 1, "decorative": True},
    "settings.png": {"listed": True, "uses": 1, "words": [["time zone", "timezone"], ["setting", "company"]]},
}


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "alt-demo")
    images(os.path.join(root, "images"))
    for path, text in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    with open(os.path.join(root, "truth.json"), "w") as f:
        json.dump(TRUTH, f, indent=1)
    print("wrote %s" % root)
