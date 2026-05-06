"""
Thinking Block Stripper
Ported from enowx_middleware: strips thinking/signature blocks from
streaming SSE delta content before forwarding to client.
"""
import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Patterns to detect and strip thinking blocks
_THINKING_OPEN = re.compile(r'<thinking>', re.IGNORECASE)
_THINKING_CLOSE = re.compile(r'</thinking>', re.IGNORECASE)

_SIGNATURE_OPEN = re.compile(r'<signature>', re.IGNORECASE)
_SIGNATURE_CLOSE = re.compile(r'</signature>', re.IGNORECASE)

# Full-block regex for non-streaming (complete text)
_THINKING_BLOCK_RE = re.compile(r'<thinking>[\s\S]*?</thinking>', re.IGNORECASE)
_SIGNATURE_BLOCK_RE = re.compile(r'<signature>[\s\S]*?</signature>', re.IGNORECASE)


def strip_thinking_from_text(text: str) -> Tuple[str, int]:
    """Strip complete thinking/signature blocks from a full text string.
    Returns (cleaned_text, blocks_removed_count)."""
    if not isinstance(text, str):
        return text, 0
    count = 0
    result, n = _THINKING_BLOCK_RE.subn('', text)
    count += n
    result, n = _SIGNATURE_BLOCK_RE.subn('', result)
    count += n
    return result.strip(), count


class StreamingThinkingStripper:
    """
    Stateful stripper for streaming SSE chunks.
    Buffers content across chunks to correctly detect and remove
    multi-chunk thinking/signature blocks.

    Usage:
        stripper = StreamingThinkingStripper()
        for chunk_data in stream:
            cleaned_data, stripped_count = stripper.process_chunk(chunk_data)
            if cleaned_data:
                yield cleaned_data
        # Flush at end of stream
        remainder, count = stripper.flush()
    """

    def __init__(self):
        self._buffer = ""
        self._in_block = False  # True if currently inside a thinking/signature block
        self._block_tag = ""    # The open tag that started the block
        self._total_stripped = 0

    def _get_close_tag(self, open_tag: str) -> str:
        tag_name = open_tag.strip('<>').lower()
        return f'</{tag_name}>'

    def process_chunk(self, chunk_data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Process a single SSE chunk dict.
        Modifies delta.content in-place if thinking blocks are found.
        Returns (modified_chunk, blocks_stripped_this_chunk).
        """
        stripped = 0
        if not chunk_data.get('choices'):
            return chunk_data, 0

        for choice in chunk_data['choices']:
            delta = choice.get('delta', {})
            content = delta.get('content')
            if not isinstance(content, str) or not content:
                continue

            cleaned, n = self._process_text(content)
            stripped += n
            delta['content'] = cleaned

        self._total_stripped += stripped
        return chunk_data, stripped

    def _process_text(self, text: str) -> Tuple[str, int]:
        """Process a text fragment, maintaining state across chunks."""
        self._buffer += text
        result_parts = []
        stripped_count = 0

        while self._buffer:
            if self._in_block:
                # Looking for the close tag
                close_tag = self._get_close_tag(self._block_tag)
                close_pos = self._buffer.lower().find(close_tag.lower())
                if close_pos >= 0:
                    # Found end of block — consume it
                    self._buffer = self._buffer[close_pos + len(close_tag):]
                    self._in_block = False
                    self._block_tag = ""
                    stripped_count += 1
                else:
                    # Close tag not yet in buffer — keep buffering
                    # But if buffer is very large, something is wrong — release it
                    if len(self._buffer) > 50000:
                        logger.warning("ThinkingStripper: buffer overflow, releasing raw content")
                        result_parts.append(self._buffer)
                        self._buffer = ""
                        self._in_block = False
                    break
            else:
                # Not in a block — look for opening tags
                open_tags = ['<thinking>', '<signature>']
                earliest_pos = -1
                earliest_tag = ''

                for tag in open_tags:
                    pos = self._buffer.lower().find(tag.lower())
                    if pos >= 0 and (earliest_pos < 0 or pos < earliest_pos):
                        earliest_pos = pos
                        earliest_tag = tag

                if earliest_pos < 0:
                    # No opening tag — check for partial tag at end of buffer
                    # Keep last 20 chars buffered in case a tag is split across chunks
                    safe_to_emit = max(0, len(self._buffer) - 20)
                    result_parts.append(self._buffer[:safe_to_emit])
                    self._buffer = self._buffer[safe_to_emit:]
                    break
                else:
                    # Emit everything before the tag
                    result_parts.append(self._buffer[:earliest_pos])
                    self._buffer = self._buffer[earliest_pos:]
                    self._in_block = True
                    self._block_tag = earliest_tag

        return ''.join(result_parts), stripped_count

    def flush(self) -> Tuple[str, int]:
        """Call at end of stream to release any remaining buffered content."""
        remaining = self._buffer
        self._buffer = ""
        self._in_block = False
        return remaining, self._total_stripped

    @property
    def total_stripped(self) -> int:
        return self._total_stripped
