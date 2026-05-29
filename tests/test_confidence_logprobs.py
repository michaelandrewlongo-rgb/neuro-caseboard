
"""Tests for logprob extraction and entropy computation."""

import math
import pytest
from caseprep.confidence.logprobs import (
    extract_logprobs, compute_entropy, content_token_logprobs
)


def test_extract_logprobs_from_valid_response():
    response = {
        "choices": [{
            "logprobs": {
                "content": [
                    {"token": "operative", "logprob": -0.2, "top_logprobs": [
                        {"token": "operative", "logprob": -0.2},
                        {"token": "literature", "logprob": -2.5},
                    ]},
                    {"token": "_briefing", "logprob": -0.05, "top_logprobs": [
                        {"token": "_briefing", "logprob": -0.05},
                    ]},
                ]
            }
        }]
    }
    result = extract_logprobs(response)
    assert result["tokens"] == ["operative", "_briefing"]
    assert len(result["logprobs"]) == 2
    assert result["logprobs"][0] == -0.2


def test_extract_logprobs_missing_keys():
    response = {}
    result = extract_logprobs(response)
    assert result["tokens"] == []
    assert result["logprobs"] == []
    assert result["top_logprobs"] == []


def test_compute_entropy_peaked():
    top_logprobs = [{"A": -0.1, "B": -4.0, "C": -5.0}]
    entropy = compute_entropy(top_logprobs)
    assert entropy < 0.5  # Low entropy for peaked distribution


def test_compute_entropy_empty():
    assert compute_entropy([]) == 0.0
    assert compute_entropy([{}]) == 0.0


def test_content_token_logprobs_filters_whitespace():
    result = {
        "tokens": ["hello", " ", "world", "\n"],
        "logprobs": [-0.1, -0.01, -0.2, -0.01],
    }
    vals, count = content_token_logprobs(result)
    assert vals == [-0.1, -0.2]
    assert count == 2


def test_content_token_logprobs_custom_stop():
    result = {
        "tokens": ["the", "answer", "is", "42"],
        "logprobs": [-0.1, -0.2, -0.3, -0.4],
    }
    vals, count = content_token_logprobs(result, stop_tokens={"the", "is"})
    assert vals == [-0.2, -0.4]
    assert count == 2
