"""Utility library for converting crude html content
into machine-readable text"""

import lxml.etree as ET
import lxml.html as lhtml
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
    'u', 'ul', 'code', 'samp', 'kbd', 'hr'
])

non_breaking_html_tags = set(['a', 'strong', 'em', 'b', 'i', 'u', 'mark', 'small',
 'sub', 'sup', 'var', 'cite', 'dfn', 'abbr', 'acronym', 'time', 'span', 'br'])

breaking_tags = all_html_tags-non_breaking_html_tags

ignore_html_tags = set(['script', 'code', 'meta', 'nav'])

class HTMLDocument(object):
    def __init__(self, html_content : str):
        self.html = html_content
        self.htree = lhtml.fromstring(html_content)
        self.xtree = self.htree.getroottree() 


def walk_tree(breaking_tags : set[str], 
              ignore_html_tags : set[str], 
              elem : HtmlElement, 
              text, 
              depth=0, 
              store=[]):
    """Walk over an html tree, extracting text while respecting
    breaking and non-breaking element tags. A breaking element
    tag results in text being assigned to a new position in 
    the output list, while a non-breaking element is concatenated
    onto the text being collected.
    The result should be a reasonably authentic split out of the
    paragraphs and sections found within a web-page."""
    if elem.tag in breaking_tags and text != "":
        store.append(text)
        text = ""

    for e in elem:
        if e.tag not in ignore_html_tags:
            text, store = walk_tree(breaking_tags, ignore_html_tags, e, text, depth+1, store)
            d = "    " * depth
            if e.text is not None:
                text = "".join([text, e.text ]).strip()
            if e.tail is not None:
                text = "".join([text, e.tail]).strip()
    return text, store
