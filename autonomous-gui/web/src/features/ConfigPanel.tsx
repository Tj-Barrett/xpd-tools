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
    const { draftFor, edit, discard } = useConfigDraft();

    if (data && !data.config) return <Paper>No config loaded; load one on the Run page.</Paper>;
    if (!data?.config) return <Paper>Loading…</Paper>;
    const server = data.config;
    // Unapplied edits of this config, else the server's copy: nothing to keep in sync.
    // (Applying saves under a new config_path, so the old draft no longer matches.)
    const pending = draftFor(data.config_path);
    const draft = pending ?? server;
    // Dropdowns: the server's fixed choices, plus the config folder's CSVs (or none) for
    // historical data.
    const choices = { ...data.choices, agent_data_path: [null, ...(csvs ?? [])] };
    const dirty = pending !== null;
    const editable = (key: string) => data.editable === 'all' || data.editable.includes(key);
    const onChange = (path: (string | number)[], next: Json) =>
        edit(
            server,
            data.config_path,
            (current) => setAt(current, path, next) as Record<string, Json>,
        );
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
                            action.mutate({ action: 'config', body: draft }, { onSuccess: discard })
                        }
                    />
                    <Button
                        text="Reset"
                        size="small"
                        isSecondary
                        disabled={!dirty}
                        onClick={discard}
                    />
                    <Button
                        text="Add success criteria"
                        size="small"
                        isSecondary
                        disabled={draft.success_criteria !== null}
                        onClick={() =>
                            edit(server, data.config_path, (current) => ({
                                ...current,
                                success_criteria: EMPTY_SUCCESS_CRITERIA,
                            }))
                        }
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
                                choices={choices}
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
                        choices={choices}
                        onChange={onChange}
                    />
                ))}
            </div>
        </Paper>
    );
}
