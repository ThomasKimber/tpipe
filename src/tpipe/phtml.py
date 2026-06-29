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
    attrs: dict = field(default_factory=dict)
    source_refs: list[SourceRef] = field(default_factory=list)

    def label(self):
        if self.node_type == "element":
            return self.tag
        elif self.node_type=="text":
            return f"({self.text_slot})\"{self.text}\""
        elif self.node_type=="comment":
            return f'<!--{self.text or ""}-->'
    
    def todict(self):
        return {k:v for k,v in asdict(self).items() if not k.startswith("_")}

class GraphBuilder:
    def __init__(self):
        self.g = nx.MultiDiGraph()
        self._ids = itertools.count(1)
    
    def new_id(self, prefix:str)->str:
        return f"{prefix}{next(self._ids)}"

    def add_element_node(self, el : _Element) -> str:
        node_id = self.new_id("e")
        xpath = el.getroottree().getpath(el)
        node_data = NodeData(
            node_type="element",
            tag = el.tag.lower() if isinstance(el.tag, str) else None,
            attrs = dict(el.attrib),
            source_refs=[SourceRef(xpath=xpath, tag=getattr(el, "tag", None))]
        )
        self.g.add_node(node_id, data=node_data)
        return node_id

    def add_text_node(self, text: str, slot: TextSlot, owner: _Element) -> str:
        node_id = self.new_id("t")
        xpath = owner.getroottree().getpath(owner)
        node_data = NodeData(
                node_type="text",
                text=text,
                text_slot=slot,
                source_refs=[SourceRef(xpath=xpath, tag=getattr(owner, "tag", None))]
            )
        self.g.add_node(
            node_id,
            data=node_data
        )
        return node_id
    
    def add_comment_node(self, el: _Element) -> str:
        node_id = self.new_id("c")
        xpath = el.getroottree().getpath(el)
        node_data = NodeData(
            node_type="comment",
            text=el.text,
            source_refs=[SourceRef(xpath=xpath, tag="#comment")],
        )
        self.g.add_node(node_id, data=node_data)
        return node_id

    def add_contains_link(self, parent_id: str, child_id: str, order: int):
        self.g.add_edge(parent_id, child_id, key=f"contains:{order}", kind="contains", order=order)

    def add_next_link(self, left_id: str, right_id: str):
        self.g.add_edge(left_id, right_id, key="next", kind="next")

    def build_from_element(self, el: _Element) -> str:
        if el.tag is Comment:
            return self.add_comment_node(el)

        parent_id = self.add_element_node(el)
        ordered_children = []

        if el.text is not None:
            text_id = self.add_text_node(el.text, "text", el)
            ordered_children.append(text_id)

        for child in el:
            child_id = self.build_from_element(child)
            ordered_children.append(child_id)

            if child.tail is not None:
                tail_id = self.add_text_node(child.tail, "tail", child)
                ordered_children.append(tail_id)

        for idx, child_id in enumerate(ordered_children):
            self.add_contains_link(parent_id, child_id, idx)

        for left, right in zip(ordered_children, ordered_children[1:]):
            self.add_next_link(left, right)

        return parent_id
    
def parse_html_root(source: str) -> HtmlElement:
    document = lhtml.fromstring(source)
    return document.getroottree().getroot()

def html_to_graph(source: str) -> nx.MultiDiGraph:
    root = parse_html_root(source)
    builder = GraphBuilder()
    builder.build_from_element(root)
    return builder.g


def ordered_children(G, parent_id):
    children = []
    for _, child_id, _, data in G.out_edges(parent_id, keys=True, data=True):
        if data.get("kind") == "contains":
            children.append((data["order"], child_id))
    return [child for _, child in sorted(children, key=lambda x: x[0])]

def walk_reconstruction(G, node_id) -> Iterator[str]:
    yield node_id
    for child_id in ordered_children(G, node_id):
        yield from walk_reconstruction(G, child_id)


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

def add_ordered_children(out: nx.MultiDiGraph, parent_id: str, child_ids: list[str]) -> None:
    for idx, child_id in enumerate(child_ids):
        out.add_edge(parent_id, child_id, key=f"contains:{idx}", kind="contains", order=idx)
    for left, right in zip(child_ids, child_ids[1:]):
        out.add_edge(left, right, key="next", kind="next")

