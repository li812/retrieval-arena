from typing import Generator

from google import genai
from google.genai import types


class GenerationAgent:
    def stream_answer(
        self,
        question: str,
        context: str,
        system_prompt: str,
        api_key: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
    ) -> Generator[str, None, None]:
        client = genai.Client(api_key=api_key)
        prompt = (
            system_prompt
            + "\n\n## Context\n"
            + context
            + "\n\n## Question\n"
            + question
        )
        stream = client.models.generate_content_stream(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
