import lxml.html as lhtml
from lxml_html_clean import Cleaner
from lxml.html import HtmlElement



all_html_tags = set([
    'a', 'article', 'aside', 
    'b', 'body', 'button', 
    'caption','colgroup',
    'div', 
    'figcaption', 'figure', 'footer', 
    'g', 
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'html', 
    'img', 
    'li', 'link', 
    'main', 'meta', 
    'nav', 'noscript', 
    'ol', 
    'p', 'path', 'picture', 
    'script', 'source', 'span', 'style', 'svg', 
    'table', 'tbody', 'thead', 'tfoot', 'th','tr','td','time', 'title', 
    'ul', 'code', 'samp', 'kbd', 'hr'
])

non_breaking_html_tags = set(['a', 'strong', 'em', 'b', 'i', 'u', 'mark', 'small',
 'sub', 'sup', 'var', 'cite', 'dfn', 'abbr', 'acronym', 'time', 'span', 'br'])

ignore_html_tags = set(['script', 'code', 'meta', 'nav'])

breaking_tags = all_html_tags-non_breaking_html_tags


def create_cleaner():
    cleaner_remove_tags = ['strong', 'em', 'b', 'i', 'u', 'mark', 'small',
    'sub', 'sup', 'var', 'cite', 'dfn', 'abbr', 'acronym', 'time', 'span', 'br', 'img']

    cleaner_kill_tags = ['meta', 'style', 'nav', 'fieldset']

    cleaner = Cleaner(kill_tags = cleaner_kill_tags, 
                        remove_tags = cleaner_remove_tags, 
                        safe_attrs_only=True, 
                        safe_attrs=['href', 'class'],
                        page_structure=False, 
                        comments=True)
    return cleaner


def get_xpath_leaves(html):
    tree = lhtml.fromstring(html)
    leaf_set = set()
    # Extract all leaf elements
    leaf_elements = tree.xpath('//*[not(*)]')
    for elem in leaf_elements:
        leaf_set.add(elem.getroottree().getpath(elem))
    return leaf_set

def xpathToNodeIds(x_path_list : list[str]) -> list[str]:
    nodes = []
    
    for p in x_path_list:
        partial_node=""
        for n in p.split("/"):
            if n!="":
                nodes.append ("/".join([partial_node, n]))
                partial_node = "/".join([partial_node, n])
    return nodes

#def path_id_to_graph(path_id_list : list[str])->nx.DiGraph:
#    """Quick function to convert a path_list into a networkx graph"""
#    dg = nx.DiGraph()
#    for e,pid in enumerate(path_id_list):
#        parent_pid = "/".join([p for p in pid.split("/")[:-1]])
#        if pid not in dg.nodes():
#            dg.add_node(pid)
#            if parent_pid != "":
#                dg.add_edge(parent_pid, pid, sequence=e)
#            
#    return dg

def html_to_HtmlElement(html: str)-> HtmlElement:
    htree=lhtml.fromstring(html)
    xtree=htree.getroottree()
    root_element = xtree.xpath('/html')[0]
    return root_element

def normalise_whitespace(xstring: str)->str:
    """Convert a string containing large volumes of whitespace at
    either end to one where the whitespace is condensed to a single
    space. 
    Additionally, convert \\xa0 characters into normal spaces"""
    xstring = xstring.replace("\xa0", " ")
    if xstring.strip()=="":
        return ""
    if len(xstring.lstrip())<len(xstring):
        xstring=" "+xstring.lstrip()
    if len(xstring.rstrip())<len(xstring):
        xstring=xstring.rstrip()+" "
    return xstring
    


