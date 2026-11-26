import re
import unicodedata
from difflib import SequenceMatcher

def _normalize_for_comparison(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def verify_quote_in_text_v2(quote: str, parsed_text: str) -> bool:
    """
    Verify that a claimed evidence quote actually exists in parsed_text.
    Strict anti-hallucination verification:
      1. Normalizes case, unicode, and punctuation.
      2. Direct substring match (exact verbatim quote).
      3. Handles ellipsis truncation (...).
      4. For short quotes (<= 3 words), requires exact contiguous substring.
      5. For longer quotes, requires ordered sequence similarity >= 0.82 in a local sliding window.
    """
    if not quote or not parsed_text:
        return False

    clean_quote = quote.strip()
    # Strip leading/trailing ellipsis or quotation marks
    clean_quote = re.sub(r"^[\s\"'“”‘’.…]+|[\s\"'“”‘’.…]+$", "", clean_quote)
    if not clean_quote:
        return False

    norm_quote = _normalize_for_comparison(clean_quote)
    norm_text  = _normalize_for_comparison(parsed_text)

    # 1. Exact direct substring match (fastest & strictest)
    if norm_quote in norm_text:
        return True

    quote_tokens = norm_quote.split()
    q_len = len(quote_tokens)
    if q_len == 0:
        return False

    # 2. Short quotes (<= 3 tokens): MUST be a direct contiguous substring
    if q_len <= 3:
        return norm_quote in norm_text

    text_tokens = norm_text.split()
    t_len = len(text_tokens)
    if t_len < q_len:
        # Check if the entire resume is a high-ratio match to the quote
        return SequenceMatcher(None, quote_tokens, text_tokens).ratio() >= 0.85

    # 3. Check for substantive key token presence
    # Stop words that shouldn't fool the matcher
    stop = {"a", "an", "the", "in", "of", "for", "and", "or", "to", "with", "is", "was", "on", "at", "by"}
    substantive = [t for t in quote_tokens if t not in stop and len(t) > 2]
    if substantive:
        text_tokens_set = set(text_tokens)
        substantive_in_text = sum(1 for t in substantive if t in text_tokens_set)
        # If less than 65% of substantive words even exist in the entire resume, it's fabricated!
        if substantive_in_text / len(substantive) < 0.65:
            return False

    # 4. Sliding window with ordered SequenceMatcher
    # Window sizes: q_len, q_len + 1, q_len - 1 to handle minor word boundary variations
    best_ratio = 0.0
    step = max(1, q_len // 4)
    
    # Fast filter: find candidate window start positions using the first 2 substantive tokens
    candidate_starts = []
    first_key = substantive[0] if substantive else quote_tokens[0]
    for idx, tok in enumerate(text_tokens):
        if tok == first_key:
            candidate_starts.append(max(0, idx - 2))

    # If no candidate starts from first token, scan across the text with step
    if not candidate_starts:
        candidate_starts = list(range(0, t_len - q_len + 1, step))

    for start in candidate_starts:
        for w_size in (q_len, q_len + 2, q_len - 2):
            if w_size <= 0:
                continue
            end = min(t_len, start + w_size)
            window = text_tokens[start:end]
            ratio = SequenceMatcher(None, quote_tokens, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
            if best_ratio >= 0.82:
                return True

    return False

# Test cases
resume = "Developed real-time ETL pipelines using Python and Snowflake to ingest live weather data. Deployed microservices on AWS."

# 1. Exact
assert verify_quote_in_text_v2("Developed real-time ETL pipelines using Python and Snowflake to ingest live weather data.", resume) == True

# 2. Minor formatting difference (newlines and commas)
assert verify_quote_in_text_v2("Developed real-time ETL\npipelines, using Python and Snowflake.", resume) == True

# 3. Fabricated quote with extra unmentioned technologies
assert verify_quote_in_text_v2("Developed real-time ETL pipelines using Python and Snowflake with enterprise Kubernetes clusters and Kafka streams.", resume) == False

# 4. Disconnected tokens across sections
assert verify_quote_in_text_v2("Python AWS", resume) == False

# 5. Fabricated technical claim
assert verify_quote_in_text_v2("Managed 50-node production Kubernetes cluster with Istio service mesh.", resume) == False

# 6. Truncated with ellipsis
assert verify_quote_in_text_v2("Developed real-time ETL pipelines using Python and Snowflake...", resume) == True

print("ALL 6 QUOTE VERIFICATION TESTS PASSED!")
