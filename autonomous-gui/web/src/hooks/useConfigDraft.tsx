import { createContext, useContext, useState, type ReactNode } from 'react';
import type { Json } from '@/types/json';

type Config = Record<string, Json>;

type DraftState = {
    /** The edited config, or null when nothing has been edited. */
    draft: Config | null;
    /** config_path the draft was edited from; a different loaded config hides it. */
    draftPath: string | null;
};

/** Unapplied Config-page edits, kept above the routes so switching pages keeps them. */
type ConfigDraft = DraftState & {
    /** The unapplied draft for `path`, or null if there isn't one. */
    draftFor: (path: string | null) => Config | null;
    /** Edit `path`'s config: continues its draft, or starts one from `base`. */
    edit: (base: Config, path: string | null, update: (current: Config) => Config) => void;
    /** Drop the draft (after Apply, Reset, or loading another config). */
    discard: () => void;
};

const ConfigDraftContext = createContext<ConfigDraft | null>(null);

/** Holds the Config page's draft for the whole app (wrap the routes in it). */
export function ConfigDraftProvider({ children }: { children: ReactNode }) {
    // One state object, updated in one step, so a draft never mixes two configs.
    const [state, setState] = useState<DraftState>({ draft: null, draftPath: null });
    const value: ConfigDraft = {
        ...state,
        draftFor: (path) => (state.draft !== null && state.draftPath === path ? state.draft : null),
        edit: (base, path, update) =>
            setState((current) => ({
                draft: update(
                    current.draft !== null && current.draftPath === path ? current.draft : base,
                ),
                draftPath: path,
            })),
        discard: () => setState({ draft: null, draftPath: null }),
    };
    return <ConfigDraftContext.Provider value={value}>{children}</ConfigDraftContext.Provider>;
}

/** The shared Config-page draft; needs a ConfigDraftProvider above it. */
export function useConfigDraft(): ConfigDraft {
    const value = useContext(ConfigDraftContext);
    if (!value) throw new Error('useConfigDraft needs a ConfigDraftProvider above it');
    return value;
}
