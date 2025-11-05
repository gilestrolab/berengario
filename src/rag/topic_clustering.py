"""
Topic clustering for usage analytics.

This module provides LLM-powered topic clustering to identify
common themes and categories in user queries.
"""

import logging
from collections import Counter
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def cluster_topics(
    query_texts: List[str], rag_engine: Any, max_topics: int = 10
) -> List[Dict[str, Any]]:
    """
    Analyze and cluster queries into topics using LLM.

    Args:
        query_texts: List of query strings to analyze
        rag_engine: RAG engine instance (for LLM access)
        max_topics: Maximum number of topics to identify

    Returns:
        List of topic dictionaries with:
        - topic_name: Name of the topic
        - description: Brief description
        - query_count: Number of queries in this topic
        - percentage: Percentage of total queries
        - sample_queries: 3-5 example queries
    """
    if not query_texts:
        logger.warning("No queries provided for topic clustering")
        return []

    total_queries = len(query_texts)
    logger.info(f"Clustering {total_queries} queries into topics")

    try:
        # Prepare prompt for LLM
        # Take a sample if there are too many queries
        sample_size = min(100, len(query_texts))
        sample_queries = query_texts[:sample_size]

        queries_text = "\n".join(
            [f"{i+1}. {q[:200]}" for i, q in enumerate(sample_queries)]
        )

        prompt = f"""Analyze these user queries and identify the main topics/themes. Group similar queries together.

Queries:
{queries_text}

Please identify up to {max_topics} main topics and provide:
1. Topic name (2-4 words)
2. Brief description (1 sentence)
3. Which query numbers belong to this topic

Format your response as a JSON array with this structure:
[
  {{
    "topic_name": "Account Management",
    "description": "Questions about user accounts, passwords, and login",
    "query_numbers": [1, 5, 12]
  }},
  ...
]

Only return the JSON array, nothing else."""

        # Query the LLM
        from llama_index.core.llms import ChatMessage, MessageRole

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="You are a data analyst expert at categorizing and clustering text data.",
            ),
            ChatMessage(role=MessageRole.USER, content=prompt),
        ]

        response = rag_engine.llm.chat(messages)
        response_text = response.message.content

        # Parse JSON response
        import json
        import re

        # Extract JSON from response (in case there's extra text)
        json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)

        topics_data = json.loads(response_text)

        # Build topic statistics
        topics = []
        for topic_data in topics_data:
            topic_name = topic_data.get("topic_name", "Unknown")
            description = topic_data.get("description", "")
            query_numbers = topic_data.get("query_numbers", [])

            # Get actual query texts
            sample_queries_for_topic = [
                sample_queries[num - 1]
                for num in query_numbers
                if 0 < num <= len(sample_queries)
            ][
                :5
            ]  # Max 5 samples

            # Estimate query count based on sample
            estimated_count = int(len(query_numbers) * (total_queries / sample_size))
            percentage = round((estimated_count / total_queries) * 100, 1)

            topics.append(
                {
                    "topic_name": topic_name,
                    "description": description,
                    "query_count": estimated_count,
                    "percentage": percentage,
                    "sample_queries": sample_queries_for_topic,
                }
            )

        # Sort by query count
        topics.sort(key=lambda x: x["query_count"], reverse=True)

        logger.info(f"Identified {len(topics)} topics from {total_queries} queries")
        return topics

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"LLM response: {response_text}")

        # Fallback: Use simple keyword-based clustering
        return _fallback_keyword_clustering(query_texts, max_topics)

    except Exception as e:
        logger.error(f"Error during topic clustering: {e}", exc_info=True)

        # Fallback: Use simple keyword-based clustering
        return _fallback_keyword_clustering(query_texts, max_topics)


def _fallback_keyword_clustering(
    query_texts: List[str], max_topics: int = 10
) -> List[Dict[str, Any]]:
    """
    Simple keyword-based clustering as fallback.

    Args:
        query_texts: List of query strings
        max_topics: Maximum number of topics

    Returns:
        List of topic dictionaries
    """
    logger.info("Using fallback keyword-based clustering")

    # Extract common words (simple approach)
    import re
    from collections import defaultdict

    # Common stop words to ignore
    stop_words = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "might",
        "must",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "what",
        "when",
        "where",
        "who",
        "why",
        "how",
        "which",
        "this",
        "that",
        "these",
        "those",
        "my",
        "your",
        "his",
        "her",
        "its",
        "our",
        "their",
        "me",
        "him",
        "us",
        "them",
        "to",
        "from",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "about",
        "of",
        "and",
        "or",
        "but",
        "not",
    }

    # Count word frequencies
    word_counts = Counter()
    query_word_map = defaultdict(list)  # word -> [query indices]

    for idx, query in enumerate(query_texts):
        # Extract words (lowercase, alphanumeric)
        words = re.findall(r"\b[a-z]{3,}\b", query.lower())
        unique_words = set(words) - stop_words

        for word in unique_words:
            word_counts[word] += 1
            query_word_map[word].append(idx)

    # Get most common words as topics
    most_common = word_counts.most_common(max_topics)

    topics = []
    for word, count in most_common:
        query_indices = query_word_map[word]
        sample_queries = [query_texts[i] for i in query_indices[:5]]
        percentage = round((count / len(query_texts)) * 100, 1)

        topics.append(
            {
                "topic_name": word.capitalize(),
                "description": f"Queries containing '{word}'",
                "query_count": count,
                "percentage": percentage,
                "sample_queries": sample_queries,
            }
        )

    return topics
