import { PlotlyScatter } from '@blueskyproject/finch';
import { Paper } from '@/components/themed';
import { colors, plot } from '@/theme/colors';
import { useAppStateQuery } from '@/api/autonomous/hooks';

const CELL = 'whitespace-nowrap border-b border-line-subtle px-2.5 py-1 text-right';

// Ax summarize() bookkeeping columns, not objectives or DOFs.
const META = new Set(['trial_index', 'arm_name', 'trial_status', 'generation_node']);

// Plot colours from src/theme/colors.ts (Plotly takes them in code, not as classes).
const PLOT_LAYOUT = {
    plot_bgcolor: plot.background,
    paper_bgcolor: plot.background,
    colorway: plot.lines,
    font: { color: plot.text },
};
const Y_AXIS = { gridcolor: plot.grid, zerolinecolor: plot.zeroLine };
const X_AXIS = {
    ...Y_AXIS,
    title: { text: 'trial', font: { size: 16, color: plot.axisTitle } },
};

/** Dashed line between historical trials (0..count-1) and new ones, with labels. */
function historyDivider(count: number) {
    const x = count - 0.5;
    const label = (text: string, xanchor: 'left' | 'right') => ({
        x,
        y: 1,
        xref: 'x' as const,
        yref: 'paper' as const,
        text,
        xanchor,
        yanchor: 'top' as const,
        showarrow: false,
        font: { size: 11, color: colors.history },
    });
    return {
        shapes: [
            {
                type: 'line' as const,
                x0: x,
                x1: x,
                y0: 0,
                y1: 1,
                xref: 'x' as const,
                yref: 'paper' as const,
                line: { color: colors.history, width: 2, dash: 'dash' as const },
            },
        ],
        annotations: [label('historical ◂ ', 'right'), label(' ▸ new', 'left')],
    };
}

/** One line+marker trace per column, against trial index. */
function traces(trials: Record<string, any>[], columns: string[]) {
    return columns.map((column) => ({
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: column,
        x: trials.map((t) => t.trial_index),
        y: trials.map((t) => t[column]),
    }));
}

/** Objectives and DOF values per trial, plus the raw table. */
export default function TrialsPanel() {
    const { data } = useAppStateQuery();
    if (!data) return <Paper title="Trials">Loading…</Paper>;

    // Plots and the table are always laid out (empty until the first trial), and the table
    // area has a fixed height and scrolls, so the page doesn't grow as trials arrive.
    const trials = data.trials;
    const columns = trials.length ? Object.keys(trials[0]) : [];
    const dofs = new Set<string>((data.config?.experiment?.sources ?? []).map((s: any) => s.dof));
    const dofColumns = columns.filter((c) => dofs.has(c));
    const objectiveColumns = columns.filter((c) => !META.has(c) && !dofs.has(c));
    const historicalCount = data.historical.count ?? 0;
    const layout =
        historicalCount > 0 ? { ...PLOT_LAYOUT, ...historyDivider(historicalCount) } : PLOT_LAYOUT;

    return (
        <Paper title={`Trials (${trials.length})`}>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(22rem,1fr))] gap-4">
                <PlotlyScatter
                    title="Objectives"
                    xAxisTitle="trial"
                    data={traces(trials, objectiveColumns)}
                    layout={layout}
                    xAxisLayout={X_AXIS}
                    yAxisLayout={Y_AXIS}
                    className="h-72"
                />
                <PlotlyScatter
                    title="DOFs"
                    xAxisTitle="trial"
                    data={traces(trials, dofColumns)}
                    layout={layout}
                    xAxisLayout={X_AXIS}
                    yAxisLayout={Y_AXIS}
                    className="h-72"
                />
            </div>
            <div className="mt-4 h-80 overflow-auto">
                {trials.length === 0 && <p className="p-2 text-sm text-muted">No trials yet.</p>}
                <table className="border-collapse text-sm">
                    <thead>
                        <tr>
                            {columns.map((c) => (
                                <th key={c} className={`${CELL} sticky top-0 bg-surface`}>
                                    {c}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {[...trials].reverse().map((t) => (
                            <tr
                                key={t.trial_index}
                                // Newest first, so the newest historical row carries the divider.
                                className={
                                    t.trial_index === historicalCount - 1
                                        ? 'border-t-2 border-dashed border-history'
                                        : ''
                                }
                            >
                                {columns.map((c) => (
                                    <td key={c} className={CELL}>
                                        {typeof t[c] === 'number'
                                            ? Number(t[c].toPrecision(4))
                                            : String(t[c] ?? '')}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Paper>
    );
}
