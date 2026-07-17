def complete(prompt: str) -> str:
    """A dummy application that simulates basic input filtering."""
    if "refund" in prompt.lower() or "admin" in prompt.lower():
        return "I am unable to process administrative or financial requests."
    return f"Processed query: {prompt}"
