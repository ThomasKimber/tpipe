import lxml.html as lhtml
from lxml.html import HtmlElement
from lxml.etree import _Element, Comment
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal, Callable, Iterator
import itertools
import networkx as nx
from html import escape
from copy import deepcopy


NodeType = Literal["element", "text", "comment"]
TextSlot = Literal["text", "tail"]

@dataclass
class SourceRef:
    xpath: str
    tag: Optional[str] = None

@dataclass
class NodeData:
    node_type: NodeType
    tag: Optional[str] = None
    text: Optional[str] = None
    text_slot: Optional[TextSlot] = None
    attributes: dict = field(default_factory=dict)
    source_refs: list[SourceRef] = field(default_factory=list)
    node_metrics: dict = field(default_factory=dict)
    subtree_metrics: dict = field(default_factory=dict)

    def label(self) -> str | None:
        if self.node_type == "element":
            return self.tag
        if self.node_type=="text":
            return f"({self.text_slot})\"{self.text}\""
        if self.node_type=="comment":
            return f'<!--{self.text or ""}-->'
    
    def to_dict(self) -> dict:
        return {k:v for k,v in asdict(self).items() if not k.startswith("_")}

class GraphBuilder:
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self._ids = itertools.count(1)
    
    def new_node_id(self, prefix:str)->str:
        return f"{prefix}{next(self._ids)}"

    def add_element_node(self, el : _Element) -> str:
        node_id = self.new_node_id("e")
        xpath = el.getroottree().getpath(el)
        node_data = NodeData(
            node_type="element",
            tag = el.tag.lower() if isinstance(el.tag, str) else None,
            attributes = dict(el.attrib),
            source_refs=[SourceRef(xpath=xpath, tag=getattr(el, "tag", None))]
        )
        self.graph.add_node(node_id, data=node_data)
        return node_id

    def add_text_node(self, text: str, slot: TextSlot, owner: _Element) -> str:
        node_id = self.new_node_id("t")
        xpath = owner.getroottree().getpath(owner)
        node_data = NodeData(
                node_type="text",
                text=text,
                text_slot=slot,
                source_refs=[SourceRef(xpath=xpath, tag=getattr(owner, "tag", None))]
            )
        self.graph.add_node(
            node_id,
            data=node_data
        )
        return node_id
    
    def add_comment_node(self, el: _Element) -> str:
        node_id = self.new_node_id("c")
        xpath = el.getroottree().getpath(el)
        node_data = NodeData(
            node_type="comment",
            text=el.text,
            source_refs=[SourceRef(xpath=xpath, tag="#comment")],
        )
        self.graph.add_node(node_id, data=node_data)
        return node_id

    def add_contains_edge(self, parent_id: str, child_id: str, order: int):
        self.graph.add_edge(parent_id, child_id, key=f"contains:{order}", kind="contains", order=order)

    def build_subtree(self, el: _Element) -> str:
        if el.tag is Comment:
            return self.add_comment_node(el)

        parent_id = self.add_element_node(el)
        ordered_children = []

        if el.text is not None:
            text_id = self.add_text_node(el.text, "text", el)
            ordered_children.append(text_id)

        for child in el:
            child_id = self.build_subtree(child)
            ordered_children.append(child_id)

            if child.tail is not None:
                tail_id = self.add_text_node(child.tail, "tail", child)
                ordered_children.append(tail_id)

        for idx, child_id in enumerate(ordered_children):
            self.add_contains_edge(parent_id, child_id, idx)

        return parent_id
    
def parse_html_root(source: str,
                    preserve_fragments: Optional[bool]) -> HtmlElement:
    if preserve_fragments:
        document = lhtml.fragments_fromstring(source)    
    else:
        document = lhtml.fromstring(source)
    return document.getroottree().getroot()

def html_to_graph(source: str, 
                  preserve_fragments: Optional[bool]) -> nx.MultiDiGraph:
    root = parse_html_root(source, preserve_fragments)
    builder = GraphBuilder()
    builder.build_subtree(root)
    rebuild_next_edges(builder.graph)
    return builder.graph


