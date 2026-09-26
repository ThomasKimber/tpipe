import math
import networkx as nx
import numpy as np

def to_simple_undirected(G):
    H = nx.Graph()
    H.add_nodes_from(G.nodes())
    H.add_edges_from((u, v) for u, v in G.edges())
    return H

def greedy_box_cover(H, lB):
    if lB < 1:
        raise ValueError("lB must be >= 1")

    # Standard network box-covering uses shortest-path distance.
    # Using radius r ensures nodes in a box are locally close.
    r = max((lB - 1) // 2, 0)

    # Shortest-path lengths up to radius r
    spl = {n: nx.single_source_shortest_path_length(H, n, cutoff=r) for n in H.nodes()}
    candidate_boxes = {n: set(d.keys()) for n, d in spl.items()}

    uncovered = set(H.nodes())
    chosen_boxes = []

    while uncovered:
        best_center = None
        best_cover = set()

        for center, box in candidate_boxes.items():
            cover = box & uncovered
            if len(cover) > len(best_cover):
                best_center = center
                best_cover = cover

        if not best_cover:
            node = uncovered.pop()
            chosen_boxes.append({node})
        else:
            chosen_boxes.append(candidate_boxes[best_center])
            uncovered -= candidate_boxes[best_center]

    return chosen_boxes

def box_count(H, lB):
    return len(greedy_box_cover(H, lB))

def estimate_fractal_dimension(G, lB_values=None):
    H = to_simple_undirected(G)

    if lB_values is None:
        diam = nx.diameter(H) if nx.is_connected(H) else max(
            nx.diameter(H.subgraph(c)) for c in nx.connected_components(H)
        )
        lB_values = list(range(1, min(diam + 1, 8)))

    counts = []
    for lB in lB_values:
        n_boxes = box_count(H, lB)
        if n_boxes > 0:
            counts.append((lB, n_boxes))

    if len(counts) < 2:
        return {"dimension": float("nan"), "counts": counts}

    x = np.log([c[0] for c in counts if c[0] > 0 and c[1] > 0])
    y = np.log([c[1] for c in counts if c[0] > 0 and c[1] > 0])

    slope, intercept = np.polyfit(x, y, 1)
    dB = -slope

    return {
        "dimension": dB,
        "counts": counts,
        "slope": slope,
        "intercept": intercept,
    }