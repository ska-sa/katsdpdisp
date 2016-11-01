import logging
import sys
import atexit
from .data import Archive, DataFile, DataArchive, CorrProdRef, SignalDisplayFrame, SignalDisplayStore, NullReceiver
from .data import SpeadSDReceiver, SignalDisplayReceiver, AnimatablePlot, AnimatableSensorPlot, PlotAnimator
from .data import DataHandler, KATData

# Setup library logger, and suppress spurious logger messages via a null handler
class _NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger("katsdpdisp")
logger.addHandler(_NullHandler())
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(levelname)s: %(message)s")

# BEGIN VERSION CHECK
# Get package version when locally imported from repo or via -e develop install
try:
    import katversion as _katversion
except ImportError:
    import time as _time
    __version__ = "0.0+unknown.{}".format(_time.strftime('%Y%m%d%H%M'))
else:
    __version__ = _katversion.get_version(__path__[0])
# END VERSION CHEC
