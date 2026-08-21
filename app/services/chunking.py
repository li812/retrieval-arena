import re


class ChunkingService:
    def chunk(self, text: str, strategy: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        if strategy == "sentence_aware":
            return self._sentence_aware(text, chunk_size, chunk_overlap)
        return self._fixed(text, chunk_size, chunk_overlap)

    def _fixed(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
        return chunks

    def _sentence_aware(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        # Split on sentence/paragraph boundaries
        units = re.split(r'(?<=[.?!])\s+|\n\n+', text)
        units = [u.strip() for u in units if u.strip()]

        chunks = []
        current_parts: list[str] = []
        current_len = 0

        for unit in units:
            unit_len = len(unit)
            if current_len + unit_len > chunk_size and current_parts:
                chunks.append(" ".join(current_parts))
                # Overlap: carry over trailing units that fit within chunk_overlap
                overlap_parts: list[str] = []
                overlap_len = 0
                for part in reversed(current_parts):
                    if overlap_len + len(part) + 1 <= chunk_overlap:
                        overlap_parts.insert(0, part)
                        overlap_len += len(part) + 1
                    else:
                        break
                current_parts = overlap_parts
                current_len = overlap_len

            current_parts.append(unit)
            current_len += unit_len + 1  # +1 for separator

        if current_parts:
            chunks.append(" ".join(current_parts))

        return chunks
