/** Any JSON value, as found in a BuildAgent config. */
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
