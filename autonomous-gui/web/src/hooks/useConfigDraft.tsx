import { createContext, useContext, useState, type ReactNode } from 'react';
import type { Json } from '@/types/json';

/** Unapplied Config-page edits, kept above the routes so switching pages keeps them. */
type ConfigDraft = {
    /** The edited config, or null before the first load. */
    draft: Record<string, Json> | null;
    /** config_path the draft was taken from; a different loaded config drops the draft. */
    draftPath: string | null;
    /** True once edited and until applied or reset. */
    dirty: boolean;
    setDraft: (
        update: (current: Record<string, Json> | null) => Record<string, Json> | null,
    ) => void;
    follow: (config: Record<string, Json>, path: string | null) => void;
    setDirty: (dirty: boolean) => void;
};

const ConfigDraftContext = createContext<ConfigDraft | null>(null);

/** Holds the Config page's draft for the whole app (wrap the routes in it). */
export function ConfigDraftProvider({ children }: { children: ReactNode }) {
    const [draft, setDraftState] = useState<Record<string, Json> | null>(null);
    const [draftPath, setDraftPath] = useState<string | null>(null);
    const [dirty, setDirty] = useState(false);
    const value: ConfigDraft = {
        draft,
        draftPath,
        dirty,
        setDraft: (update) => setDraftState(update),
        // Replace the draft with the server's config (not editing, or a new config).
        follow: (config, path) => {
            setDraftState(config);
            setDraftPath(path);
            setDirty(false);
        },
        setDirty,
    };
    return <ConfigDraftContext.Provider value={value}>{children}</ConfigDraftContext.Provider>;
}

/** The shared Config-page draft; needs a ConfigDraftProvider above it. */
export function useConfigDraft(): ConfigDraft {
    const value = useContext(ConfigDraftContext);
    if (!value) throw new Error('useConfigDraft needs a ConfigDraftProvider above it');
    return value;
}
