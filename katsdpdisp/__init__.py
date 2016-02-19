import logging
import sys
import atexit
from .data import quitter, Archive, DataFile, DataArchive, CorrProdRef, SignalDisplayFrame, SignalDisplayStore, NullReceiver
from .data import SpeadSDReceiver, SignalDisplayReceiver, AnimatablePlot, AnimatableSensorPlot, PlotAnimator
from .data import DataHandler, KATData

# Setup library logger, and suppress spurious logger messages via a null handler
class _NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger("katsdpdisp")
logger.addHandler(_NullHandler())
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(levelname)s: %(message)s")


try:
    import IPython.ipapi
    ip = IPython.ipapi.get()
    if ip is not None:
        # setup new exit handlers
        ip.IP.exit = exit
        quitter.shell = ip.IP
        ip.user_ns['exit'] = quitter
        ip.user_ns['quit'] = ip.user_ns['exit']
except:
    pass
     # no ipython stuff to handle

atexit.register(quitter)
sys.excepthook = quitter.excepthook


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
