"""OpenAI embeddings wrapper for the loan approval system."""

import openai
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Initialize OpenAI client
openai.api_key = settings.openai_api_key


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
def get_embedding(text: str, model: str = None) -> List[float]:
    """
    Get embedding for a single text using OpenAI API.
    
    Args:
        text: Text to embed
        model: Embedding model name (default from settings)
    
    Returns:
        List of embedding values (floats)
    
    Raises:
        Exception: If embedding request fails after retries
    """
    if model is None:
        model = settings.llm.embedding_model
    
    try:
        # Truncate text if too long (OpenAI has token limits)
        max_chars = 8000  # Conservative limit
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.warning("text_truncated", original_length=len(text), truncated_length=max_chars)
        
        logger.debug("embedding_request", text_length=len(text), model=model)
        
        # Call OpenAI API
        response = openai.embeddings.create(
            input=text,
            model=model
        )
        
        embedding = response.data[0].embedding
        
        logger.debug(
            "embedding_success",
            text_length=len(text),
            embedding_dim=len(embedding),
            model=model
        )
        
        return embedding
        
    except Exception as e:
        logger.error(
            "embedding_failed",
            text_length=len(text),
            model=model,
            error=str(e)
        )
        raise


def embed_texts(texts: List[str], model: str = None, batch_size: int = 100) -> List[List[float]]:
    """
    Get embeddings for multiple texts in batches.
    
    Args:
        texts: List of texts to embed
        model: Embedding model name (default from settings)
        batch_size: Number of texts to process in each batch
    
    Returns:
        List of embedding lists
    
    Raises:
        Exception: If any embedding request fails
    """
    if model is None:
        model = settings.llm.embedding_model
    
    if not texts:
        return []
    
    logger.info(
        "batch_embedding_start",
        total_texts=len(texts),
        batch_size=batch_size,
        model=model
    )
    
    all_embeddings = []
    
    try:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(texts) + batch_size - 1) // batch_size
            
            logger.debug(
                "processing_batch",
                batch_num=batch_num,
                total_batches=total_batches,
                batch_size=len(batch)
            )
            
            # Truncate texts in batch if needed
            truncated_batch = []
            for text in batch:
                if len(text) > 8000:
                    truncated_batch.append(text[:8000])
                else:
                    truncated_batch.append(text)
            
            # Call OpenAI API for batch
            response = openai.embeddings.create(
                input=truncated_batch,
                model=model
            )
            
            # Extract embeddings from response
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
            logger.debug(
                "batch_complete",
                batch_num=batch_num,
                embeddings_count=len(batch_embeddings)
            )
        
        logger.info(
            "batch_embedding_complete",
            total_embeddings=len(all_embeddings),
            expected=len(texts)
        )
        
        return all_embeddings
        
    except Exception as e:
        logger.error(
            "batch_embedding_failed",
            total_texts=len(texts),
            processed=len(all_embeddings),
            error=str(e)
        )
        raise


def get_embedding_dimension(model: str = None) -> int:
    """
    Get the dimension of embeddings for a given model.
    
    Args:
        model: Embedding model name (default from settings)
    
    Returns:
        Embedding dimension
    """
    if model is None:
        model = settings.llm.embedding_model
    
    # Known dimensions for OpenAI models
    model_dimensions = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    return model_dimensions.get(model, 1536)  # Default to 1536


def validate_embedding_config():
    """
    Validate embedding configuration and test API connection.
    
    Returns:
        bool: True if configuration is valid and API is accessible
    """
    try:
        # Test with a simple embedding request
        test_embedding = get_embedding("test")
        expected_dim = get_embedding_dimension()
        
        if len(test_embedding) != expected_dim:
            logger.error(
                "embedding_dimension_mismatch",
                expected=expected_dim,
                actual=len(test_embedding)
            )
            return False
        
        logger.info(
            "embedding_config_validated",
            model=settings.llm.embedding_model,
            dimension=len(test_embedding)
        )
        
        return True
        
    except Exception as e:
        logger.error("embedding_config_invalid", error=str(e))
        return False 