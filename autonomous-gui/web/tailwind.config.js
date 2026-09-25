import { colors } from './src/theme/colors.ts';

/** @type {import('tailwindcss').Config} */
// Same setup as finch (Tailwind v3 + PostCSS). finch.css already ships Tailwind's
// base reset, so preflight is off here to avoid loading it twice.
export default {
    content: ['./index.html', './src/**/*.{ts,tsx}'],
    corePlugins: { preflight: false },
    // Named colours (text-muted, bg-stop, …); edit them in src/theme/colors.ts.
    theme: { extend: { colors } },
    plugins: [],
};