def simple_walk_tree(elem: HtmlElement, 
                     breaking_tags: set[str],
                     ignore_html_tags: set[str],
                     xpath: str, 
                     depth: int = 0, 
                     store: list[tuple[str, str, str, int, str]] = [])->list[tuple[str, str, str, int, str]]:

    if elem.tag in breaking_tags:
        store.append((elem.tag, xpath, 'break', depth, ""))

    if elem.text:
        text=normalise_whitespace(elem.text)
    else:
        text=None
    if text:
        text = normalise_whitespace(elem.text)
    else:
        text=""
    store.append((elem.tag, xpath, 'head', depth, text))
        
    for i, e in enumerate(elem):
        if e.tag not in ignore_html_tags:
            # Build the XPath for the child element
            child_xpath = e.getroottree().getpath(e)
            simple_walk_tree(e, breaking_tags, ignore_html_tags, child_xpath, depth+1, store)
    if elem.tail:
        text = normalise_whitespace(elem.tail)
        if text:
            store.append((elem.tag, xpath, 'tail', depth, text))
    return store

def consolidate_text(tree_walk_store: list[tuple[str, str, str, int, str]]):
    
    sequence_mapping={}
    
    for e,c in enumerate(tree_walk_store):
        if c[1] in sequence_mapping:
            sequence_mapping[c[1]].append(e)
        else:
            sequence_mapping[c[1]]=[e]
            
    inverse_node_mapping = {i:k for k,v in sequence_mapping.items() for i in v}


    node_mappings = {}
    for e, store_content in enumerate(tree_walk_store):
        tag, xpath, cue, depth, content = store_content
        if xpath in node_mappings:
            node_mappings[xpath]={**node_mappings[xpath], **{cue : content}, **{"sequence" : sequence_mapping[xpath]}}
        else:
            node_mappings[xpath]={**{cue : content}, **{"sequence" : sequence_mapping[xpath]}}

    visited_nodes = set()
    content_reform = {}
    parent_lookup = {}
    xpath_key=None
    oseq=-1
    new_sequence_mapping={}
    for e, store_content in enumerate(tree_walk_store):
        #node, data = inverse_node_mapping.get(e), tree_graph.nodes(data=True)[inverse_node_mapping.get(e)]
        node, data = inverse_node_mapping.get(e), node_mappings[inverse_node_mapping.get(e)]
        if e in data.get('sequence',[]):
            if node not in visited_nodes:
                
                if 'break' in data:
                    
                    xpath_key = node
                    content_reform[node]=[""]
                    oseq=oseq+1
                    new_sequence_mapping[node]=[oseq]
                    
                
                parent_lookup[node]=xpath_key # build a lookup back to the parent established for this node

                if 'head' in data and data['head']!="":

                    if xpath_key==node:
                        content_reform[xpath_key][0] = " ".join([content_reform[xpath_key][0], data['head']])
                    else:
                        content_reform[xpath_key][0] = "".join([content_reform[xpath_key][0], data['head']])
    #            if 'tail' in data and data['tail']!='':
    #                if node in parent_lookup:
    #                    content_reform[parent_lookup[node]] = content_reform[parent_lookup[node]] + data['tail']
    #                else:
    #                    content_reform[xpath_key] = content_reform[xpath_key] + data['tail']


            else:
                seq = data.get('sequence',[])
                if 'tail' in data and data['tail']!='' and e==seq[-1]:
                    breaking_backtrack  = any([s[2]=='break' for e,s in enumerate(tree_walk_store) if e in range(seq[0]+1,seq[-1]+1)])
                    if node in parent_lookup and not breaking_backtrack:
                        #print(f"tail:{node}, {xpath_key}, {last_xpath_key}, {data}")
                        content_reform[parent_lookup[node]][0] = "".join([content_reform[parent_lookup[node]][0],  data['tail']])
                    else:
                        oseq=oseq+1
                        new_sequence_mapping[parent_lookup[node]].append(oseq)
                        if len(content_reform[parent_lookup[node]])==1:
                            content_reform[parent_lookup[node]].append(data['tail'])
                        elif len(content_reform[parent_lookup[node]])==2:
                            print(f"{node}, {xpath}, {xpath_key}")
                            content_reform[parent_lookup[node]][1] = content_reform[parent_lookup[node]][1] + data['tail']

            last_xpath_key = xpath_key
        
        visited_nodes.add(node)


    results = {k:(new_sequence_mapping[k],v) for k,v in content_reform.items()} # Possible cleanup opportunity to remove/renumber those sequence numbers that aren't blank

    return results