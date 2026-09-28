/** Response of server.py's GET /api/state (and of every action). */
export type AppState = {
    status:
        | 'empty'
        | 'loaded'
        | 'built'
        | 'running'
        | 'stopping'
        | 'finished'
        | 'stopped'
        | 'failed'
        | 'refill';
    error: string | null;
    mode: 'queue_server' | 'local' | null;
    config_dir: string;
    config_path: string | null;
    config: Record<string, any> | null;
    editable: 'all' | string[];
    trials: Record<string, any>[];
    trials_path: string | null;
    /** agent_data_path resolved to a file, and how many rows were ingested at Build. */
    historical: { path: string | null; count: number | null };
    /** Set when a syringe can't supply the next trial (status 'refill'). */
    refill: { message: string; pumps: string[] } | null;
    /** Iterations left in the campaign (run again after a refill). */
    remaining: number | null;
    /** Allowed values of fixed-choice fields by dotted path, e.g. 'xray.objective_function'. */
    choices: Record<string, (string | null)[]>;
    /** Fields picked from whole preset values by dotted path, e.g. 'run.local.simulated'. */
    presets: Record<string, Preset[]>;
};

/** One option of a preset dropdown: the value the field is set to when it's picked. */
export type Preset = { label: string; value: any };

/** Actions the GUI can ask server.py for; 'config' is PUT /api/config, the rest POST. */
export type Action = 'build' | 'run' | 'stop' | 'config' | 'load' | 'clear' | 'refilled';
