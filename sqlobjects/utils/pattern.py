import re


__all__ = ["pluralize", "singularize", "is_plural"]


# Irregular plural forms - words that don't follow standard rules
IRREGULAR_PLURALS: dict[str, str] = {
    # Person/People
    "person": "people",
    "man": "men",
    "woman": "women",
    "child": "children",
    "human": "humans",
    # Animals
    "mouse": "mice",
    "goose": "geese",
    "foot": "feet",
    "tooth": "teeth",
    "ox": "oxen",
    "louse": "lice",
    # Special cases
    "datum": "data",
    "medium": "media",
    "curriculum": "curricula",
    "memorandum": "memoranda",
    "bacterium": "bacteria",
    "criterion": "criteria",
    "phenomenon": "phenomena",
    "analysis": "analyses",
    "basis": "bases",
    "crisis": "crises",
    "diagnosis": "diagnoses",
    "ellipsis": "ellipses",
    "hypothesis": "hypotheses",
    "oasis": "oases",
    "parenthesis": "parentheses",
    "synopsis": "synopses",
    "thesis": "theses",
    # Additional irregular forms
    "die": "dice",
    "penny": "pennies",
    "quiz": "quizzes",
    "genus": "genera",
    "corpus": "corpora",
    "opus": "opera",
    "octopus": "octopi",
    "platypus": "platypuses",
    "hippopotamus": "hippopotamuses",
    "rhinoceros": "rhinoceroses",
    # Latin/Greek origins
    "alumnus": "alumni",
    "cactus": "cacti",
    "focus": "foci",
    "fungus": "fungi",
    "nucleus": "nuclei",
    "radius": "radii",
    "stimulus": "stimuli",
    "syllabus": "syllabi",
    "terminus": "termini",
    "index": "indices",
    "matrix": "matrices",
    "vertex": "vertices",
    "appendix": "appendices",
    # -f/-fe endings
    "knife": "knives",
    "life": "lives",
    "wife": "wives",
    "half": "halves",
    "leaf": "leaves",
    "loaf": "loaves",
    "shelf": "shelves",
    "thief": "thieves",
    "wolf": "wolves",
    "calf": "calves",
    "elf": "elves",
    "scarf": "scarves",
    "wharf": "wharves",
}

# Words that are the same in singular and plural
UNCOUNTABLE_WORDS: set[str] = {
    # Animals
    "sheep",
    "deer",
    "fish",
    "moose",
    "swine",
    "bison",
    "buffalo",
    "duck",
    "pike",
    "salmon",
    "trout",
    "squid",
    "aircraft",
    # Materials/Substances
    "rice",
    "wheat",
    "corn",
    "barley",
    "oats",
    "sugar",
    "salt",
    "water",
    "milk",
    "oil",
    "butter",
    "cheese",
    "bread",
    "meat",
    "beef",
    "pork",
    "chicken",
    "seafood",
    # Abstract concepts
    "information",
    "news",
    "advice",
    "progress",
    "research",
    "knowledge",
    "wisdom",
    "intelligence",
    "experience",
    "evidence",
    "proof",
    "truth",
    "justice",
    "peace",
    "happiness",
    "sadness",
    "anger",
    "fear",
    "love",
    "hate",
    "beauty",
    "ugliness",
    "strength",
    "weakness",
    # Activities/Fields
    "homework",
    "housework",
    "work",
    "employment",
    "business",
    "economics",
    "mathematics",
    "physics",
    "chemistry",
    "biology",
    "history",
    "geography",
    "literature",
    "music",
    "art",
    "politics",
    "athletics",
    "gymnastics",
    # Materials
    "gold",
    "silver",
    "copper",
    "iron",
    "steel",
    "wood",
    "paper",
    "plastic",
    "glass",
    "cotton",
    "wool",
    "silk",
    "leather",
    # Weather
    "weather",
    "rain",
    "snow",
    "sunshine",
    "wind",
    "fog",
    # Others
    "equipment",
    "furniture",
    "luggage",
    "baggage",
    "clothing",
    "jewelry",
    "machinery",
    "software",
    "hardware",
    "data",
    "staff",
    "personnel",
    "police",
    "cattle",
    "poultry",
    "scissors",
    "glasses",
    "pants",
    "shorts",
    "jeans",
    "series",
    "species",
    "means",
    "headquarters",
    # Additional uncountable words
    "traffic",
    "feedback",
    "merchandise",
    "livestock",
    "wildlife",
    "offspring",
    "crossroads",
}

