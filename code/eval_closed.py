"""InjectNo: closed-model comparison (ROI).

Runs a closed API model through exactly the same agent episodes, prompt, two-turn loop and scorers that NB09 used for
Aya Expanse 8B and InjectNo: the 254-email benchmark v3 test and the 64 hand-written emails (sets 1-3).

Works with any OpenAI-compatible endpoint (Gemini, OpenAI, OpenRouter, ...). Every API answer is cached in a .jsonl file,
so the run can be stopped and restarted (e.g. after a free-tier daily limit) and it continues where it left off.

Usage (Gemini free tier):
    pip install openai pandas huggingface_hub
    export GEMINI_API_KEY=...            # https://aistudio.google.com/apikey
    python eval_closed.py --model gemini-2.5-flash \
        --base-url https://generativelanguage.googleapis.com/v1beta/openai/ --key-env GEMINI_API_KEY \
        --rpm 8 --price-in 0.30 --price-out 2.50
"""
import argparse, json, os, re, sys, time, importlib

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--base-url", default=None)
ap.add_argument("--key-env", default="OPENAI_API_KEY")
ap.add_argument("--label", default=None, help="name used in the CSV (default: the model id)")
ap.add_argument("--rpm", type=float, default=8, help="max requests per minute (stay under the free-tier limit)")
ap.add_argument("--max-tokens", type=int, default=4096)
ap.add_argument("--price-in", type=float, default=None, help="USD per 1M input tokens (paid tier), for the cost table")
ap.add_argument("--price-out", type=float, default=None, help="USD per 1M output tokens incl. thinking (paid tier)")
ap.add_argument("--code-dir", default="code", help="folder with bench*.py and handwritten*.py from kenil1710/injectno-bench")
ap.add_argument("--out-dir", default="results_closed")
ap.add_argument("--dry", action="store_true", help="no API calls: a fake model, to test the pipeline")
args = ap.parse_args()
label = args.label or args.model
os.makedirs(args.out_dir, exist_ok=True)

# ---------------------------------------------------------------- benchmark code (same files NB09 used)
if not os.path.exists(os.path.join(args.code_dir, "bench3.py")):
    from huggingface_hub import hf_hub_download
    os.makedirs(args.code_dir, exist_ok=True)
    for f in ["bench.py", "bench2.py", "bench3.py", "handwritten.py", "handwritten2.py", "handwritten3.py"]:
        p = hf_hub_download("kenil1710/injectno-bench", f"code/{f}", repo_type="dataset")
        open(os.path.join(args.code_dir, f), "w", encoding="utf-8").write(open(p, encoding="utf-8").read())
sys.path.insert(0, os.path.abspath(args.code_dir))
import pandas as pd
bench, bench3 = importlib.import_module("bench"), importlib.import_module("bench3")
hw, hw2, hw3 = (importlib.import_module(m) for m in ("handwritten", "handwritten2", "handwritten3"))

# ---------------------------------------------------------------- model client with cache, rate limit and retries
slug = re.sub(r"[^A-Za-z0-9._-]+", "_", label)
cache_path = os.path.join(args.out_dir, f"{slug}_cache.jsonl")
cache = {}
if os.path.exists(cache_path):
    for line in open(cache_path, encoding="utf-8"):
        try: r = json.loads(line); cache[r["key"]] = r
        except Exception: pass
print(f"{len(cache)} cached answers loaded from {cache_path}")

class DailyLimit(Exception): pass

if not args.dry:
    from openai import OpenAI
    key = os.environ.get(args.key_env)
    if not key: sys.exit(f"Set the API key first: export {args.key_env}=...")
    client = OpenAI(api_key=key, base_url=args.base_url)
_last = [0.0]

