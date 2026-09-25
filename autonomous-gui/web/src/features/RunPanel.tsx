import { Button, Paper } from '@/components/themed';
import { useActionMutation, useAppStateQuery } from '@/api/autonomous/hooks';
import LoadConfig from '@/components/LoadConfig';

// Status pill colours; full class names so Tailwind finds them when scanning.
const STATUS_COLOR: Record<string, string> = {
    empty: 'bg-status-empty',
    loaded: 'bg-status-loaded',
    built: 'bg-status-built',
    running: 'bg-status-running',
    stopping: 'bg-status-stopping',
    finished: 'bg-status-finished',
    stopped: 'bg-status-stopped',
    failed: 'bg-status-failed',
};

/** Build / run / stop the campaign and show its status. */
export default function RunPanel() {
    const { data, error } = useAppStateQuery();
    const action = useActionMutation();

    if (error)
        return (
            <Paper title="Run">
                <p className="my-2 whitespace-pre-wrap text-error">
                    Can't reach server.py: {error.message}
                </p>
            </Paper>
        );
    if (!data) return <Paper title="Run">Loading…</Paper>;
    if (!data.config) {
        return (
            <Paper title="Run">
                <LoadConfig />
                <p>No config loaded. Choose one above.</p>
            </Paper>
        );
    }

    const running = data.status === 'running' || data.status === 'stopping';
    const run = data.config.run;
    const criteria = data.config.success_criteria;
    const busy = action.isPending;
    const historical = data.historical;
    const historicalCount = historical.count ?? 0;
    // Why Clear is unavailable, shown next to it (a disabled outline button looks nearly enabled).
    const clearHint = running
        ? 'Stop the campaign and let it end to enable Clear'
        : data.status === 'loaded'
          ? 'Nothing to clear: no agent has been built'
          : null;
    const cleared = action.isSuccess && action.variables?.action === 'clear';
    // One reserved line under the buttons for the most relevant message, so it never
    // pushes the page around.
    const message = action.isError
        ? { text: action.error.message, isError: true }
        : data.error
          ? { text: `Last error: ${data.error}`, isError: true }
          : busy
            ? { text: 'Working… (building can take a while)', isError: false }
            : cleared && data.status === 'loaded'
              ? {
                    text: 'Cleared: the built agent and its trials were dropped. Build to start again.',
                    isError: false,
                }
              : null;

    return (
        <Paper>
            <dl className="my-2 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 [&_dt]:font-semibold">
                {/*<dt>Run</dt>
        <dd>Please select a run configuration below.</dd>*/}
            </dl>
            <LoadConfig />
            <dl className="my-2 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 [&_dt]:font-semibold">
                {/* Status Section */}
                <dt>Status</dt>
                <dd>
                    <span
                        className={`rounded-full px-2.5 py-0.5 ${STATUS_COLOR[data.status] ?? 'bg-status-empty'}`}
                    >
                        {data.status}
                    </span>
                </dd>
                {/* Mode Section */}
                <dt>Mode</dt>
                <dd>{data.mode === 'queue_server' ? 'Queue Server' : 'Local simulation'}</dd>
                {/* Evaluation Section */}
                <dt>Evaluation</dt>
                <dd>{data.config.evaluation_method}</dd>
                {/* Progress Section */}
                <dt>Progress</dt>
                <dd>
                    {historicalCount > 0
                        ? `${historicalCount} historical + ${data.trials.length - historicalCount} new trials`
                        : `${data.trials.length} trials`}{' '}
                    · {run.iterations} iterations × {run.n_points} point
                    {run.n_points === 1 ? '' : 's'} planned
                </dd>
                {/* Historical data: always shown so the rows below don't move */}
                <dt>Historical</dt>
                <dd className="min-w-0 truncate" title={historical.path ?? ''}>
                    {historical.path ? (
                        <>
                            {historical.path.split('/').pop()}
                            <span className="text-sm text-muted">
                                {' '}
                                ·{' '}
                                {historical.count === null
                                    ? 'loaded at Build'
                                    : `${historical.count} trials ingested`}
                            </span>
                        </>
                    ) : (
                        'none'
                    )}
                </dd>
                {/* Success Criteria Section */}
                <dt>Success criteria</dt>
                <dd>
                    {criteria
                        ? Object.entries(criteria)
                              .filter(([, v]) => v !== null)
                              .map(([k, v]) => `${k} = ${v}`)
                              .join(', ')
                        : 'none (runs all iterations)'}
                </dd>
                {/* Config Section */}
                {/* Paths stay on one line (full path on hover), and the Trials saved row is
                    always there, so the buttons below don't move when a campaign ends. */}
                <dt>Config</dt>
                <dd className="min-w-0 truncate text-sm text-muted" title={data.config_path ?? ''}>
                    {data.config_path}
                </dd>
                <dt>Trials saved</dt>
                <dd className="min-w-0 truncate text-sm text-muted" title={data.trials_path ?? ''}>
                    {data.trials_path ?? '—'}
                </dd>
            </dl>

            {/* Populate Build, Run, Stop Buttons */}
            <div className="my-3 flex flex-wrap items-center gap-3">
                <Button
                    text="Build"
                    disabled={busy || running}
                    onClick={() => action.mutate({ action: 'build' })}
                />
                <Button
                    text="Run"
                    disabled={busy || running || data.status === 'loaded'}
                    onClick={() => action.mutate({ action: 'run' })}
                />
                <Button
                    text="Stop"
                    className="bg-stop hover:bg-stop-hover text-stop-text"
                    disabled={busy || data.status !== 'running'}
                    onClick={() => action.mutate({ action: 'stop' })}
                />
                <Button
                    text="Clear"
                    isSecondary
                    disabled={busy || running || data.status === 'loaded'}
                    onClick={() => {
                        if (
                            window.confirm(
                                'Clear the built agent and its trials? (The trials CSV is kept.)',
                            )
                        )
                            action.mutate({ action: 'clear' });
                    }}
                />
                {clearHint && <span className="text-sm text-muted">{clearHint}</span>}
            </div>
            <p
                className={`min-h-6 whitespace-pre-wrap ${message?.isError ? 'text-error' : 'text-sm text-muted'}`}
            >
                {message?.text}
            </p>
        </Paper>
    );
}