def new_like_node_id(node_id: str, counters: dict[str, int]) -> str:
    prefix = node_id[:1] if node_id else "n"
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}n{counters[prefix]}"
# ============================================================


def serialize_attrs(attrs: dict) -> str:
    if not attrs:
        return ""
    parts = []
    for key, value in attrs.items():
        if value is None:
            continue
        parts.append(f' {key}="{escape(str(value), quote=True)}"')
    return "".join(parts)

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
    attrs = serialize_attrs(data.attrs)

    if tag in VOID_TAGS:
        return f"<{tag}{attrs}>"

    inner = []
    for child_id in ordered_children(G, node_id):
        inner.append(_serialize_html_node(G, child_id, parent_tag=tag))

    return f"<{tag}{attrs}>{''.join(inner)}</{tag}>"


NORMALISATION_RULES = {
    "PRUNE" : { "script", "style", "noscript", "nav", },
    "UNWRAP" : { "b", "i", "span", "font" }
}

# Rewrite Functions
# =====================================================================
def default_mutate(
    G_in: nx.MultiDiGraph,
    G_out: nx.MultiDiGraph,
    node_id: str,
    rewritten_children: list[str],
    counters: dict[str, int],
    rules: dict
) -> list[str]:
    data = get_node_data(G_in, node_id)

    if data.node_type == "comment":
        return []

    if data.node_type == "text":
        text = data.text or ""
        if not text.strip():
            return []
        new_id = new_like_node_id(node_id, counters)
        G_out.add_node(new_id, data=clone_node_data_with_sources(data))
        return [new_id]

    if data.node_type != "element":
        return []

    tag = (data.tag or "").lower()

    if tag in rules.get("PRUNE", set()):
        return []

    if tag in rules.get("UNWRAP", set()):
        source_refs = data.source_refs
        for child_id in rewritten_children:
            child_data = get_node_data(G_out, child_id)
            child_data.source_refs = clone_node_data_with_sources(
                child_data,
                extra_sources=source_refs
            ).source_refs
        return rewritten_children

    new_id = new_like_node_id(node_id, counters)
    new_data = clone_node_data_with_sources(data)
    G_out.add_node(new_id, data=new_data)
    add_ordered_children(G_out, new_id, rewritten_children)
    return [new_id]


def rewrite_subtree(
    G_in: nx.MultiDiGraph,
    G_out: nx.MultiDiGraph,
    node_id: str,
    mutate: Callable,
    counters: dict[str, int],
    rules: dict
) -> list[str]:
    rewritten_children = []
    for child_id in ordered_children(G_in, node_id):
        rewritten_children.extend(
            rewrite_subtree(G_in, G_out, child_id, mutate, counters, rules)
        )
    return mutate(G_in, G_out, node_id, rewritten_children, counters, rules)
# =========================================================================

def normalise_graph(
    G_in: nx.MultiDiGraph,
    rules: Optional[dict] = None,
    mutate: Optional[Callable] = None
) -> nx.MultiDiGraph:
    rules = rules or NORMALISATION_RULES
    mutate = mutate or default_mutate

    G_out = nx.MultiDiGraph()
    G_out.graph.update(deepcopy(G_in.graph))

    counters: dict[str, int] = {}
    old_root = root_node_id(G_in)
    new_roots = rewrite_subtree(G_in, G_out, old_root, mutate, counters, rules)

    if not new_roots:
        synthetic_root = "en1"
        G_out.add_node(
            synthetic_root,
            data=NodeData(
                node_type="element",
                tag="div",
                attrs={},
                source_refs=[]
            )
        )
        G_out.graph["root"] = synthetic_root
        return G_out

    if len(new_roots) == 1:
        G_out.graph["root"] = new_roots[0]
        return G_out

    synthetic_root = "en1"
    G_out.add_node(
        synthetic_root,
        data=NodeData(
            node_type="element",
            tag="div",
            attrs={},
            source_refs=[]
        )
    )
    add_ordered_children(G_out, synthetic_root, new_roots)
    G_out.graph["root"] = synthetic_root
    return G_out