def get_ordered_children(G, parent_id):
    children = []
    for _, child_id, _, data in G.out_edges(parent_id, keys=True, data=True):
        if data.get("kind") == "contains":
            children.append((data["order"], child_id))
    return [child for _, child in sorted(children, key=lambda x: x[0])]

def walk_subtree(G, node_id) -> Iterator[str]:
    yield node_id
    for child_id in get_ordered_children(G, node_id):
        yield from walk_subtree(G, child_id)


def get_node_data(G, node_id):
    node = G.nodes[node_id]
    return node.get("data", node)

# Normalisation Builder helper functions:
# ============================================================
def root_node_id(G) -> str:
    for node_id in G.nodes:
        if G.in_degree(node_id) == 0:
            return node_id
    raise ValueError("Graph has no root node")

def clone_node_data_with_sources(data: NodeData, extra_sources: Optional[list[SourceRef]] = None) -> NodeData:
    cloned = deepcopy(data)
    if extra_sources:
        existing = {(ref.xpath, ref.tag) for ref in cloned.source_refs}
        for ref in extra_sources:
            key = (ref.xpath, ref.tag)
            if key not in existing:
                cloned.source_refs.append(ref)
                existing.add(key)
    return cloned

def add_ordered_children(out: nx.MultiDiGraph, 
                         parent_id: str, 
                         child_ids: list[str]) -> None:
    for idx, child_id in enumerate(child_ids):
        out.add_edge(parent_id, 
                     child_id, 
                     key=f"contains:{idx}", 
                     kind="contains", 
                     order=idx)

def new_rewritten_node_id(node_id: str, counters: dict[str, int]) -> str:
    prefix = node_id[:1] if node_id else "n"
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}n{counters[prefix]}"

# ============================================================



def serialize_attributes(attributes: dict) -> str:
    if not attributes:
        return ""
    parts = []
    for key, value in attributes.items():
        if value is None:
            continue
        parts.append(f' {key}="{escape(str(value), quote=True)}"')
    return "".join(parts)

# TAGS that are optionally self-closing
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
}

RAW_TEXT_TAGS = {"script", "style"}

def serialize_html_node(G, node_id) -> str:
    return _serialize_html_node(G, node_id, parent_tag=None)

def _serialize_html_node(G, node_id, parent_tag=None) -> str:
    data = get_node_data(G, node_id)

    if data.node_type == "text":
        if parent_tag in RAW_TEXT_TAGS:
            return data.text or ""
        return escape(data.text or "")

    if data.node_type == "comment":
        return f"<!--{data.text or ''}-->"

    if data.node_type != "element":
        return ""

    tag = data.tag or "div"
    attributes = serialize_attributes(data.attributes)

    if tag in VOID_TAGS:
        return f"<{tag}{attributes}>"

    inner = []
    for child_id in get_ordered_children(G, node_id):
        inner.append(_serialize_html_node(G, child_id, parent_tag=tag))

    return f"<{tag}{attributes}>{''.join(inner)}</{tag}>"


NORMALISATION_RULES = {
    "PRUNE" : { "script", "style", "noscript", "nav", "aside", "footer"},
    "UNWRAP" : { "b", "i", "span", "font" }
}

# Rewrite Functions
# =====================================================================
def default_rewrite_node(
    input_graph: nx.MultiDiGraph,
    output_graph: nx.MultiDiGraph,
    node_id: str,
    rewritten_children: list[str],
    counters: dict[str, int],
    rules: dict
) -> list[str]:
    data = get_node_data(input_graph, node_id)

    if data.node_type == "comment":
        return []

    if data.node_type == "text":
        text = data.text or ""
        if not text.strip():
            return []
        new_node_id = new_rewritten_node_id(node_id, counters)
        output_graph.add_node(new_node_id, data=clone_node_data_with_sources(data))
        return [new_node_id]

    if data.node_type != "element":
        return []

    tag = (data.tag or "").lower()

    if tag in rules.get("UNWRAP", set()):
        source_refs = data.source_refs
        for child_id in rewritten_children:
            child_data = get_node_data(output_graph, child_id)
            child_data.source_refs = clone_node_data_with_sources(
                child_data,
                extra_sources=source_refs
            ).source_refs
        return rewritten_children

    new_node_id = new_rewritten_node_id(node_id, counters)
    new_data = clone_node_data_with_sources(data)
    if tag in rules.get("PRUNE", set()):
        new_data.attributes = dict(new_data.attributes or {})
        new_data.attributes["_prune_root"] = True

    output_graph.add_node(new_node_id, data=new_data)
    add_ordered_children(output_graph, new_node_id, rewritten_children)

    return [new_node_id]


