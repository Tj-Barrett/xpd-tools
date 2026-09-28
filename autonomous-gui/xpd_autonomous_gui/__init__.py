"""Browser GUI for xpd-tools autonomous campaigns, run from a BuildAgent config JSON."""

import warnings

# linear_operator (under Ax's BoTorch/GPyTorch) calls torch.jit.script on import, which
# newer torch warns about. Harmless; xpd-tools' pytest config ignores the same message.
warnings.filterwarnings(
    "ignore", message=r"`torch\.jit\.script` is deprecated", category=FutureWarning
)
