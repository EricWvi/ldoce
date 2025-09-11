"""Word processing utilities for spell checking and inflection"""

import inflect
from spellchecker import SpellChecker
import re
from typing import List


# Initialize global instances
inflect_engine = inflect.engine()
spellchecker = SpellChecker()


def plural_to_singular(word: str) -> str:
    """Convert plural word to singular, return original if not plural"""
    singular = inflect_engine.singular_noun(word)
    if not singular:
        return word
    return singular


def spell_correct(word: str) -> str:
    """Get spell-corrected version of word"""
    corrected = spellchecker.correction(word)
    return corrected if corrected else word


def enhanced_word_lookup(db_instance, word: str) -> List[str]:
    """
    Enhanced word lookup with fallback strategies:
    1. Exact match (lowercase)
    2. Plural to singular conversion
    3. Spell correction
    4. Uppercase
    5. Handle @@@LINK= redirects
    """
    if not word:
        return []
    
    original_word = word
    word = word.lower()
    
    # Strategy 1: Exact match
    results = db_instance.mdx_lookup(word)
    
    # Strategy 2: Plural to singular
    if not results:
        singular_word = plural_to_singular(word)
        if singular_word != word:
            results = db_instance.mdx_lookup(singular_word)
    
    # Strategy 3: Spell correction
    if not results:
        corrected_word = spell_correct(word)
        if corrected_word != word:
            results = db_instance.mdx_lookup(corrected_word)
    
    # Strategy 4: Uppercase
    if not results:
        results = db_instance.mdx_lookup(original_word.upper())
    
    if not results:
        return []
    
    # Handle @@@LINK= redirects
    first_result = results[0]
    link_pattern = re.compile(r"@@@LINK=([\w\s]*)")
    match = link_pattern.match(first_result)
    
    if match:
        link_word = match.group(1).strip()
        results = db_instance.mdx_lookup(link_word)
        if not results:
            return []
    
    # Clean up results
    processed_results = []
    for result in results:
        cleaned = result.replace("\r\n", "").replace("entry:/", "")
        processed_results.append(cleaned)
    
    return processed_results