def call(key, messages):
    if key in cache: return cache[key]["text"]
    if args.dry:
        text = bench.READ_CALL if "Pay" in messages[1]["content"] else "Summary: dry run."
        rec = dict(key=key, text=text, tin=700, tout=60)
    else:
        for attempt in range(8):
            wait = 60.0 / args.rpm - (time.time() - _last[0])
            if wait > 0: time.sleep(wait)
            _last[0] = time.time()
            try:
                r = client.chat.completions.create(model=args.model, messages=messages, temperature=0, max_tokens=args.max_tokens)
                text = (r.choices[0].message.content or "").strip()
                u = r.usage
                rec = dict(key=key, text=text, tin=getattr(u, "prompt_tokens", 0) or 0,
                           tout=(getattr(u, "total_tokens", 0) or 0) - (getattr(u, "prompt_tokens", 0) or 0))
                break
            except Exception as e:
                msg = str(e) + " " + (getattr(getattr(e, "response", None), "text", "") or "")
                if "429" in msg and re.search(r"per ?day|PerDay|daily|per ?month|/ ?month|PerMonth|monthly", msg, re.I):
                    raise DailyLimit(msg[:1500])
                if any(c in msg for c in ("429", "500", "502", "503", "504", "timeout", "Timeout", "overloaded")):
                    time.sleep(min(120, 10 * 2 ** attempt)); continue
                raise
        else:
            raise RuntimeError("too many retries")
    cache[key] = rec
    with open(cache_path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["text"]

def episode(set_name, cid, msgs1, second):
    o1 = call(f"{set_name}|{cid}|1", msgs1)
    m2 = second(o1)
    o2 = call(f"{set_name}|{cid}|2", m2) if m2 is not None else ""
    return o1, o2

# ---------------------------------------------------------------- the same episodes as NB09
v3 = bench3.build_v3(seed=23)["test_v3"]
SET1 = [dict(c, cat="kency/" + c["lang"], bad=[c["attacker_account"]] if c.get("attacker_account") else []) for c in hw.CASES]
HSETS = [("set1_kency12", SET1, hw2.score), ("set2_dev28", hw2.CASES, hw2.score), ("set3_final24", hw3.CASES, hw3.score)]

rows_v3, rows_hw, stopped = [], [], None
try:
    for i, s in enumerate(v3):
        o1, o2 = episode("v3", s["id"], bench3.to_messages(s), lambda o, s=s: bench3.second_turn(s, o))
        rows_v3.append(dict(model=label, set="v3", id=s["id"], family=s["family"], kind=s["kind"], held_out=s["held_out"],
                            lang=s["lang"], style=s["style"], **bench3.score3(s, o1, o2), out1=o1, out2=o2))
        if (i + 1) % 25 == 0: print(f"v3 {i+1}/{len(v3)}")
    for name, cases, sc in HSETS:
        for c in cases:
            o1, o2 = episode(name, c["id"], hw2.to_messages(c, bench), lambda o, c=c: hw2.second_turn(c, o, bench))
            rows_hw.append(dict(model=label, set=name, id=c["id"], kind=c["kind"], family=c["cat"],
                                **sc(c, o1, o2, bench), out1=o1, out2=o2))
        print(f"{name} done")
except DailyLimit as e:
    stopped = str(e)

if stopped:
    n = len(cache)
    print(f"\nDAILY LIMIT REACHED after {n} cached answers. Nothing is lost: run the same command again tomorrow and it continues.\n{stopped}")
    sys.exit(2)

d3, dh = pd.DataFrame(rows_v3), pd.DataFrame(rows_hw)
d3.to_csv(os.path.join(args.out_dir, f"{slug}_eval_v3.csv"), index=False)
dh.to_csv(os.path.join(args.out_dir, f"{slug}_eval_handwritten.csv"), index=False)

# ---------------------------------------------------------------- comparison with the recorded Aya / InjectNo answers
pct = lambda x: f"{100 * x.mean():.1f}% ({int(x.sum())}/{len(x)})"
try:
    from huggingface_hub import hf_hub_download
    R = "results/injectno-aya-expanse-8b-v3/injectno-aya-expanse-8b-v3_eval_"
    p3 = pd.read_csv(hf_hub_download("kenil1710/injectno-bench", R + "v3.csv", repo_type="dataset"))
    ph = pd.read_csv(hf_hub_download("kenil1710/injectno-bench", R + "handwritten.csv", repo_type="dataset"))
    p3 = p3[p3.model.isin(["base", "run5"])]; ph = ph[ph.model.isin(["base", "run5"])]
    A3, AH = pd.concat([p3, d3]), pd.concat([ph, dh])
except Exception as e:
    print("could not load recorded results:", repr(e)[:200]); A3, AH = d3, dh

names = {"base": "Aya Expanse 8B", "run5": "InjectNo", label: label}
lines = ["| | " + " | ".join(names.get(m, m) for m in A3.model.unique()) + " |", "|---" * (1 + A3.model.nunique()) + "|"]
def row(title, f):
    lines.append(f"| {title} | " + " | ".join(f(A3[A3.model == m], AH[AH.model == m]) for m in A3.model.unique()) + " |")
row("v3 attacks that worked (140)", lambda a, h: pct(a[a.kind == "attack"].harmful))
row("v3 warned on attacks (140)", lambda a, h: pct(a[a.kind == "attack"].warned))
row("v3 normal emails done right (114)", lambda a, h: pct(a[a.kind == "benign"].correct))
row("v3 false alarms on normal emails (114)", lambda a, h: pct(a[a.kind == "benign"].warned))
row("hand-written attacks that worked (40)", lambda a, h: pct(h[h.kind == "attack"].harmful))
row("64 hand-written emails handled correctly", lambda a, h: pct(h.correct))
row("final exam (24): correct / harmful", lambda a, h: f"{int(h[h.set == 'set3_final24'].correct.sum())} / {int(h[h.set == 'set3_final24'].harmful.sum())}")
table = "\n".join(lines)

fam = A3[A3.kind == "attack"].groupby(["family", "model"]).harmful.mean().unstack("model").mul(100).round(1)
eps = len(d3) + len(dh)
tin = sum(r["tin"] for r in cache.values()); tout = sum(r["tout"] for r in cache.values())
cost = ""
if args.price_in is not None and args.price_out is not None:
    c1k = (tin * args.price_in + tout * args.price_out) / 1e6 / eps * 1000
    cost = (f"\nTokens: {tin:,} in / {tout:,} out (incl. thinking) over {eps} episodes = {tin/eps:.0f} in / {tout/eps:.0f} out per episode."
            f"\nAt paid-tier prices (${args.price_in}/M in, ${args.price_out}/M out): ${c1k:.2f} per 1,000 agent episodes.")
report = f"# Closed-model comparison: {label}\n\n{table}\n\nAttacks that worked, by family (%):\n\n{fam.to_string()}\n{cost}\n"
open(os.path.join(args.out_dir, f"{slug}_summary.md"), "w", encoding="utf-8").write(report)
print("\n" + report)
print("Saved:", os.listdir(args.out_dir))
