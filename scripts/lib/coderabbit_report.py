"""Summarise CodeRabbit's inline findings for scripts/coderabbit.sh (reads gh api JSON on stdin)."""
import json
import re
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else ""
raw = sys.stdin.read().strip()
if not raw:
    print("no review comments (or the GitHub API failed)")
    sys.exit(0)

# `gh api --paginate` concatenates one JSON array per page: "[...][...]".
dec, comments, i = json.JSONDecoder(), [], 0
while i < len(raw):
    try:
        obj, end = dec.raw_decode(raw, i)
    except ValueError:
        print("could not parse the GitHub response", file=sys.stderr)
        sys.exit(1)
    comments += obj if isinstance(obj, list) else [obj]
    i = end
    while i < len(raw) and raw[i].isspace():
        i += 1

# A finding counts as addressed when the author said so ("Addressed in commit") OR CodeRabbit itself re-checked the code
# in a reply on that thread and resolved it. CodeRabbit posts "Review thread resolved" only when it has done that, so a
# reviewer's own claim ("I verified it") does not clear a Critical/Major by itself.
RESOLVED_BY_BOT = set()
for c in comments:
    if "coderabbit" in c.get("user", {}).get("login", "").lower() and c.get("in_reply_to_id") \
            and re.search(r"Review thread resolved", c.get("body", "")):
        RESOLVED_BY_BOT.add(c["in_reply_to_id"])

ORDER = {"Critical": 0, "Major": 1, "Minor": 2, "Trivial": 3, "?": 4}
rows = []
for c in comments:
    if "coderabbit" not in c.get("user", {}).get("login", "").lower() or c.get("in_reply_to_id"):
        continue  # only the top-level findings; CodeRabbit's replies are read above
    body = c.get("body", "")
    m = re.search(r"(Critical|Major|Minor|Trivial)", body[:400])
    sev = m.group(1) if m else "?"
    addressed = bool(re.search(r"Addressed in commit", body)) or c.get("id") in RESOLVED_BY_BOT
    text = re.sub(r"<details>.*?</details>", "", body, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith(("_", "<"))]
    summary = " ".join(lines[:2])[:300] if lines else "(see the comment)"
    where = f"{(c.get('path') or '?').split('/')[-1]}:{c.get('line') or c.get('original_line') or '?'}"
    rows.append((ORDER[sev], sev, addressed, where, summary, c.get("html_url", "")))

rows.sort(key=lambda r: (r[0], r[3]))
blocking = [r for r in rows if r[1] in ("Critical", "Major") and not r[2]]
shown = [r for r in rows if mode == "--all" or r in blocking]
print(f"CodeRabbit: {len(rows)} inline finding(s); {len(blocking)} unaddressed Critical/Major")
for _, sev, addressed, where, summary, url in shown:
    tag = sev + (" ADDRESSED" if addressed else "")
    print(f"  [{tag}] {where}  {summary}\n      {url}")
if not shown and rows:
    print("  (only Minor/Trivial or addressed findings; run with --all to list them)")
sys.exit(2 if blocking else 0)
