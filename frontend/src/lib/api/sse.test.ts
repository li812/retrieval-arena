import { describe, expect, it, vi } from 'vitest';

import { jsonResponse } from '@/test/utils';

import { ApiError } from './client';
import { parseEventBlock, streamSse } from './sse';

function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('parseEventBlock', () => {
  it('parses event + JSON data', () => {
    expect(parseEventBlock('event: token\ndata: {"text":"hi"}')).toEqual({
      event: 'token',
      data: { text: 'hi' },
    });
  });
  it('ignores comments / keep-alives', () => {
    expect(parseEventBlock(': ping')).toBeNull();
  });
  it('keeps non-JSON data as text and joins multi-line data', () => {
    expect(parseEventBlock('data: a\ndata: b')).toEqual({ event: 'message', data: 'a\nb' });
  });
});

describe('streamSse', () => {
  it('yields events split across arbitrary chunk boundaries', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        streamResponse([
          'event: embedding_done\ndata: {"duration_ms": 12}\n',
          '\nevent: tok',
          'en\ndata: {"text":"Hel"}\n\nevent: token\r\ndata: {"text":"lo"}\r\n\r\n',
          'event: done\ndata: {}\n\n',
        ]),
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    const events = [];
    for await (const e of streamSse('/query', { question: 'q' })) events.push(e);
    expect(events.map((e) => e.event)).toEqual(['embedding_done', 'token', 'token', 'done']);
    expect(events[1]!.data).toEqual({ text: 'Hel' });
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>).Accept).toBe('text/event-stream');
  });

  it('throws ApiError before streaming on an HTTP error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ detail: 'No API key' }, 400))),
    );
    const gen = streamSse('/chat', {});
    await expect(gen.next()).rejects.toBeInstanceOf(ApiError);
  });
});
