import traceback
import sys

class Quitter(object):
    """Class used to override the default ipython exit behaviour when running fringe finder operations.

    Parameters
    ----------
    shell : IP
        The current IPython instance (if any). Used to handle gracefull shutdown.
    name : string
        The name of the command against which this Quitter object is registered. (e.g. exit)
    """
    def __init__(self, name, shell=None):
        self.shell = shell
        self.name = name
        self.top = None
        self._callbacks = []

    def sig_handler(self, signum, frame):
        print "Caught Ctrl-D :)"

    def deregister_callback(self, hash):
        """Deregister a previosuly registered callback function.

        Parameters
        ==========
        hash : integer
            The hash of the function registered in the callback
        """
        for cb in self._callbacks:
            if cb[1].__hash__() == hash:
                self._callbacks.remove(cb)

    def register_callback(self, name, callback):
        """Register a callback function that is executed on program termination.

        Parameters
        ==========
        name : string
            A descriptive name for this callback
        callback : function pointer
            The function to call

        Returns
        =======
        hash : string
            The function hash for use in deregister_callback
        """
        self._callbacks.append((name,callback))
        return callback.__hash__()

    def excepthook(self, e_class, e_instance, tb):
        print "Unhandled exception",str(e_class),":",e_instance
        print "Traceback (most recent call last):"
        traceback.print_tb(tb)
        sys.exit()

    def cleanup(self):
        while len(self._callbacks) > 0:
            callback = self._callbacks.pop()
            print "Running cleanup for",str(callback[0])
            try:
                callback[1]()
            except:
                pass

    def __repr__(self):
        return 'Use call syntax () to exit shell and close fringe finder connections.'

    __str__ = __repr__

    def __call__(self):
        self.cleanup()
        if self.shell is not None:
            self.shell.exit_now = True
        else:
            try:
                sys.exit()
            except:
                pass
