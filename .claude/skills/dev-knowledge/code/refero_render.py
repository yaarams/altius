#!/usr/bin/env python3
"""Render a Refero Styles API response to DESIGN.md.

Usage: UUID=<uuid> python3 workspace/dev-knowledge/skills/code/refero_render.py
Reads:  workspace/local/design/<uuid>.json
Writes: workspace/local/design/<uuid>.DESIGN.md
See:    workspace/dev-knowledge/skills/refero_design_styles.md
"""
from __future__ import annotations
import json, os, pathlib, sys

BASE = pathlib.Path("workspace/local/design")

def render(uuid: str) -> pathlib.Path:
    src = json.loads((BASE / f"{uuid}.json").read_text())
    s   = src["style"]
    ds  = s["fullResult"]["designSystem"]
    name = s.get("siteName", "unknown")

    out = [
        f"# DESIGN.md \u2014 {name}",
        f"> Source: {s.get('url','')}",
        f"> Refero: https://styles.refero.design/style/{uuid}",
        f"> North star: {ds.get('northStar','')}",
        "", "## Description", ds.get("description", ""),
        "", "## Theme & Industry",
        f"- theme: {ds.get('theme','')}",
        f"- industry: {ds.get('industry','')}",
        "", "## Colors",
    ]
    for c in ds.get("colors", []):
        grp = f" _{c.get('group','')}_" if c.get("group") else ""
        out.append(f"- **{c.get('name','')}** `{c.get('hex','')}`{grp} \u2014 {c.get('role','')}")

    out += ["", "## Surfaces"]
    for x in ds.get("surfaces", []):
        out.append(f"- **{x.get('name','')}** `{x.get('hex','')}` (level {x.get('level','')}) \u2014 {x.get('purpose','')}")

    out += ["", "## Elevation"]
    for e in ds.get("elevation", []):
        out.append(f"- **{e.get('element','')}** \u2014 `{e.get('style','')}`")

    out += ["", "## Typography"]
    for t in ds.get("typography", []):
        out.append(
            f"- **{t.get('family','')}** \u2014 weights: {t.get('weight','')}; "
            f"sizes: {t.get('sizes','')}; line-heights: {t.get('lineHeight','')}"
        )
        if t.get("role"):
            out.append(f"  > {t['role']}")

    out += ["", "## Type scale"]
    for t in ds.get("typeScale", []):
        ls = t.get("letterSpacing")
        ls_s = f", tracking {ls}" if ls is not None else ""
        out.append(
            f"- **{t.get('role','')}** \u2014 {t.get('size','')}px / {t.get('lineHeight','')}{ls_s}"
        )

    out += ["", "## Spacing", "```json",
            json.dumps(ds.get("spacing", {}), indent=2), "```"]

    out += ["", "## Components"]
    for c in ds.get("components", []):
        out.append(f"### {c.get('name','')}")
        if c.get("role"):
            out.append(f"_{c['role']}_\n")
        out.append(c.get("description", "") or "")
        out.append("")

    out += ["## Layout", ds.get("layout", ""),
            "", "## Imagery", ds.get("imagery", ""),
            "", "## Do"]
    out += [f"- {x}" for x in ds.get("dos", [])]
    out += ["", "## Don't"]
    out += [f"- {x}" for x in ds.get("donts", [])]

    for cs in ds.get("customSections", []):
        out += ["", f"## {cs.get('title','Notes')}", cs.get("content", "")]

    out += ["", "## Similar brands (Refero suggestions)"]
    for b in src.get("similar", [])[:10]:
        out.append(f"- {b.get('siteName','')} \u2014 https://styles.refero.design/style/{b.get('id','')}")

    dest = BASE / f"{uuid}.DESIGN.md"
    dest.write_text("\n".join(out))
    return dest

if __name__ == "__main__":
    uuid = os.environ.get("UUID") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not uuid:
        sys.exit("set UUID=<refero-uuid> or pass it as argv[1]")
    print(render(uuid))
