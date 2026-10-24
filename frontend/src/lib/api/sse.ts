/**
 * POST + Server-Sent Events reader, for the `/query` and `/chat` streams.
 * `EventSource` can't POST, so this parses the `text/event-stream` body by hand.
 * The legacy backend frames every event as `event: <type>\ndata: <json>\n\n`.
 */
import { rawRequest, toApiError, type RequestOptions } from './client';

export interface SseEvent<T = unknown> {
  event: string;
  data: T;
  id?: string;
}

/** Parse one raw event block (lines between blank lines). Returns null for comments/keep-alives. */
export function parseEventBlock(block: string): SseEvent | null {
  let event = 'message';
  let id: string | undefined;
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') dataLines.push(value);
    else if (field === 'id') id = value;
  }
  if (!dataLines.length && event === 'message') return null;
  const raw = dataLines.join('\n');
  let data: unknown = raw;
  if (raw) {
    try {
      data = JSON.parse(raw) as unknown;
    } catch {
      data = raw;
    }
  }
  return id === undefined ? { event, data } : { event, data, id };
}

/**
 * Yields events as they arrive. Throws `ApiError` if the response is not 2xx.
 * Abort with `signal` to stop reading (the loop then ends quietly).
 */
export async function* streamSse<T = unknown>(
  path: string,
  body: unknown,
  opts: Pick<RequestOptions, 'signal' | 'headers'> = {},
): AsyncGenerator<SseEvent<T>, void, undefined> {
  const res = await rawRequest(path, {
    method: 'POST',
    body,
    signal: opts.signal,
    headers: { Accept: 'text/event-stream', ...opts.headers },
  });
  if (!res.ok) throw await toApiError(res, path);
  if (!res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) {
        finished = true;
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let match: RegExpExecArray | null;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const block = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const evt = parseEventBlock(block);
        if (evt) yield evt as SseEvent<T>;
      }
    }
    buffer += decoder.decode();
    const tail = parseEventBlock(buffer);
    if (tail) yield tail as SseEvent<T>;
  } finally {
    // Consumer stopped early (break/return/abort): close the connection instead of leaking it.
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
