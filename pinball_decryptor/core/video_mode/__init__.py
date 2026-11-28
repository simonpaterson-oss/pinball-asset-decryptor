"""Video modes: small screen games played with the flipper and Action buttons (PAD-1654 epic).

document.py reads and checks <project>/modes/<slug>/video_mode.json against
video_mode.schema.json; examples/ holds the plan's worked example."""

from .document import FORMAT, FILE_NAME, KIND, SCHEMA_PATH, VideoModeError, check, load, migrate, schema  # noqa: F401
