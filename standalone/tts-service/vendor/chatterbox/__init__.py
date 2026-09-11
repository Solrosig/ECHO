try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version  # For Python <3.8

__version__ = "0.1.2"  # Vendored upstream release; distribution metadata is not installed.


from .tts import ChatterboxTTS
from .vc import ChatterboxVC
