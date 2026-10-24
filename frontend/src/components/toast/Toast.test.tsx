import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { useToast, type ToastInput } from './context';
import { ToastProvider } from './ToastProvider';

let push: (t: ToastInput) => string = () => '';
function Grab() {
  push = useToast().push;
  return null;
}

function setup() {
  render(
    <ToastProvider>
      <Grab />
    </ToastProvider>,
  );
}

describe('toasts', () => {
  it('announces errors assertively and info politely', () => {
    setup();
    act(() => {
      push({ kind: 'error', title: 'Boom' });
      push({ title: 'Saved' });
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Boom');
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
  });

  it('deduplicates by key and shows a counter', () => {
    setup();
    act(() => {
      push({ title: 'Down', dedupeKey: 'k' });
      push({ title: 'Down', dedupeKey: 'k' });
    });
    expect(screen.getAllByText('Down')).toHaveLength(1);
    expect(screen.getByText('×2')).toBeInTheDocument();
  });

  it('auto-dismisses after its duration', () => {
    vi.useFakeTimers();
    try {
      setup();
      act(() => {
        push({ title: 'Bye', durationMs: 1000 });
      });
      expect(screen.getByText('Bye')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1100);
      });
      expect(screen.queryByText('Bye')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('runs the action and can be dismissed by button', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    setup();
    act(() => {
      push({ title: 'Failed', action: { label: 'Retry', onClick }, durationMs: 0 });
    });
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onClick).toHaveBeenCalledOnce();
    expect(screen.queryByText('Failed')).not.toBeInTheDocument();
    act(() => {
      push({ title: 'Again', durationMs: 0 });
    });
    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    expect(screen.queryByText('Again')).not.toBeInTheDocument();
  });
});