def rewrite_node_subtree(
    input_graph: nx.MultiDiGraph,
    output_graph: nx.MultiDiGraph,
    node_id: str,
    mutate: Callable,
    counters: dict[str, int],
    rules: dict
) -> list[str]:
    rewritten_children = []
    for child_id in get_ordered_children(input_graph, node_id):
        rewritten_children.extend(
            rewrite_node_subtree(input_graph, output_graph, child_id, mutate, counters, rules)
        )
    return mutate(input_graph, output_graph, node_id, rewritten_children, counters, rules)
# =========================================================================

def sweep_pruned_subtrees(graph: nx.MultiDiGraph) -> None:

    contains = nx.DiGraph(
        (u, v)
        for u, v, _, d in graph.edges(keys=True, data=True)
        if d.get("kind") == "contains"
    )

    prune_roots_set = [
        n for n, nd in graph.nodes(data=True)
        if (dict(nd["data"].attributes or {})).get("_prune_root")
    ]

    prune_roots = [
        n for n in prune_roots_set
        if not any(
            p in prune_roots_set
            for p, _, _, d in graph.in_edges(n, keys=True, data=True)
            if d.get("kind") == "contains"
        )
    ]

    doomed = set()
    for n in prune_roots:
        doomed.add(n)
        doomed.update(nx.descendants(contains, n))

    graph.remove_nodes_from(doomed)

def rebuild_next_edges(graph: nx.MultiDiGraph) -> None:
    next_edges_to_remove = [
        (u, v, k)
        for u, v, k, d in graph.edges(keys=True, data=True)
        if d.get("kind") == "next"
    ]
    graph.remove_edges_from(next_edges_to_remove)

    children_by_parent: dict[str, list[tuple[int, str]]] = {}

    for parent_id, child_id, key, data in graph.edges(keys=True, data=True):
        if data.get("kind") != "contains":
            continue
        order = data.get("order", 0)
        children_by_parent.setdefault(parent_id, []).append((order, child_id))

    for parent_id, ordered_children in children_by_parent.items():
        ordered_children.sort(key=lambda x: x[0])
        child_ids = [child_id for _, child_id in ordered_children]

        for left, right in zip(child_ids, child_ids[1:]):
            graph.add_edge(
                left,
                right,
                key=f"next:{left}:{right}",
                kind="next",
            )


def normalise_graph(
    input_graph: nx.MultiDiGraph,
    rules: Optional[dict] = None,
    rewrite_func: Optional[Callable] = None
) -> nx.MultiDiGraph:
    
    rules = rules or NORMALISATION_RULES
    rewrite_func = rewrite_func or default_rewrite_node

    output_graph = nx.MultiDiGraph()
    output_graph.graph.update(deepcopy(input_graph.graph))

    counters: dict[str, int] = {}
    old_root = root_node_id(input_graph)
    new_roots = rewrite_node_subtree(input_graph, output_graph, old_root, rewrite_func, counters, rules)

    if not new_roots:
        synthetic_root = "en1"
        output_graph.add_node(
            synthetic_root,
            data=NodeData(
                node_type="element",
                tag="div",
                attributes={},
                source_refs=[]
            )
        )
        output_graph.graph["root"] = synthetic_root
        
    else:

        if len(new_roots) == 1:
            output_graph.graph["root"] = new_roots[0]
        else:
            # Happy Path - new_roots returned with sub_tree contents of size > 1
            synthetic_root = "en1"
            output_graph.add_node(
                synthetic_root,
                data=NodeData(
                    node_type="element",
                    tag="div",
                    attributes={},
                    source_refs=[]
                )
            )
            add_ordered_children(output_graph, synthetic_root, new_roots)
            output_graph.graph["root"] = synthetic_root


    sweep_pruned_subtrees(output_graph)
    rebuild_next_edges(output_graph)
    return output_graph
