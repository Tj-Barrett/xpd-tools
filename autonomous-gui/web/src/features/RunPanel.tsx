import { Button, Paper } from '@/components/themed';
import { useActionMutation, useAppStateQuery } from '@/api/autonomous/hooks';
import LoadConfig from '@/components/LoadConfig';
import { useConfigDraft } from '@/hooks/useConfigDraft';

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
    refill: 'bg-status-refill',
};

/** Build / run / stop the campaign and show its status. */
export default function RunPanel() {
    const { data, error } = useAppStateQuery();
    const action = useActionMutation();
    const { draftFor } = useConfigDraft();

    if (error)
        return (
            <Paper>
                <p className="my-2 whitespace-pre-wrap text-error">
                    Can't reach server.py: {error.message}
                </p>
            </Paper>
        );
    if (!data) return <Paper>Loading…</Paper>;
    if (!data.config) {
        return (
            <Paper>
                <LoadConfig />
                <p>No config loaded. Choose one above.</p>
            </Paper>
        );
    }

    const running = data.status === 'running' || data.status === 'stopping';
    const run = data.config.run;
    const criteria = data.config.success_criteria;
    // This page's own request in flight, or a Build running (e.g. from another tab).
    const busy = action.isPending || data.building;
    // Running with no RUNNING trial: Ax is still generating the next suggestion (instant
    // for Sobol, tens of seconds once the model takes over), so no trial exists yet.
    const choosing =
        data.status === 'running' && !data.trials.some((t) => t.trial_status === 'RUNNING');
    const unappliedConfig = draftFor(data.config_path) !== null;
    const historical = data.historical;
    const historicalCount = historical.count ?? 0;
    // What Ax does before the model takes over, from run.extra_initialization_trials /
    // run.generation_strategy (see BuildAgent.configure_generation_strategy).
    const afterHistory = historical.path
        ? historical.count === null
            ? ' after the historical trials'
            : ` after the ${historical.count} historical`
        : '';
    const budget = run.generation_strategy?.initialization_budget;
    const exploration =
        run.extra_initialization_trials != null
            ? `${run.extra_initialization_trials} Sobol trials${afterHistory}, then model-guided`
            : budget != null
              ? `Sobol until ${budget} trials in total, then model-guided`
              : "Ax's default generation strategy";
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
        : data.refill
          ? {
                text: `${data.refill.message} Refill, then press Refilled — continue (it resets their volume counters).`,
                isError: false,
                isRefill: true,
            }
          : data.error
            ? { text: `Last error: ${data.error}`, isError: true }
            : busy
              ? {
                    text: data.building
                        ? 'Building the agent… (can take a while)'
                        : 'Working… (building can take a while)',
                    isError: false,
                }
              : choosing
                ? {
                      text: 'Choosing the next point (fitting the model; can take ~30 s per trial)…',
                      isError: false,
                  }
                : unappliedConfig
                  ? {
                        text: 'The Config page has unapplied changes: press Apply there to use them.',
                        isError: false,
                    }
                  : cleared && data.status === 'loaded'
                    ? {
                          text: 'Cleared: the built agent and its trials were dropped. Build to start again.',
                          isError: false,
                      }
                    : null;

    return (
        <Paper>
            {/* Kept for later; as an empty <dl> its margins pushed the card's content down.
            <dl className="my-2 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 [&_dt]:font-semibold">
                <dt>Run</dt>
                <dd>Please select a run configuration below.</dd>
            </dl> */}
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
                    · {run.iterations} iterations planned
                    {data.status === 'refill' && ` · ${data.remaining} left after the refill`}
                </dd>
                <dt>Exploration</dt>
                <dd>{exploration}</dd>
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
                    disabled={busy || running || data.status === 'loaded' || !!data.refill}
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
                {data.refill && (
                    <Button
                        text="Refilled — continue"
                        disabled={busy}
                        onClick={() => action.mutate({ action: 'refilled' })}
                    />
                )}
                {clearHint && <span className="text-sm text-muted">{clearHint}</span>}
            </div>
            <p
                className={`min-h-6 whitespace-pre-wrap ${
                    message?.isError
                        ? 'text-error'
                        : message && 'isRefill' in message
                          ? 'font-semibold text-refill'
                          : 'text-sm text-muted'
                }`}
            >
                {message?.text}
            </p>
        </Paper>
    );
}
