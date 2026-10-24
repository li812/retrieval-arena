import { KeyRound, Monitor, Moon, Sun } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { HelpTip } from '@/components/HelpTip';
import { ClassicUiLink } from '@/components/Primitives';
import { THEME_MODES, type ThemeMode } from '@/lib/theme';
import { useTheme } from '@/lib/themeContext';

import { PageHeader } from './PageHeader';

const ICONS: Record<ThemeMode, typeof Sun> = { auto: Monitor, light: Sun, dark: Moon };
const SHORT: Record<ThemeMode, string> = { auto: 'Auto', light: 'Light', dark: 'Dark' };

export default function Settings() {
  const { mode, resolved, setMode } = useTheme();
  return (
    <div className="page">
      <PageHeader eyebrow="Preferences" title="Settings" />

      <section className="panel" aria-labelledby="appearance-title" data-tour="appearance">
        <div className="panel-header">
          <h3 className="panel-title" id="appearance-title">
            Appearance
          </h3>
        </div>
        <div className="panel-body">
          <div className="field-row">
            <div>
              <div className="field-label" id="theme-label">
                Theme
                <HelpTip label="theme">
                  Auto follows your device’s light or dark setting and switches with it. The choice
                  is saved in this browser and shared with the classic UI. Press T anywhere to
                  cycle.
                </HelpTip>
              </div>
              <div className="field-help">
                Currently showing the <strong>{resolved}</strong> theme.
              </div>
            </div>
            <div className="segmented" role="radiogroup" aria-labelledby="theme-label">
              {THEME_MODES.map((m) => {
                const Icon = ICONS[m];
                return (
                  <label key={m}>
                    <input
                      type="radio"
                      name="theme"
                      value={m}
                      checked={mode === m}
                      onChange={() => setMode(m)}
                    />
                    <Icon aria-hidden="true" />
                    {SHORT[m]}
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="keys-title" data-tour="provider-keys">
        <div className="panel-header">
          <h3 className="panel-title" id="keys-title">
            Provider keys
          </h3>
        </div>
        <EmptyState
          icon={KeyRound}
          title="Manage API keys in the classic UI"
          action={<ClassicUiLink>Open key settings</ClassicUiLink>}
        >
          Gemini and NVIDIA keys are stored on the server and picked from the classic interface’s
          settings drawer. Encrypted, per-workspace credentials arrive in a later release.
        </EmptyState>
      </section>
    </div>
  );
}