# Pluralization rules in order of precedence
PLURALIZATION_RULES: list[tuple[str, str]] = [
    # Words ending in -s, -ss, -sh, -ch, -x, -z
    (r"(s|ss|sh|ch|x|z)$", r"\1es"),
    # Words ending in consonant + y
    (r"([bcdfghjklmnpqrstvwxz])y$", r"\1ies"),
    # Words ending in vowel + y
    (r"([aeiou])y$", r"\1ys"),
    # Words ending in -f or -fe (not covered by irregular)
    (r"([^aeiou])fe?$", r"\1ves"),
    # Words ending in consonant + o
    (r"([bcdfghjklmnpqrstvwxz])o$", r"\1oes"),
    # Words ending in vowel + o
    (r"([aeiou])o$", r"\1os"),
    # Words ending in -us (Latin)
    (r"us$", r"i"),
    # Words ending in -is (Greek)
    (r"is$", r"es"),
    # Words ending in -on (Greek)
    (r"on$", r"a"),
    # Words ending in -um (Latin)
    (r"um$", r"a"),
    # Default rule: add -s
    (r"$", r"s"),
]

# Special cases for -o endings that take -s instead of -es
O_EXCEPTIONS: set[str] = {
    "photo",
    "piano",
    "halo",
    "solo",
    "soprano",
    "alto",
    "disco",
    "casino",
    "studio",
    "radio",
    "stereo",
    "video",
    "audio",
    "portfolio",
    "scenario",
    "embryo",
    "memo",
    "logo",
    "ego",
    "zero",
    "auto",
    "metro",
    "macro",
    "micro",
    "retro",
    "tempo",
    "contralto",
}

# Words ending in -o that take -es (not -s)
O_ES_WORDS: set[str] = {
    "hero",
    "potato",
    "tomato",
    "echo",
    "veto",
    "torpedo",
    "volcano",
    "tornado",
    "mosquito",
    "buffalo",
    "domino",
    "mango",
    "flamingo",
}

# Words ending in -f that take -s instead of -ves
F_EXCEPTIONS: set[str] = {
    "roof",
    "proof",
    "chief",
    "cliff",
    "staff",
    "golf",
    "safe",
    "belief",
    "chef",
    "reef",
    "grief",
    "brief",
    "handkerchief",
}


def pluralize(word: str) -> str:
    """
    Convert a singular English word to its plural form.

    Args:
        word: The singular word to pluralize

    Returns:
        The plural form of the word

    Examples:
        >>> pluralize("cat")
        'cats'
        >>> pluralize("child")
        'children'
        >>> pluralize("mouse")
        'mice'
        >>> pluralize("box")
        'boxes'
        >>> pluralize("city")
        'cities'
    """
    if not word or not isinstance(word, str):
        return word

    # Clean the word
    original_word = word
    word = word.strip().lower()

    if not word:
        return original_word

    # Check if already plural or uncountable
    if is_plural(word) or word in UNCOUNTABLE_WORDS:
        return original_word

    # Check irregular plurals
    if word in IRREGULAR_PLURALS:
        plural = IRREGULAR_PLURALS[word]
        return _preserve_case(original_word, plural)

    # Apply pluralization rules
    for pattern, replacement in PLURALIZATION_RULES:
        if re.search(pattern, word):
            # Special handling for -o endings
            if pattern == r"([bcdfghjklmnpqrstvwxz])o$":
                if word in O_EXCEPTIONS:
                    plural = word + "s"
                elif word in O_ES_WORDS:
                    plural = word + "es"
                else:
                    # Default for consonant + o: add -es
                    plural = re.sub(pattern, replacement, word)
            # Special handling for -f endings
            elif pattern == r"([^aeiou])fe?$":
                if word in F_EXCEPTIONS or word.rstrip("e") in F_EXCEPTIONS:
                    plural = word + "s"
                else:
                    plural = re.sub(pattern, replacement, word)
            else:
                plural = re.sub(pattern, replacement, word)

            return _preserve_case(original_word, plural)

    # Fallback: just add 's'
    return original_word + "s"


def singularize(word: str) -> str:
    """
    Convert a plural English word to its singular form.

    Args:
        word: The plural word to singularize

    Returns:
        The singular form of the word

    Examples:
        >>> singularize("cats")
        'cat'
        >>> singularize("children")
        'child'
        >>> singularize("mice")
        'mouse'
    """
    if not word or not isinstance(word, str):
        return word

    original_word = word
    word = word.strip().lower()

    if not word:
        return original_word

    # Check if already singular or uncountable
    if not is_plural(word) or word in UNCOUNTABLE_WORDS:
        return original_word

    # Check reverse irregular plurals
    reverse_irregulars = {v: k for k, v in IRREGULAR_PLURALS.items()}
    if word in reverse_irregulars:
        singular = reverse_irregulars[word]
        return _preserve_case(original_word, singular)

    # Latin/Greek words that end in -a and should become -um
    latin_um_words = {"datum", "medium", "curriculum", "memorandum", "bacterium", "stadium", "aquarium", "terrarium"}
    # Latin/Greek words that end in -a and should become -on
    greek_on_words = {"criterion", "phenomenon", "automaton"}

    # Apply singularization rules (reverse of pluralization)
    singularization_rules = [
        # -ies -> -y (but not -eies)
        (r"([bcdfghjklmnpqrstvwxz])ies$", r"\1y"),
        # -ves -> -f/-fe
        (r"([bcdfghjklmnpqrstvwxz])ves$", r"\1f"),
        # -oes -> -o (but check exceptions)
        (r"([bcdfghjklmnpqrstvwxz])oes$", r"\1o"),
        # -es -> '' (for words ending in s, ss, sh, ch, x, z)
        (r"(s|ss|sh|ch|x|z)es$", r"\1"),
        # -i -> -us (Latin)
        (r"i$", r"us"),
        # -s -> '' (default)
        (r"s$", r""),
    ]

    # Special handling for Latin/Greek -a endings
    if word.endswith("a"):
        base = word[:-1]
        if base + "um" in latin_um_words:
            return _preserve_case(original_word, base + "um")
        elif base + "on" in greek_on_words:
            return _preserve_case(original_word, base + "on")

    for pattern, replacement in singularization_rules:
        if re.search(pattern, word):
            singular = re.sub(pattern, replacement, word)
            return _preserve_case(original_word, singular)

    return original_word


