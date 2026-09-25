// Every colour the autonomous GUI uses, including finch's own components. Change a value
// here and all pages follow (restart `npm run dev` / `npm run storybook`, or `npm run build`
// for server.py). The defaults reproduce finch's look.
//
// Values are Tailwind palette colours (https://v3.tailwindcss.com/docs/customizing-colors),
// e.g. palette.red[500], or any CSS colour such as '#dc2626' ('#ffffff80' = 50% white).
import palette from 'tailwindcss/colors';

/**
 * Colours used as Tailwind classes. Each name becomes classes such as `bg-sidebar`,
 * `text-muted`, `hover:bg-stop-hover` (nested names join with `-`).
 */
export const colors = {
    // Page frame (finch FinchAppLayout, applied in app/App.tsx)
    header: {
        DEFAULT: palette.white, // header bar
        title: palette.sky[950], // "XPD Autonomous Experimentation"
        logo: palette.black, // header icon
    },
    sidebar: {
        DEFAULT: palette.sky[950], // sidebar background
        text: palette.white, // page links
        hover: palette.sky[800], // link under the mouse
        active: palette.sky[300], // current page's link
        'active-text': palette.black,
        divider: '#ffffff80', // lines between links
    },
    page: palette.sky[900], // background around the cards

    // Cards (finch Paper, components/themed.tsx)
    card: {
        DEFAULT: palette.white,
        title: palette.sky[900], // e.g. "Config", "Trials (40)"
        text: palette.black,
    },

    // Buttons (finch Button, components/themed.tsx)
    primary: {
        DEFAULT: palette.sky[500], // Build, Run, Load, Apply
        hover: palette.sky[600],
        text: palette.white,
    },
    secondary: {
        DEFAULT: '#ffffff80', // Clear, Reset, Add success criteria
        hover: palette.slate[200],
        text: palette.black,
        border: palette.gray[200],
    },
    stop: {
        DEFAULT: palette.red[500], // Stop
        hover: palette.red[600],
        text: palette.white,
    },

    // Inputs
    select: {
        DEFAULT: palette.sky[900], // "Choose a config…"
        option: palette.sky[600], // file names in the open list
        menu: palette.white, // open list background
    },
    checkbox: {
        DEFAULT: palette.black, // box border and tick
        box: palette.white, // box fill
        label: palette.black, // label when ticked
        'label-hover': palette.slate[400],
        'label-off': palette.slate[500], // label when unticked
        'label-off-hover': palette.slate[900],
    },

    // Text and lines in our panels
    muted: palette.slate[500], // paths, hints, "Working…"
    error: palette.red[700], // error messages
    line: {
        DEFAULT: palette.slate[300], // input and group borders
        subtle: palette.slate[200], // trial-table row lines
    },
    surface: {
        DEFAULT: palette.white, // inputs, table header
        disabled: palette.slate[100], // locked inputs
    },

    // Divider between historical and new trials (Trials plots and table)
    history: palette.slate[500],

    // Config tile backgrounds by nesting depth (tile, tile inside it, …); repeats after 3
    nest: {
        1: palette.slate[50],
        2: palette.slate[100],
        3: palette.slate[200],
    },

    // Status pill on the Run page, one per server status
    status: {
        empty: palette.slate[200],
        loaded: palette.amber[200],
        built: palette.green[200],
        running: palette.green[200],
        stopping: palette.amber[200],
        finished: palette.green[200],
        stopped: palette.red[200],
        failed: palette.red[200],
    },
};

/** Trials plots. Plotly draws these itself, so they're passed in code (features/TrialsPanel.tsx). */
export const plot = {
    background: '#E2E8F0',
    text: '#444444', // title, tick labels, legend
    axisTitle: '#082f49', // "trial"
    grid: '#d4d9e0', // Plotly's automatic grid colour on this background
    zeroLine: '#444444',
    // One colour per line, in order (Plotly's defaults); repeats after the last.
    lines: [
        '#1f77b4',
        '#ff7f0e',
        '#2ca02c',
        '#d62728',
        '#9467bd',
        '#8c564b',
        '#e377c2',
        '#7f7f7f',
        '#bcbd22',
        '#17becf',
    ],
};
