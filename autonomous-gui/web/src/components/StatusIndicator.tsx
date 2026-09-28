import { useAppStateQuery } from '@/api/autonomous/hooks';
import type { AppState } from '@/api/autonomous/types';

// Server status -> the three states worth noticing from across the room.
const RUNNING: AppState['status'][] = ['running', 'stopping'];

// Full class names so Tailwind finds them when scanning; colours in colors.ts `indicator`.
const STYLE = {
    Waiting: 'border-indicator-waiting-border text-indicator-waiting-text',
    Running: 'border-transparent bg-indicator-running text-indicator-running-text',
    Failed: 'border-transparent bg-indicator-failed text-indicator-failed-text animate-pulse',
};

/** Waiting / Running / Failed badge for the header, shown on every page. */
export default function StatusIndicator() {
    const { data, error } = useAppStateQuery();
    const label = error
        ? 'Failed'
        : data?.status === 'failed'
          ? 'Failed'
          : data && RUNNING.includes(data.status)
            ? 'Running'
            : 'Waiting';
    // Hover shows the exact status (e.g. "stopping", "finished") or why it failed.
    const detail = error
        ? `Can't reach server.py: ${error.message}`
        : (data?.error ?? data?.status);
    return (
        <span
            role="status"
            title={detail}
            className={`inline-block w-28 rounded-full border-2 py-1 text-center text-lg font-semibold ${STYLE[label]}`}
        >
            {label}
        </span>
    );
}
