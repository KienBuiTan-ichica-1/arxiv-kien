import os

def load_semantic_scholar_key() -> str | None:
    value=os.getenv('SEMANTIC_SCHOLAR_API_KEY','').strip()
    if value: return value
    try:
        from google.colab import userdata
    except ImportError:
        return None
    try:
        value=userdata.get('SEMANTIC_SCHOLAR_API_KEY')
    except userdata.SecretNotFoundError:
        return None
    except userdata.NotebookAccessError:
        raise RuntimeError('Enable notebook access to SEMANTIC_SCHOLAR_API_KEY in Colab Secrets') from None
    return value.strip() if value else None
