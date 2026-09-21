import json
import sys
import uuid
import requests

BASE = "http://127.0.0.1:8188"

COL_W = 420
COL_GAP = 460  # col_w + horizontal breathing room
ROW_GAP = 40


def convert(api_path, out_path):
    with open(api_path) as f:
        api = json.load(f)

    node_ids = list(api.keys())
    info_cache = {}

    def get_info(class_type):
        if class_type not in info_cache:
            r = requests.get(f"{BASE}/object_info/{class_type}")
            r.raise_for_status()
            info_cache[class_type] = r.json()[class_type]
        return info_cache[class_type]

    # --- pass 1: raw dependency graph straight from the API json's link refs ---
    deps = {nid: set() for nid in node_ids}   # nid -> direct predecessor node ids
    dependents = {nid: set() for nid in node_ids}  # nid -> direct successor node ids
    for nid, node in api.items():
        for val in node["inputs"].values():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                src_id = val[0]
                deps[nid].add(src_id)
                dependents[src_id].add(nid)

    # --- pass 2: rank = longest path from a source (node with no deps) ---
    rank = {}

    def compute_rank(nid, seen=None):
        if nid in rank:
            return rank[nid]
        seen = seen or set()
        if nid in seen:
            return 0  # cycle guard, shouldn't happen in a real ComfyUI graph
        seen = seen | {nid}
        preds = deps[nid]
        rank[nid] = 0 if not preds else 1 + max(compute_rank(d, seen) for d in preds)
        return rank[nid]

    for nid in node_ids:
        compute_rank(nid)

    max_rank = max(rank.values())
    columns = {r: [nid for nid in node_ids if rank[nid] == r] for r in range(max_rank + 1)}

    # --- pass 3: barycenter sweeps to reduce edge crossings between adjacent columns ---
    order_pos = {nid: i for r in columns for i, nid in enumerate(columns[r])}

    def barycenter(nid, neighbor_set):
        neighbors = [order_pos[n] for n in neighbor_set if n in order_pos]
        return sum(neighbors) / len(neighbors) if neighbors else order_pos[nid]

    for _ in range(4):
        # left-to-right: order each column by the average position of its predecessors
        for r in range(1, max_rank + 1):
            columns[r].sort(key=lambda nid: barycenter(nid, deps[nid]))
            for i, nid in enumerate(columns[r]):
                order_pos[nid] = i
        # right-to-left: order each column by the average position of its successors
        for r in range(max_rank - 1, -1, -1):
            columns[r].sort(key=lambda nid: barycenter(nid, dependents[nid]))
            for i, nid in enumerate(columns[r]):
                order_pos[nid] = i

    links = []
    link_id_counter = [1]
    ui_nodes = []
    node_meta = {}  # nid -> (node_inputs, node_outputs, widgets_values, class_type)

    for nid in node_ids:
        node = api[nid]
        class_type = node["class_type"]
        info = get_info(class_type)

        input_order = list(info["input"].get("required", {}).keys()) + list(
            info["input"].get("optional", {}).keys()
        )
        output_types = info.get("output", [])
        output_names = info.get("output_name", output_types)

        node_inputs = []
        widgets_values = []

        for in_name in input_order:
            val = node["inputs"].get(in_name, None)
            is_link = isinstance(val, list) and len(val) == 2 and isinstance(val[0], str)
            if is_link:
                src_id, src_slot = val
                link_id = link_id_counter[0]
                link_id_counter[0] += 1
                src_info = get_info(api[src_id]["class_type"])
                src_out_types = src_info.get("output", [])
                link_type = src_out_types[src_slot] if src_slot < len(src_out_types) else "*"
                links.append([link_id, int(src_id), src_slot, int(nid), len(node_inputs), link_type])
                node_inputs.append({"name": in_name, "type": link_type, "link": link_id})
            else:
                if val is not None:
                    widgets_values.append(val)

        node_outputs = [
            {"name": (output_names[i] if i < len(output_names) else t), "type": t, "links": None}
            for i, t in enumerate(output_types)
        ]

        node_meta[nid] = (node_inputs, node_outputs, widgets_values, class_type)

    # --- sizing: rough content-based height so nodes aren't all the same padded box ---
    def node_size(node_inputs, node_outputs, widgets_values):
        socket_rows = max(len(node_inputs), len(node_outputs))
        long_text = any(isinstance(v, str) and len(v) > 40 for v in widgets_values)
        widget_rows = len(widgets_values) + (3 if long_text else 0)  # textarea eats more vertical space
        height = 60 + 26 * socket_rows + 26 * widget_rows
        width = 420 if long_text else COL_W
        return [width, max(120, height)]

    # --- positions: pack each column vertically by actual node height, using the
    # barycenter-swept order computed above ---
    positions = {}
    sizes = {}
    for r in range(max_rank + 1):
        y = 0
        for nid in columns[r]:
            node_inputs, node_outputs, widgets_values, _ = node_meta[nid]
            size = node_size(node_inputs, node_outputs, widgets_values)
            sizes[nid] = size
            positions[nid] = [r * COL_GAP, y]
            y += size[1] + ROW_GAP

    for nid in node_ids:
        node_inputs, node_outputs, widgets_values, class_type = node_meta[nid]
        ui_nodes.append(
            {
                "id": int(nid),
                "type": class_type,
                "pos": positions[nid],
                "size": sizes[nid],
                "flags": {},
                "order": 0,  # filled in below by true topological order
                "mode": 0,
                "inputs": node_inputs,
                "outputs": node_outputs,
                "properties": {"Node name for S&R": class_type},
                "widgets_values": widgets_values,
            }
        )

    # `order` must respect dependency order (a node can't execute before its inputs
    # exist) — sort by (rank, column position) rather than raw JSON key order.
    ui_nodes.sort(key=lambda n: (rank[str(n["id"])], order_pos[str(n["id"])]))
    for i, n in enumerate(ui_nodes):
        n["order"] = i

    node_by_id = {n["id"]: n for n in ui_nodes}
    for link in links:
        link_id, src_id, src_slot, _tgt_id, _tgt_slot, _type = link
        src_node = node_by_id[src_id]
        if src_slot < len(src_node["outputs"]):
            out = src_node["outputs"][src_slot]
            if out["links"] is None:
                out["links"] = []
            out["links"].append(link_id)

    ui_workflow = {
        "id": str(uuid.uuid4()),
        "revision": 0,
        "last_node_id": max(int(n) for n in node_ids),
        "last_link_id": link_id_counter[0] - 1,
        "nodes": ui_nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }

    with open(out_path, "w") as f:
        json.dump(ui_workflow, f, indent=2)
    print(f"wrote {out_path}: {len(ui_nodes)} nodes, {len(links)} links, {max_rank + 1} columns")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