def is_plural(word: str) -> bool:
    """
    Check if a word is in plural form.

    Args:
        word: The word to check

    Returns:
        True if the word appears to be plural, False otherwise

    Examples:
        >>> is_plural("cats")
        True
        >>> is_plural("cat")
        False
        >>> is_plural("children")
        True
    """
    if not word or not isinstance(word, str):
        return False

    word = word.strip().lower()

    if not word:
        return False

    # Uncountable words are neither singular nor plural
    if word in UNCOUNTABLE_WORDS:
        return False

    # Check if it's a known plural form
    if word in IRREGULAR_PLURALS.values():
        return True

    # Check if it's a known singular form
    if word in IRREGULAR_PLURALS:
        return False

    # Common singular words that end in 's' but are not plural
    singular_s_words = {
        "bus",
        "gas",
        "glass",
        "class",
        "pass",
        "mass",
        "grass",
        "bass",
        "kiss",
        "miss",
        "boss",
        "loss",
        "cross",
        "dress",
        "stress",
        "press",
        "chess",
        "mess",
        "less",
        "guess",
        "bless",
        "process",
        "success",
        "address",
        "access",
        "express",
        "progress",
        "congress",
        "princess",
        "business",
        "witness",
        "fitness",
        "illness",
        "darkness",
        "happiness",
        "this",
        "yes",
        "us",
        "plus",
        "minus",
        "focus",
        "campus",
        "virus",
        "status",
        "bonus",
        "genus",
        "census",
        "chorus",
        "circus",
    }

    # If word ends in 's' but is a known singular word, it's not plural
    if word.endswith("s") and word in singular_s_words:
        return False

    # Apply heuristic rules
    plural_patterns = [
        r"[bcdfghjklmnpqrstvwxz]ies$",  # cities, flies
        r"[bcdfghjklmnpqrstvwxz]ves$",  # knives, wolves
        r"[bcdfghjklmnpqrstvwxz]oes$",  # heroes, potatoes
        r"(s|ss|sh|ch|x|z)es$",  # boxes, dishes
        r"[aeiou]ys$",  # boys, keys
        r"i$",  # alumni, fungi
        r"a$",  # data, criteria
        r"[^aeiou]s$",  # general plural ending (but not after vowels to avoid false positives)
    ]

    for pattern in plural_patterns:
        if re.search(pattern, word):
            return True

    return False


def _preserve_case(original: str, converted: str) -> str:
    """
    Preserve the case pattern of the original word in the converted word.

    Args:
        original: The original word with its case pattern
        converted: The converted word in lowercase

    Returns:
        The converted word with the original's case pattern applied
    """
    if not original or not converted:
        return converted

    # If original is all uppercase
    if original.isupper():
        return converted.upper()

    # If original is title case (first letter uppercase)
    if original[0].isupper() and len(original) > 1 and original[1:].islower():
        return converted.capitalize()

    # If original has mixed case, try to preserve pattern
    if any(c.isupper() for c in original):
        result = list(converted.lower())
        for i, char in enumerate(original):
            if i < len(result) and char.isupper():
                result[i] = result[i].upper()
        return "".join(result)

    # Default: return as lowercase
    return converted


# Convenience functions for common use cases
def smart_pluralize(word: str, count: int) -> str:
    """
    Return singular or plural form based on count.

    Args:
        word: The base word
        count: The count to determine singular/plural

    Returns:
        Singular form if count is 1, plural otherwise

    Examples:
        >>> smart_pluralize("cat", 1)
        'cat'
        >>> smart_pluralize("cat", 2)
        'cats'
        >>> smart_pluralize("cat", 0)
        'cats'
    """
    if count == 1:
        return singularize(word) if is_plural(word) else word
    else:
        return pluralize(word) if not is_plural(word) else word


def format_count(word: str, count: int) -> str:
    """
    Format a count with the appropriate singular/plural form.

    Args:
        word: The base word
        count: The count

    Returns:
        Formatted string with count and appropriate word form

    Examples:
        >>> format_count("cat", 1)
        '1 cat'
        >>> format_count("cat", 2)
        '2 cats'
        >>> format_count("mouse", 3)
        '3 mice'
    """
    word_form = smart_pluralize(word, count)
    return f"{count} {word_form}"
