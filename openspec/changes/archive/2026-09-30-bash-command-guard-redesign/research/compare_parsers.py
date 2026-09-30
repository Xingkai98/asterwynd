"""Head-to-head: current tokenizer vs tree-sitter-bash vs bashlex.

Measures, over the same corpus:
  - parse coverage (commands correctly recovered as separate command nodes)
  - error signalling (does it tell you it failed?)
  - words recovered for the DESTINATION of an mv/cp (the semantic the guard needs)
  - latency
"""
import json, sys, pathlib, time, traceback

REPO = pathlib.Path("/home/happy/.paseo/worktrees/0frj3kg8/bash-command-guard-redesign-2026-09-27")
sys.path.insert(0, str(REPO))
corpus = json.loads((REPO / ".guardlab-corpus.json").read_text())

# ---------- A. current tokenizer ----------
from agent.tools.command_guard import tokenize_command, _check_command_text

def tok_commands(cmd):
    return [seg for seg in _check_command_text(cmd) if seg]

# ---------- B. tree-sitter-bash ----------
from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_bash
LANG = Language(tree_sitter_bash.language())
_TS_PARSER = Parser(LANG)
_CMD_Q = Query(LANG, "(command) @c")

def ts_parse(cmd):
    tree = _TS_PARSER.parse(cmd.encode())
    root = tree.root_node
    caps = QueryCursor(_CMD_Q).captures(root)
    nodes = caps.get("c", [])
    # for each command node, recover argv-ish words
    cmds = []
    for n in nodes:
        words = []
        for ch in n.children:
            if ch.type in ("command_name", "word", "string", "raw_string", "concatenation",
                           "simple_expansion", "expansion", "command_substitution",
                           "process_substitution", "number", "variable_assignment"):
                words.append(ch.text.decode("utf-8", "replace"))
        cmds.append(words)
    return {"has_error": root.has_error, "n_commands": len(nodes), "commands": cmds, "root": root.type}

# ---------- C. bashlex ----------
import bashlex

def bl_parse(cmd):
    try:
        parts = bashlex.parse(cmd)
    except Exception as e:  # bashlex raises for many inputs
        return {"raised": type(e).__name__, "commands": [], "n_commands": 0, "has_error": True}
    cmds = []
    def walk(node):
        if getattr(node, "kind", None) == "command":
            words = [cmd[node.pos[0]:node.pos[1]] for node in node.parts if getattr(node, "kind", None) == "word"]
            cmds.append(words)
            return
        for p in getattr(node, "parts", []) or []:
            walk(p)
    for p in parts:
        walk(p)
    return {"raised": None, "commands": cmds, "n_commands": len(cmds), "has_error": False}

# ---------- harness ----------
def bench(fn, cmd, n=200):
    fn(cmd)
    t0 = time.perf_counter()
    for _ in range(n):
        fn(cmd)
    return (time.perf_counter() - t0) / n * 1000  # ms

REPRESENTATIVE = "git status --short && ls -la /tmp | grep -v node_modules || rm -rf build 2>/dev/null"

rows = []
for c in corpus:
    cmd = c["command"]
    t = tok_commands(cmd)
    ts = ts_parse(cmd)
    bl = bl_parse(cmd)
    rows.append({
        "id": c["id"], "category": c["category"], "command": cmd,
        "tok_n": len(t),
        "ts_n": ts["n_commands"], "ts_err": ts["has_error"],
        "bl_n": bl["n_commands"], "bl_raised": bl["raised"],
    })

pathlib.Path("/tmp/guardlab/rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))

# ---- summarize ----
from collections import Counter, defaultdict
cat = defaultdict(lambda: Counter())
for r in rows:
    c = cat[r["category"]]
    c["n"] += 1
    c["ts_err"] += int(r["ts_err"])
    c["bl_raised"] += int(bool(r["bl_raised"]))

print("=== error / raise rates by category ===")
print(f"{'category':28} {'n':>4} {'ts_has_error':>13} {'bashlex_raised':>15}")
for k in sorted(cat):
    v = cat[k]
    print(f"{k:28} {v['n']:>4} {v['ts_err']:>13} {v['bl_raised']:>15}")

tot = Counter(r["ts_err"] for r in rows)
print("\nOVERALL ts has_error:", dict(tot), "of", len(rows))
print("OVERALL bashlex raised:", sum(1 for r in rows if r["bl_raised"]), "of", len(rows))
print("OVERALL bashlex raise kinds:", Counter(r["bl_raised"] for r in rows if r["bl_raised"]))

print("\n=== latency (ms/call, n=300) ===")
print(f"  tokenizer      : {bench(lambda s: tok_commands(s), REPRESENTATIVE):.4f}")
print(f"  tree-sitter    : {bench(lambda s: ts_parse(s), REPRESENTATIVE):.4f}")
print(f"  bashlex        : {bench(lambda s: bl_parse(s), REPRESENTATIVE):.4f}")
