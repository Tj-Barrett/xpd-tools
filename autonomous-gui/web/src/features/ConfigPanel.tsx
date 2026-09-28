import { useEffect } from 'react';
import { Button, Paper } from '@/components/themed';
import { useActionMutation, useAppStateQuery, useCsvsQuery } from '@/api/autonomous/hooks';
import ConfigField, { ConfigGroup, isGroup } from '@/components/ConfigField';
import { Json } from '@/types/json';
import { setAt } from '@/utils/configUtils';
import { useConfigDraft } from '@/hooks/useConfigDraft';

// Mirrors xpd_tools.optimization.stopping.SuccessCriteria's fields and defaults.
const EMPTY_SUCCESS_CRITERIA: Json = {
    min_correlation: null,
    max_fwhm: null,
    min_plqy: null,
    poll_interval: 5.0,
};

/** Edit the loaded config; while running, only the server's `editable` keys unlock. */
export default function ConfigPanel() {
    const { data } = useAppStateQuery();
    const action = useActionMutation();
    const { data: csvs } = useCsvsQuery();
    // Shared with the whole app, so leaving this page keeps unapplied edits.
    const { draft, draftPath, dirty, setDraft, follow, setDirty } = useConfigDraft();

    // Follow the server's config, unless editing this same config: a different one
    // (loaded, or an edit applied) replaces the draft.
    useEffect(() => {
        if (data?.config && (!dirty || data.config_path !== draftPath))
            follow(data.config, data.config_path);
        // eslint-disable-next-line react-hooks/exhaustive-deps -- follow is recreated each render
    }, [data, dirty, draftPath]);

    if (data && !data.config) return <Paper>No config loaded; load one on the Run page.</Paper>;
    if (!data || !draft) return <Paper>Loading…</Paper>;
    const editable = (key: string) => data.editable === 'all' || data.editable.includes(key);
    const onChange = (path: (string | number)[], next: Json) => {
        setDraft((current) => setAt(current, path, next) as Record<string, Json>);
        setDirty(true);
    };
    // Top-level single values (evaluation_method, …) share a "general" tile, so every field
    // sits in a tile. Display only: they stay top-level keys in the JSON.
    const entries = Object.entries(draft);
    const general = entries.filter(([, value]) => !isGroup(value));
    const groups = entries.filter(([, value]) => isGroup(value));
    const generalLocked = general.every(([key]) => !editable(key));
    // One reserved line under the buttons, so notes and errors never push the form down.
    const notice = action.isError
        ? { text: action.error.message, isError: true }
        : dirty
          ? {
                text: 'Unapplied changes: press Apply to use them (Reset discards them)',
                isError: false,
            }
          : data.editable !== 'all'
            ? { text: `Running: only ${data.editable.join(', ')} can change`, isError: false }
            : null;

    return (
        <Paper>
            {/* Path on its own line (full path on hover), then buttons that are always there,
                then a reserved notice line: nothing shifts as the state changes. Sticky, so
                Apply stays in view while editing fields further down. */}
            <div className="sticky top-0 z-10 bg-card">
                <p className="min-w-0 truncate text-sm text-muted" title={data.config_path ?? ''}>
                    {data.config_path}
                </p>
                <div className="my-3 flex flex-wrap items-center gap-3">
                    <Button
                        text="Apply"
                        size="small"
                        disabled={!dirty || action.isPending}
                        onClick={() =>
                            action.mutate(
                                { action: 'config', body: draft },
                                { onSuccess: () => setDirty(false) },
                            )
                        }
                    />
                    <Button
                        text="Reset"
                        size="small"
                        isSecondary
                        disabled={!dirty}
                        onClick={() => follow(data.config!, data.config_path)}
                    />
                    <Button
                        text="Add success criteria"
                        size="small"
                        isSecondary
                        disabled={draft.success_criteria !== null}
                        onClick={() => {
                            setDraft((current) => ({
                                ...current!,
                                success_criteria: EMPTY_SUCCESS_CRITERIA,
                            }));
                            setDirty(true);
                        }}
                    />
                </div>
                <p
                    className={`min-h-6 whitespace-pre-wrap ${notice?.isError ? 'text-error' : 'text-sm text-muted'}`}
                >
                    {notice?.text}
                </p>
            </div>
            <div className="flex flex-col gap-2">
                {general.length > 0 && (
                    <ConfigGroup name="general" depth={0} dim={generalLocked}>
                        {general.map(([key, value]) => (
                            <ConfigField
                                key={key}
                                name={key}
                                value={value}
                                path={[key]}
                                disabled={!editable(key)}
                                depth={1}
                                parentDisabled={generalLocked}
                                // Historical data: pick a CSV from the config folder
                                choices={key === 'agent_data_path' ? (csvs ?? []) : undefined}
                                onChange={onChange}
                            />
                        ))}
                    </ConfigGroup>
                )}
                {groups.map(([key, value]) => (
                    <ConfigField
                        key={key}
                        name={key}
                        value={value}
                        path={[key]}
                        disabled={!editable(key)}
                        onChange={onChange}
                    />
                ))}
            </div>
        </Paper>
    );
}
