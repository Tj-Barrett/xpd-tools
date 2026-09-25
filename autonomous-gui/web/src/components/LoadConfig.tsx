import { useState } from 'react';
import { Button, SelectDropdown } from '@/components/themed';
import { useActionMutation, useAppStateQuery, useConfigsQuery } from '@/api/autonomous/hooks';

/** Pick a config JSON from the server's config directory and load it. */
export default function LoadConfig() {
    const { data } = useAppStateQuery();
    const { data: configs } = useConfigsQuery();
    const action = useActionMutation();
    const [choice, setChoice] = useState<string | null>(null);

    const running = data?.status === 'running' || data?.status === 'stopping';
    const dirty = data?.status !== 'empty' && data?.status !== 'loaded';
    const filled = data?.status === 'loaded';
    // One reserved line for whichever hint applies, so it never pushes the page down.
    const hint = action.isError
        ? action.error.message
        : running
          ? 'Stop the campaign to load another config.'
          : filled
            ? 'Build the RunAgent using the config.'
            : null;

    return (
        <div>
            <b>Load a config from the server's config directory.</b>
            <div className="my-3 flex flex-wrap items-center gap-3">
                <div className="w-80">
                    <SelectDropdown
                        listItems={configs ?? []}
                        placeholder={configs?.length ? 'Choose a config…' : 'No .json files found'}
                        onValueChange={setChoice}
                    />
                </div>
                <Button
                    text="Load"
                    size="small"
                    disabled={!choice || running || action.isPending}
                    onClick={() => {
                        if (dirty && !window.confirm('Loading drops the current agent. Continue?'))
                            return;
                        action.mutate({ action: 'load', body: { path: choice } });
                    }}
                />
                {/*<span className="text-sm text-muted">from {data?.config_dir}</span>*/}
            </div>
            <p
                className={`min-h-6 whitespace-pre-wrap ${action.isError ? 'text-error' : 'text-sm text-muted'}`}
            >
                {hint}
            </p>
        </div>
    );
}
