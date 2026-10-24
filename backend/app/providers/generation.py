from collections.abc import Generator

from google import genai
from google.genai import types
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


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
        provider: str = "gemini",
    ) -> Generator[str, None, None]:
        if provider == "nvidia":
            yield from self._stream_nvidia(
                question, context, system_prompt, api_key, model, temperature, max_output_tokens
            )
        else:
            yield from self._stream_gemini(
                question, context, system_prompt, api_key, model, temperature, max_output_tokens
            )

    def _stream_gemini(
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
        prompt = system_prompt + "\n\n## Context\n" + context + "\n\n## Question\n" + question
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

    def _stream_nvidia(
        self,
        question: str,
        context: str,
        system_prompt: str,
        api_key: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
    ) -> Generator[str, None, None]:
        client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)
        prompt = system_prompt + "\n\n## Context\n" + context + "\n\n## Question\n" + question
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_output_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    # ------------------------------------------------------------------
    # Multi-turn chat
    # ------------------------------------------------------------------

    def stream_chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_content: str,
        api_key: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        provider: str = "gemini",
    ) -> Generator[str, None, None]:
        """Stream a reply given prior turns ([{role: user|assistant, content}]) and the new user turn."""
        if provider == "nvidia":
            client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)
            messages = [{"role": "system", "content": system_prompt}]
            messages += [{"role": m["role"], "content": m["content"]} for m in history]
            messages.append({"role": "user", "content": user_content})
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_output_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
            return

        client = genai.Client(api_key=api_key)
        contents = [
            types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
            for m in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=user_content)]))
        stream = client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )
        for chunk in stream:
            if chunk.text:
                yield chunk.text
