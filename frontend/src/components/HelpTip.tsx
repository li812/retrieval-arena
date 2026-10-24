import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

interface HelpTipProps {
  /** What the tip is about, e.g. "SQLite" → button label "About SQLite". */
  label: string;
  children: ReactNode;
}

const GAP = 8;
const EDGE = 12;

/**
 * "?" contextual help (UX-3). Opens on hover (mouse), keyboard focus, or tap; closes on
 * Esc, outside tap, blur, or tapping again. The text is always wired via aria-describedby.
 */
export function HelpTip({ label, children }: HelpTipProps) {
  const id = useId();
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setPinned(false);
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const place = () => {
      const btn = btnRef.current;
      const tip = tipRef.current;
      if (!btn || !tip) return;
      const b = btn.getBoundingClientRect();
      const t = tip.getBoundingClientRect();
      const vw = document.documentElement.clientWidth || window.innerWidth;
      let left = b.left + b.width / 2 - t.width / 2;
      left = Math.max(EDGE, Math.min(left, vw - EDGE - t.width));
      let top = b.top - GAP - t.height;
      if (top < EDGE) top = b.bottom + GAP;
      setPos({ top, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
    };
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (btnRef.current?.contains(target) || tipRef.current?.contains(target)) return;
      close();
    };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onPointerDown, true);
    };
  }, [open, close]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="help-tip"
        aria-label={`About ${label}`}
        aria-describedby={id}
        aria-expanded={open}
        onPointerEnter={(e) => {
          if (e.pointerType === 'mouse') setOpen(true);
        }}
        onPointerLeave={(e) => {
          if (e.pointerType === 'mouse' && !pinned) setOpen(false);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          if (!pinned) setOpen(false);
        }}
        onClick={() => {
          // Tap / click toggles a pinned tip; on touch this is the only way in.
          if (pinned) close();
          else {
            setPinned(true);
            setOpen(true);
          }
        }}
      >
        ?
      </button>
      {createPortal(
        <div
          ref={tipRef}
          id={id}
          role="tooltip"
          className="tooltip"
          hidden={!open}
          style={
            pos
              ? { top: pos.top, left: pos.left }
              : { top: 0, left: 0, visibility: open ? 'hidden' : undefined }
          }
        >
          {children}
        </div>,
        document.body,
      )}
    </>
  );
}
