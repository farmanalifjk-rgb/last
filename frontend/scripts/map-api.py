#!/usr/bin/env python3
"""
Maps every backend operation in the OpenAPI schema against the frontend.

Inputs
  --schema FILE   OpenAPI YAML/JSON file (default: fetch from API_BASE/api/schema/
                  with API_TOKEN, both read from the environment).
Outputs
  docs/API_OPERATIONS.md                  one row per operation with its status
  src/js/api-map/operations.json          fields and parameters for every in-scope
                                          operation (wired and unwired). Deferred and
                                          server-only operations are left out.

Status values
  wired          method and path appear in frontend source
  path-only      path appears in frontend source, method could not be confirmed
  deferred       domain is outside the agreed scope (none at present; see DEFERRED)
  server-only    called by external systems or monitors, not by the UI
  unwired        in scope and not yet called by the frontend

Requires: pyyaml (and requests only when fetching the schema from the backend).
"""
import argparse, collections, json, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(FRONTEND, "src")

# Deferred domains were in scope for this round (accounting, HR, FBR, SaaS, RBAC,
# loyalty, notifications, backups, security, integrations, webhooks) per the user's
# request to map and build every remaining API. Set names here to defer again.
DEFERRED = set()
SERVER_ONLY = {"health", "system-health"}
SERVER_ONLY_PATHS = (
    "/webhook/",  # provider and Stripe webhook receivers
    "/api/fbr-simulator/",  # dev-only IMS simulator, called by the backend itself, never by the UI
)

METHODS = ("get", "post", "put", "patch", "delete")


def load_schema(path):
    if path:
        text = open(path, encoding="utf8").read()
        return yaml.safe_load(text)
    import urllib.request
    base = os.environ.get("API_BASE")
    token = os.environ.get("API_TOKEN")
    if not base or not token:
        sys.exit("Set API_BASE and API_TOKEN, or pass --schema FILE.")
    req = urllib.request.Request(base.rstrip("/") + "/api/schema/", headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req) as r:
        return yaml.safe_load(r.read().decode("utf8"))


def domain_of(path):
    return path.split("/")[2] if path.count("/") >= 2 else ""


def path_regex(p):
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "/?$")


def scan_frontend():
    """Return {schema_path: set(methods)} and the list of unmatched literal paths."""
    raw_paths = []
    for root, _, files in os.walk(SRC):
        for name in files:
            if not name.endswith((".js", ".mjs", ".html")):
                continue
            text = open(os.path.join(root, name), encoding="utf8").read()
            for m in re.finditer(r"([\"'`])(/api/[^\"'`]*)", text):
                raw = m.group(2)
                out, i = "", 0
                while i < len(raw):
                    if raw.startswith("${", i):
                        depth, j = 0, i + 1
                        while j < len(raw):
                            if raw[j] == "{":
                                depth += 1
                            elif raw[j] == "}":
                                depth -= 1
                                if depth == 0:
                                    break
                            j += 1
                        out += "{x}"
                        i = j + 1
                    else:
                        out += raw[i]
                        i += 1
                path = out.split("?")[0].split("`")[0].split(")")[0]
                window = text[m.end():m.end() + 500]
                mm = re.search(r"method:\s*[\"'](\w+)", window)
                if mm:
                    meth = mm.group(1).upper()
                else:
                    back = re.findall(r"method:\s*[\"'](\w+)", text[max(0, m.start() - 300):m.start()])
                    meth = back[-1].upper() if back else "GET"
                raw_paths.append((path, meth))
    return raw_paths


def match_calls(schema_paths, raw_paths):
    compiled = [(p, path_regex(p)) for p in schema_paths]
    calls = collections.defaultdict(set)
    unmatched = collections.Counter()
    for path, meth in raw_paths:
        if not path.endswith("/") and path.endswith("{x}"):
            path = path + "/"
        cands = [path]
        while cands[-1].endswith("{x}/"):
            cands.append(cands[-1][:-4] + "/")
        hit = None
        for cand in cands:
            for sp, rx in compiled:
                if rx.match(cand.replace("{x}", "1")):
                    hit = sp
                    break
            if hit:
                break
        if hit:
            calls[hit].add(meth)
        else:
            unmatched[path] += 1
    return calls, unmatched


