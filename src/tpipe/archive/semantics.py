"""A library of classification functions 
to be applied to Spacy span objects in 
order to collect meta-data and classify
them prior to more focused processing."""

from collections.abc import Iterable

import spacy
import spacy.tokens



def extract_matching_pos_instances(sentence : spacy.tokens.Span, p_types : Iterable[str]) -> list[str]:
    """Given a span and a set of d_types, return a list 
    of POS values found in the span."""
    matches = [t.pos_
            for t in sentence
            if t.pos_ in p_types]
    return matches

def extract_matching_dependency_instances(sentence : spacy.tokens.Span, d_types : Iterable[str]) -> list[str]:
    """Given a span and a set of d_types, return a list 
    of d_types found in the span."""
    matches = [ t.dep_
            for f,t in enumerate(sentence)
            if t.dep_ in d_types]
    return matches

def extract_tokens_linked_by_dependency(sentence : spacy.tokens.Span, d_types : Iterable[str]) -> list[spacy.tokens.Token]:
    matches = [t
            for t in sentence
            if t.dep_ in d_types]
    return matches

def extract_tokens_with_pos(sentence : spacy.tokens.Span, p_types : Iterable[str]) -> list[spacy.tokens.Token]:
    matches = [t
            for t in sentence
            if t.pos_ in p_types]
    return matches

def is_sentence(sentence : spacy.tokens.Span) -> bool:
    """Accept a span of content that Spacey has deemed to be
    a sentence-chunk and apply a heuristic test for contents 
    that make it likely to be a 'proper' sentence.
    Heuristic: A sentence contains at least one noun and
    at least one verb."""
    has_noun = any_pos_in_sentence(sentence, ('NOUN','PROPN', 'PRON'))
    has_verb = any_pos_in_sentence(sentence, ('VERB'))
    if has_noun and has_verb:
        return True
    else:
        return False
    
def contains_rooted_verb(sentence: spacy.tokens.Span) -> bool:
    root_t = extract_tokens_linked_by_dependency(sentence, ["ROOT"])
    for t in root_t:
        if t.pos_ in ['VERB','AUX']:
            return True
    return False

def contains_subject(sentence: spacy.tokens.Span) -> bool:
    subj_t = extract_tokens_linked_by_dependency(sentence, ['nsubj', 'nsubjpass'])
    return any([t for t in subj_t])

def contains_object(sentence: spacy.tokens.Span) -> bool:
    subj_t = extract_tokens_linked_by_dependency(sentence, ['dobj', 'pobj'])
    return any([t for t in subj_t])

def contains_appos(sentence: spacy.tokens.Span) -> bool:
    appos_t = extract_tokens_linked_by_dependency(sentence, ['appos'])
    return any([t for t in appos_t])

def contains_pronoun(sentence: spacy.tokens.Span) -> bool:
    return any_pos_in_sentence(sentence, ('PRON'))

def likely_question(sentence: spacy.tokens.Span) -> bool:
    ends_in_q_mark = str(sentence).strip()[-1]=="?"
    return ends_in_q_mark

def contains_quotes(sentence: spacy.tokens.Span) -> bool:
    quote_marks = "“”\"‘’'"
    any_quotes = any([
        True 
        for t in sentence
        if 
            any([q in t.text for q in quote_marks]) and
            t.pos_ != 'PART'
    ])
    return any_quotes


def all_dependencies_in_sentence(sentence : spacy.tokens.Span, d_types : Iterable[str]) -> bool:
    return all([m in d_types for m in extract_matching_dependency_instances(sentence, d_types)])

def any_dependencies_in_sentence(sentence : spacy.tokens.Span, d_types : Iterable[str]) -> bool:
    return any([m in d_types for m in extract_matching_dependency_instances(sentence, d_types)])

def all_pos_in_sentence(sentence : spacy.tokens.Span, p_types : Iterable[str]) -> bool:
    return all([m in p_types for m in extract_matching_pos_instances(sentence, p_types)])

def any_pos_in_sentence(sentence : spacy.tokens.Span, p_types : Iterable[str]) -> bool:
    return any([m in p_types for m in extract_matching_pos_instances(sentence, p_types)])


