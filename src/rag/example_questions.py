"""
Generate example questions based on the knowledge base.

This module provides functionality to generate suggested questions
that users can ask based on the available knowledge base content.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from src.rag.rag_engine import RAGEngine
from src.config import settings

logger = logging.getLogger(__name__)

# Path to store generated questions
EXAMPLE_QUESTIONS_FILE = Path("data/config/example_questions.json")


def generate_example_questions(
    rag_engine: Optional[RAGEngine] = None,
    count: int = 15
) -> List[str]:
    """
    Generate example questions based on the knowledge base content.

    Uses the RAG engine to analyze the knowledge base and generate
    relevant example questions that users might want to ask.

    Args:
        rag_engine: RAG engine instance (creates new if None).
        count: Number of example questions to generate.

    Returns:
        List of example question strings.

    Raises:
        Exception: If question generation fails.
    """
    if rag_engine is None:
        rag_engine = RAGEngine()

    logger.info(f"Generating {count} example questions from knowledge base")

    # Craft a prompt to generate example questions
    prompt = f"""Based on your acquired knowledge base, generate a list of exactly {count} example questions that users may be interested in asking.

Requirements:
- Questions should be brief and clear
- Focus on useful, practical information from the knowledge base
- Be creative and varied in topics
- Questions should give users an idea of your knowledge capabilities
- Think about what information would be most valuable to users

IMPORTANT: You must respond ONLY with a valid JSON array of strings, nothing else. No markdown formatting, no explanations, just the JSON array.

Example format:
["Question 1?", "Question 2?", "Question 3?"]

Generate the {count} questions now:"""

    try:
        # Query the RAG engine
        result = rag_engine.query(prompt)
        response_text = result["response"].strip()

        logger.debug(f"Raw response: {response_text}")

        # Try to parse the JSON response
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            # Extract content between ``` markers
            lines = response_text.split("\n")
            json_lines = []
            in_code_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block or (not line.strip().startswith("```")):
                    json_lines.append(line)
            response_text = "\n".join(json_lines).strip()

        # Parse JSON
        questions = json.loads(response_text)

        # Validate
        if not isinstance(questions, list):
            raise ValueError("Response is not a list")

        if len(questions) == 0:
            raise ValueError("No questions generated")

        # Ensure all items are strings
        questions = [str(q).strip() for q in questions if q]

        logger.info(f"Successfully generated {len(questions)} example questions")
        return questions[:count]  # Ensure we return exactly count questions

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Response text: {response_text}")
        raise Exception(f"Failed to parse LLM response as JSON: {e}")
    except Exception as e:
        logger.error(f"Error generating example questions: {e}")
        raise


def save_example_questions(questions: List[str]) -> None:
    """
    Save example questions to file.

    Args:
        questions: List of question strings to save.

    Raises:
        Exception: If saving fails.
    """
    try:
        # Ensure directory exists
        EXAMPLE_QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save as JSON
        data = {
            "questions": questions,
            "generated_at": None,  # Will be set by API
            "count": len(questions),
        }

        with open(EXAMPLE_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(questions)} example questions to {EXAMPLE_QUESTIONS_FILE}")

    except Exception as e:
        logger.error(f"Error saving example questions: {e}")
        raise


def load_example_questions() -> Dict:
    """
    Load example questions from file.

    Returns:
        Dictionary containing:
            - questions: List of question strings
            - generated_at: Timestamp of generation (or None)
            - count: Number of questions

    Raises:
        FileNotFoundError: If questions file doesn't exist.
        Exception: If loading fails.
    """
    try:
        if not EXAMPLE_QUESTIONS_FILE.exists():
            logger.warning(f"Example questions file not found: {EXAMPLE_QUESTIONS_FILE}")
            raise FileNotFoundError("Example questions not generated yet")

        with open(EXAMPLE_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"Loaded {data.get('count', 0)} example questions")
        return data

    except FileNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error loading example questions: {e}")
        raise


def generate_and_save_example_questions(
    rag_engine: Optional[RAGEngine] = None,
    count: int = 15
) -> Dict:
    """
    Generate and save example questions in one operation.

    Args:
        rag_engine: RAG engine instance (creates new if None).
        count: Number of questions to generate.

    Returns:
        Dictionary with saved questions data.

    Raises:
        Exception: If generation or saving fails.
    """
    from datetime import datetime

    # Generate questions
    questions = generate_example_questions(rag_engine, count)

    # Prepare data
    data = {
        "questions": questions,
        "generated_at": datetime.now().isoformat(),
        "count": len(questions),
    }

    # Save with timestamp
    EXAMPLE_QUESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EXAMPLE_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Generated and saved {len(questions)} example questions")
    return data