def resolve(schema, node, components):
    if node is None:
        return None
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        return components.get(name)
    return node


def scalar_type(prop):
    t = prop.get("type")
    if "enum" in prop:
        return "enum", prop["enum"]
    if t in ("integer", "number", "boolean", "string"):
        fmt = prop.get("format", "")
        if t == "string" and fmt in ("date", "date-time"):
            return fmt, None
        if t == "string" and fmt in ("decimal", "float", "double"):
            return "number", None
        return t, None
    if t == "array":
        return "json", None
    if t == "object" or "properties" in prop or "additionalProperties" in prop:
        return "json", None
    return "string", None


SERVER_MANAGED = {"id", "tenant", "created_at", "updated_at", "created_by", "updated_by", "tenant_id"}


def body_fields(node, components):
    schema = resolve(None, node, components)
    if not schema:
        return None, False
    props = schema.get("properties")
    if not props or set(props) == {"data"}:
        return [], True  # generic payload with no known fields; the UI must declare them
    required = set(schema.get("required", []))
    fields = []
    for name, raw in props.items():
        prop = resolve(None, raw, components) or raw
        if prop.get("readOnly") or name in SERVER_MANAGED:
            continue
        kind, enum = scalar_type(prop)
        item = {"name": name, "type": kind, "required": name in required,
                "label": prop.get("title") or name.replace("_", " ")}
        if enum:
            item["enum"] = enum
        if prop.get("nullable"):
            item["nullable"] = True
        if "maxLength" in prop:
            item["maxLength"] = prop["maxLength"]
        if "default" in prop:
            item["default"] = prop["default"]
        fields.append(item)
    return fields, False


def response_shape(op, components):
    for code in ("200", "201"):
        resp = op.get("responses", {}).get(code)
        if not resp:
            continue
        content = resp.get("content", {}).get("application/json", {}).get("schema")
        schema = resolve(None, content, components) if content else None
        if not schema:
            return {"kind": "other"}
        if schema.get("type") == "array":
            items = resolve(None, schema.get("items"), components) or {}
            return {"kind": "list", "fields": scalar_fields(items, components)}
        props = schema.get("properties", {})
        if "results" in props:
            items = resolve(None, props["results"].get("items"), components) or {}
            return {"kind": "paginated", "fields": scalar_fields(items, components)}
        return {"kind": "object", "fields": scalar_fields(schema, components)}
    return {"kind": "none"}


def scalar_fields(schema, components):
    out = []
    for name, raw in (schema.get("properties") or {}).items():
        prop = resolve(None, raw, components) or raw
        kind, _ = scalar_type(prop)
        if kind == "json":
            continue
        out.append({"name": name, "type": kind})
    return out


def query_params(op, components):
    out = []
    for p in op.get("parameters", []):
        if p.get("in") != "query":
            continue
        sch = resolve(None, p.get("schema", {}), components) or {}
        kind, enum = scalar_type(sch) if sch else ("string", None)
        item = {"name": p["name"], "type": kind, "required": bool(p.get("required"))}
        if enum:
            item["enum"] = enum
        out.append(item)
    return out


