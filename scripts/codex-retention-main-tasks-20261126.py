#!/usr/bin/env python3
"""Locked main-cohort executable tasks for the Codex retention experiment."""

import importlib.util
from pathlib import Path
import sys


sys.dont_write_bytecode = True
builder_path = Path(__file__).with_name("codex-retention-task-fixtures-20261126.py")
spec = importlib.util.spec_from_file_location("retention_fixture_builder", builder_path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


builder.CATALOG = {
    "R01": {
        "title": "Correct cursor pagination in a job event log",
        "starter": '''
            def run(data):
                records = sorted(data["events"], key=lambda row: row["when"])
                if data.get("after"):
                    records = [row for row in records if row["when"] > data["after"][0]]
                return [row["id"] for row in records[:data["limit"]]]
        ''',
        "first": "Return up to `limit` active event IDs sorted by `(when, id)` in ascending order. Each optional `after` value is the two-element list `[when, id]`. The page begins strictly after this complete pair and must work when the pair is absent from the source rows. The initial contract allows arbitrary positive limits.",
        "middle": "Tombstone rows have `deleted: true` and are excluded before pagination. Missing `deleted` means active. An absent or null `after` means start at the beginning.",
        "latest": "The service page limit is now capped at three results. A requested limit below zero returns an empty list, as does zero.",
        "diagnosis": "CURSOR_DROPS_TIED_EVENTS", "receipt": "JEV-507",
        "operation": "backfill the remote event index", "versions": ["event-paging/4", "event-paging/5"],
        "baseline": ({"events":[{"id":"a","when":4},{"id":"b","when":4},{"id":"c","when":5}],"after":[4,"a"],"limit":2}, ["c"], ["b","c"]),
        "cases": [
            ({"events":[{"id":"z","when":0},{"id":"x","when":0},{"id":"b","when":-2},{"id":"a","when":0}],"after":[0,"c"],"limit":2}, ["x","z"]),
            ({"events":[{"id":name,"when":i} for i,name in enumerate("abcdef")],"limit":18}, ["a","b","c"]),
            ({"events":[{"id":"zero","when":0,"deleted":True},{"id":"one","when":1,"deleted":False},{"id":"two","when":2}],"after":None,"limit":2}, ["one","two"]),
            ({"events":[{"id":"first","when":0},{"id":"next","when":1}],"limit":-1}, []),
            ({"events":[],"limit":3}, []),
        ],
    },
    "R02": {
        "title": "Fix delayed job dequeue ordering",
        "starter": '''
            def run(data):
                ready = [job for job in data["jobs"] if job["ready_at"] <= data["now"]]
                return [job["id"] for job in ready]
        ''',
        "first": "Return ready job IDs. Sort eligible jobs by highest `priority` first, then earliest `ready_at`, then ascending ID. Jobs whose ready_at exceeds now are not ready. The initial rule permits an arbitrary number of retries.",
        "middle": "Jobs in terminal states succeeded, failed, or canceled are excluded, as are jobs with absent or null ready_at. A missing state means queued. A missing `attempts` count is zero.",
        "latest": "Include only jobs whose attempts is strictly below their `max_attempts`. The max defaults to four when absent. Zero is an explicit cap of zero and admits no jobs.",
        "diagnosis": "DISPATCH_IGNORES_PRIORITY", "receipt": "DQ-8894",
        "operation": "resume external workers", "versions": ["dequeue/8", "dequeue/9"],
        "baseline": ({"now":3,"jobs":[{"id":"slow","ready_at":1,"priority":1},{"id":"fast","ready_at":3,"priority":2}]}, ["slow","fast"], ["fast","slow"]),
        "cases": [
            ({"now":6,"jobs":[{"id":"c","ready_at":6,"priority":0},{"id":"b","ready_at":6,"priority":0},{"id":"a","ready_at":5,"priority":0}]}, ["a","b","c"]),
            ({"now":10,"jobs":[{"id":"live","ready_at":8,"priority":0},{"id":"off","ready_at":1,"priority":3,"state":"canceled"},{"id":"unknown","ready_at":None,"priority":4},{"id":"missing","priority":8},{"id":"later","ready_at":11,"priority":3}]}, ["live"]),
            ({"now":2,"jobs":[{"id":"zero","ready_at":0,"priority":1,"max_attempts":0},{"id":"explicit","ready_at":2,"priority":1,"attempts":5,"max_attempts":6},{"id":"at_default","ready_at":0,"priority":8,"attempts":4},{"id":"below_default","ready_at":1,"priority":2,"attempts":3}]}, ["below_default","explicit"]),
            ({"now":0,"jobs":[{"id":"ok","ready_at":0,"priority":1,"attempts":0},{"id":"future","ready_at":1,"priority":9}]}, ["ok"]),
            ({"now":8,"jobs":[]}, []),
        ],
    },
    "R03": {
        "title": "Merge availability intervals in a calendar renderer",
        "starter": '''
            def run(data):
                return sorted(data["windows"])
        ''',
        "first": "Build the union of half-open windows `[start, end)` as a sorted list of disjoint windows. Start and end are integers. Merge overlapping or touching windows. The initial contract returns the whole union.",
        "middle": "Discard zero-length and reversed windows before merging. Input order is arbitrary. Negative timestamps are valid.",
        "latest": "If non-null `clip` is supplied, intersect the union with that half-open window. Exclude zero-length intersections. Absent or null `clip` means unrestricted. A reversed or empty clip returns an empty result.",
        "diagnosis": "OVERLAPPING_SLOTS_DUPLICATE", "receipt": "CW-921",
        "operation": "replace the shared calendar availability", "versions": ["window-union/2", "window-union/3"],
        "baseline": ({"windows":[[7,11],[4,8]]}, [[4,8],[7,11]], [[4,11]]),
        "cases": [
            ({"windows":[[3,7],[-3,0],[0,3],[4,5],[12,13]],"clip":[-1,12]}, [[-1,7]]),
            ({"windows":[[0,0],[6,2],[-6,-4],[-2,-1],[1,3]],"clip":[-5,2]}, [[-5,-4],[-2,-1],[1,2]]),
            ({"windows":[[1,8]],"clip":[4,4]}, []),
            ({"windows":[[1,8]],"clip":[5,2]}, []),
            ({"windows":[[3,9],[0,3]],"clip":None}, [[0,9]]),
        ],
    },
    "R04": {
        "title": "Reconcile local export receipts with the requested revision",
        "starter": '''
            def run(data):
                by_key = {receipt["key"]: receipt for receipt in data["receipts"]}
                return {job["key"]: by_key.get(job["key"], {}).get("state", "UNKNOWN") for job in data["jobs"]}
        ''',
        "first": "Return a key-to-state map for requested jobs. Select receipts whose `key` and `revision` both match the job. Missing matches are UNKNOWN. If receipts repeat, select the matching receipt with greatest integer `seq`; equal sequences keep the first one under the original revision.",
        "middle": "Receipt states written and failed are the only known states. An unrecognized state on the selected receipt is UNKNOWN. The decision uses matching receipts only and retains every requested job in its result.",
        "latest": "Conflicting states at the greatest matching sequence produce UNKNOWN. Matching repeats of the same state do not create ambiguity. Any lower sequence is irrelevant once a greater sequence exists.",
        "diagnosis": "STALE_RECEIPT_MARKS_JOB_DONE", "receipt": "EX-9318",
        "operation": "sync exports to external storage", "versions": ["export-check/6", "export-check/7"],
        "baseline": ({"jobs":[{"key":"invoice","revision":3}],"receipts":[{"key":"invoice","revision":2,"seq":1,"state":"written"}]}, {"invoice":"written"}, {"invoice":"UNKNOWN"}),
        "cases": [
            ({"jobs":[{"key":"a","revision":3},{"key":"b","revision":2}],"receipts":[{"key":"a","revision":3,"seq":5,"state":"failed"},{"key":"a","revision":3,"seq":2,"state":"written"},{"key":"a","revision":2,"seq":15,"state":"written"}]}, {"a":"failed","b":"UNKNOWN"}),
            ({"jobs":[{"key":"a","revision":2},{"key":"b","revision":1}],"receipts":[{"key":"a","revision":2,"seq":0,"state":"written"},{"key":"a","revision":2,"seq":0,"state":"failed"},{"key":"b","revision":1,"seq":0,"state":"written"},{"key":"b","revision":1,"seq":0,"state":"written"}]}, {"a":"UNKNOWN","b":"written"}),
            ({"jobs":[{"key":"d","revision":1}],"receipts":[{"key":"d","revision":1,"seq":0,"state":"pending"},{"key":"d","revision":1,"seq":-1,"state":"written"}]}, {"d":"UNKNOWN"}),
            ({"jobs":[{"key":"a","revision":1}],"receipts":[{"key":"a","revision":1,"seq":1,"state":"failed"},{"key":"a","revision":1,"seq":1,"state":"written"},{"key":"a","revision":1,"seq":2,"state":"written"}]}, {"a":"written"}),
            ({"jobs":[],"receipts":[{"key":"a","revision":1,"seq":1,"state":"failed"}]}, {}),
        ],
    },
    "R05": {
        "title": "Calculate effective alert muting for overlapping rules",
        "starter": '''
            def run(data):
                return [alert["id"] for alert in data["alerts"]]
        ''',
        "first": "Return the IDs of unsuppressed alerts in original input order. A mute for the alert tenant and exact category suppresses an alert whose `at` is inside `[start, end)`. Missing match means unmuted.",
        "middle": "Ignore mutes that have `enabled: false`; missing `enabled` means true. Treat category `*` as a mute for every category of its own tenant only. An empty or reversed interval never matches.",
        "latest": "A mute can have optional integer `revoked_at`. From that timestamp onward it no longer applies, even inside its original interval. Absent or null revoked_at leaves the original end unchanged. Another active mute can still suppress the alert.",
        "diagnosis": "MUTED_ALERT_DELIVERED", "receipt": "AL-148",
        "operation": "enable notification delivery to the on-call service", "versions": ["alert-mute/13", "alert-mute/14"],
        "baseline": ({"alerts":[{"id":"x","tenant":"one","category":"db","at":1}],"mutes":[{"tenant":"one","category":"db","start":0,"end":2}]}, ["x"], []),
        "cases": [
            ({"alerts":[{"id":"before","tenant":"a","category":"db","at":1},{"id":"start","tenant":"a","category":"db","at":2},{"id":"end","tenant":"a","category":"db","at":7},{"id":"tenant","tenant":"b","category":"db","at":3}],"mutes":[{"tenant":"a","category":"*","start":2,"end":7}]}, ["before","end","tenant"]),
            ({"alerts":[{"id":"a","tenant":"t","category":"api","at":3}],"mutes":[{"tenant":"t","category":"*","start":0,"end":4,"enabled":False},{"tenant":"t","category":"db","start":0,"end":4},{"tenant":"t","category":"*","start":5,"end":3}]}, ["a"]),
            ({"alerts":[{"id":"early","tenant":"t","category":"api","at":-1},{"id":"at","tenant":"t","category":"api","at":0},{"id":"later","tenant":"t","category":"db","at":1}],"mutes":[{"tenant":"t","category":"*","start":-3,"end":8,"revoked_at":0},{"tenant":"t","category":"db","start":0,"end":8,"revoked_at":None}]}, ["at"]),
            ({"alerts":[{"id":"b","tenant":"t","category":"x","at":0},{"id":"a","tenant":"t","category":"x","at":0}],"mutes":[]}, ["b","a"]),
            ({"alerts":[],"mutes":[{"tenant":"t","category":"*","start":0,"end":9}]}, []),
        ],
    },
    "R06": {
        "title": "Conform import preview to configured column aliases",
        "starter": '''
            def run(data):
                return [dict(zip(data["headers"], row)) for row in data["rows"]]
        ''',
        "first": "For each source row, return a mapping only for columns whose names are in `fields` or map to one through `aliases`. Canonical header names do not require an alias entry. Normalize headers to lowercase after stripping surrounding whitespace. The configured field names and alias keys are already normalized.",
        "middle": "Ignore columns beyond the header count and omit missing cells. Canonical header columns win over aliases mapping to the same field, regardless of input order. Multiple candidates of the same precedence keep the leftmost source column. The old contract treated null and empty strings as winning cell values.",
        "latest": "A cell whose value is null or the empty string no longer competes for precedence. Omit a field when every candidate is absent, null, or empty. Preserve numeric zero, false and whitespace-only cell values verbatim.",
        "diagnosis": "ALIASED_FIELDS_DROPPED", "receipt": "IMP-422",
        "operation": "commit imports to the shared contacts database", "versions": ["column-mapping/5", "column-mapping/6"],
        "baseline": ({"headers":[" Name ","Tel","junk"],"fields":["name","phone"],"aliases":{"tel":"phone"},"rows":[["Z","7","junk"]]}, [{" Name ":"Z","Tel":"7","junk":"junk"}], [{"name":"Z","phone":"7"}]),
        "cases": [
            ({"headers":["n","name","NAME ","no","other"],"fields":["name"],"aliases":{"n":"name","no":"notallowed"},"rows":[["alias","primary","duplicate",8,7,2],["alias"],["a",None,"next"],[None,None,""]]}, [{"name":"primary"},{"name":"alias"},{"name":"next"},{}]),
            ({"headers":["alt","first","first"],"fields":["first"],"aliases":{"alt":"first"},"rows":[["fallback","",None],["fallback",False,3],["fallback",0,3],["fallback"," ",3]]}, [{"first":"fallback"},{"first":False},{"first":0},{"first":" "}]),
            ({"headers":["m","alt","other"],"fields":["field"],"aliases":{"m":"field","alt":"field"},"rows":[["left","right","junk"],[None,"right"],[]]}, [{"field":"left"},{"field":"right"},{}]),
            ({"headers":["field"],"fields":["field"],"aliases":{"field":"different"},"rows":[[9],[]]}, [{"field":9},{}]),
            ({"headers":[],"fields":["k"],"aliases":{},"rows":[[9],[]]}, [{},{}]),
        ],
    },
    "R07": {
        "title": "Repair deterministic integer fee allocation",
        "starter": '''
            def run(data):
                pieces = data["parts"]
                unit = data["total"] // len(pieces) if pieces else 0
                return {part["id"]: unit for part in pieces}
        ''',
        "first": "Distribute nonnegative integer `total` across parts with positive integer weights by exact proportional share. Return integer parts in an ID-to-amount mapping. Assign the leftover units to the largest fractional remainders, with ascending ID breaking ties under the old contract.",
        "middle": "Exclude weights that are zero or negative, and disabled parts (`enabled` explicitly false). Missing enabled means true. Empty eligible parts produce an empty object even when total is positive. Eligible parts with zero allocation remain visible.",
        "latest": "For equal fractional remainders, break ties by larger weight first, then ascending ID. Money must be allocated with exact integer arithmetic for arbitrarily large weights and totals.",
        "diagnosis": "FEE_WEIGHT_IGNORED", "receipt": "FEE-64",
        "operation": "submit the fee settlement", "versions": ["fee-split/1", "fee-split/2"],
        "baseline": ({"total":12,"parts":[{"id":"a","weight":1},{"id":"b","weight":3}]}, {"a":6,"b":6}, {"a":3,"b":9}),
        "cases": [
            ({"total":2,"parts":[{"id":"x","weight":3},{"id":"a","weight":1}]}, {"a":0,"x":2}),
            ({"total":1,"parts":[{"id":"b","weight":1},{"id":"a","weight":1},{"id":"c","weight":1}]}, {"a":1,"b":0,"c":0}),
            ({"total":3,"parts":[{"id":"a","weight":1,"enabled":True},{"id":"b","weight":0},{"id":"c","weight":2,"enabled":False},{"id":"d","weight":-2}]}, {"a":3}),
            ({"total":10**18+1,"parts":[{"id":"b","weight":10**18},{"id":"a","weight":10**18+1}]}, {"a":500000000000000001,"b":500000000000000000}),
            ({"total":7,"parts":[{"id":"a","weight":0}]}, {}),
        ],
    },
    "R08": {
        "title": "Resolve layered application preferences",
        "starter": '''
            def run(data):
                settings = {}
                for layer in data["layers"]:
                    settings.update(layer)
                return settings
        ''',
        "first": "Merge preference layers in input order. Nested objects merge recursively. Arrays and scalars replace earlier values completely. Any object after a non-object starts a fresh nested object. The old contract treated null as a literal replacement value.",
        "middle": "A layer's empty object merges with a prior object without erasing its existing keys. Empty objects replacing an absent or non-object value are preserved. Empty arrays and false are explicit replacements. Duplicate nested setting keys across layers are ordinary overrides.",
        "latest": "Null is now a deletion marker at any object depth. Omit the key when an override is null. A later layer may reintroduce a removed key without resurrecting deleted descendants. Null elements inside arrays are literal array contents.",
        "diagnosis": "LAYER_MERGE_LOSES_SIBLINGS", "receipt": "CFG-109",
        "operation": "apply preferences to the shared service", "versions": ["preference-overlay/9", "preference-overlay/10"],
        "baseline": ({"layers":[{"ui":{"font":12,"show":True}},{"ui":{"font":14}}]}, {"ui":{"font":14}}, {"ui":{"font":14,"show":True}}),
        "cases": [
            ({"layers":[{"a":{"x":1,"y":{"z":2}},"b":[1,2]},{"a":{"x":None,"y":{"q":3}},"b":[None]}]}, {"a":{"y":{"q":3,"z":2}},"b":[None]}),
            ({"layers":[{"a":{"x":1}},{"a":None},{"a":{"y":2,"z":None},"b":None}]}, {"a":{"y":2}}),
            ({"layers":[{"a":1,"b":{"k":2},"c":{"k":2}},{"a":{},"b":{},"c":False,"d":[]}]}, {"a":{},"b":{"k":2},"c":False,"d":[]}),
            ({"layers":[{"a":{"x":1}},{"a":[8]},{"a":{"x":None}}]}, {"a":{}}),
            ({"layers":[]}, {}),
        ],
    },
}


def main():
    builder.main()
    if sys.argv[1] == "generate":
        output = Path(sys.argv[2])
        ids = sys.argv[3:] or list(builder.CATALOG)
        lock = output / f"lock-{'-'.join(ids)}.json"
        data = builder.json.loads(lock.read_text(encoding="utf-8"))
        data["catalog_sha256"] = builder.hash_file(Path(__file__))
        builder.write_json(lock, data)


if __name__ == "__main__":
    main()