# Operations called through runtime-built paths (for example `${verb}`) that the
# static scan cannot see. Reviewed by hand; keep this list short.
MANUAL_WIRED = {
    ("POST", "/api/purchasing/purchase-returns/{id}/cancel/"),
    ("POST", "/api/purchasing/purchase-returns/{id}/process/"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema")
    args = ap.parse_args()
    schema = load_schema(args.schema)
    components = schema.get("components", {}).get("schemas", {})

    ops = []
    for path, item in schema["paths"].items():
        for m in METHODS:
            if m in item:
                ops.append((m.upper(), path, item[m]))

    raw = scan_frontend()
    calls, unmatched = match_calls(list(schema["paths"].keys()), raw)

    rows, new_ui = [], {}
    for method, path, op in ops:
        dom = domain_of(path)
        if dom in SERVER_ONLY or any(s in path for s in SERVER_ONLY_PATHS):
            status = "server-only"
        elif dom in DEFERRED:
            status = "deferred"
        else:
            methods = calls.get(path, set())
            if method in methods or (method, path) in MANUAL_WIRED:
                status = "wired"
            elif methods:
                status = "path-only"
            else:
                status = "unwired"
        rows.append((method, path, op.get("summary", ""), status))
        if status in ("unwired", "wired", "path-only"):
            entry = {"method": method, "path": path,
                     "params": query_params(op, components),
                     "response": response_shape(op, components)}
            entry["body"], entry["bodyGeneric"] = None, False
            if "requestBody" in op:
                content = op["requestBody"].get("content", {})
                jsonc = content.get("application/json", {}).get("schema")
                formc = resolve(None, content.get("multipart/form-data", {}).get("schema"), components) or {}
                has_file = any((resolve(None, v, components) or v).get("format") == "binary"
                               for v in (formc.get("properties") or {}).values())
                if has_file:
                    entry["multipart"] = True
                    entry["body"], entry["bodyGeneric"] = body_fields(formc, components)
                elif jsonc:
                    entry["body"], entry["bodyGeneric"] = body_fields(jsonc, components)
                elif formc:
                    entry["body"], entry["bodyGeneric"] = body_fields(formc, components)
            new_ui[f"{method} {path}"] = entry

    # Write the operations map.
    counts = collections.Counter(r[3] for r in rows)
    lines = [
        "# API operations map",
        "",
        "Generated by `frontend/scripts/map-api.py` from the backend OpenAPI schema.",
        "Do not edit by hand. Re-run the script after backend changes.",
        "",
        "## Summary",
        "",
        "| Status | Operations |",
        "|---|---:|",
    ]
    for key in ("wired", "path-only", "unwired", "deferred", "server-only"):
        lines.append(f"| {key} | {counts.get(key, 0)} |")
    lines += ["", f"Total operations: {len(rows)}.", "",
              "`wired` and `path-only` come from a static scan of the frontend source. A call built",
              "from a runtime variable (for example `${verb}`) is not matched, so a few operations can",
              "show as `unwired` while they are used. Check those by hand.", "",
              "## By domain", "", "| Domain | Operations | Wired | Path-only | Unwired | Deferred | Server-only |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    by_dom = collections.defaultdict(collections.Counter)
    for method, path, summary, status in rows:
        by_dom[domain_of(path)][status] += 1
        by_dom[domain_of(path)]["total"] += 1
    for dom in sorted(by_dom, key=lambda d: (-by_dom[d]["total"], d)):
        c = by_dom[dom]
        lines.append(f"| {dom} | {c['total']} | {c['wired']} | {c['path-only']} | {c['unwired']} | {c['deferred']} | {c['server-only']} |")
    lines += ["", "## Operations", "", "| Method | Path | Summary | Status |", "|---|---|---|---|"]
    for method, path, summary, status in rows:
        lines.append(f"| {method} | `{path}` | {summary} | {status} |")
    lines += ["", "## Unmatched literal paths", "",
              "Paths the scan saw in source that do not match any schema path. Review these.", ""]
    for path, n in unmatched.most_common():
        lines.append(f"- `{path}` ({n})")
    out_md = os.path.join(FRONTEND, "docs", "API_OPERATIONS.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    open(out_md, "w", encoding="utf8").write("\n".join(lines) + "\n")

    out_json = os.path.join(SRC, "js", "api-map", "operations.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    open(out_json, "w", encoding="utf8").write(json.dumps(new_ui, indent=1, sort_keys=True) + "\n")
    print(json.dumps(counts, indent=1))
    print(f"wrote {out_md}\nwrote {out_json} ({len(new_ui)} operations)")


if __name__ == "__main__":
    main()
