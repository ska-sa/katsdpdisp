# A library for receiving and interacting with online signal display data.
#
# The useful things herein are:
#    AnimatablePlot - generally not called directly, but all plot commands return an instance of this class to allow the plot to be animated
#    SignalDisplayFrame - in signal display parlance a frame is the complex spectrum for a single correlator product id for a single dump.
#                       - internally the data is stored as a np.float32 array of size CHANNELS*2. A number of helper functions provide views such as complex, re, im, mag, phase
#    SignalDisplayStore - a class to store and group a bunch of SignalDisplayFrame. By default 3600 frames for each unique product id are stored.
#    SignalDisplayReceiver - receives signal display frames (or parts thereof) and places them in the store.
#    DataHandler - High level object that holds all plots and utility functions for interacting with a SignalDisplayStore.
#
# Fundamentally all the signal display addressing uses what we call correlator product id's. Each invididual correlation product
# produced by a correlator is assigned a unique correlation product id. (e.g. 0x * 0y). This avoid issues such as combinations of
# single pol and dual pol antennas connected to the same correlator causing problems with traditional baseline/polarisation indexing.
#

import threading
import socket
import logging
import numpy as np
import time
import warnings
import sys
from struct import unpack
from .quitter import Quitter

quitter = Quitter("exit")
 # create a quitter to handle exit conditions

logger = logging.getLogger("katsdisp.data")

try:
    import matplotlib.pyplot as pl
    import matplotlib.lines
except:
    pl = None
    warnings.warn("Could not import matplotlib.pyplot -- plotting functions will not work.")

class Archive(object):
    """An archive containing telescope data.

    Parameters
    ----------
    ip : string
        The IP address (or FQDN) of the archive
    user : string
        default: ffuser
        The username to use when connecting to the archive
    password : string
        default: None
        The password associated with the provided username. Ideally the user will have key based access to the remote archive.
    data_directory : string
        default: /data
        The base directory to use when querying the archive
    """
    def __init__(self, ip, user="ffuser", password=None, data_directory='/data'):
        self.ip = ip
        self.user = user
        self.password = password
        self.data_directory = data_directory
        from .utility import FFNode
        self.node = FFNode(ip,ip)

class DataFile(object):
    """A reference to a data file stored in an archive.
    """
    def __init__(self, archive, file_name, full_name, size_b, samples, date_created, date_modified, date_augmented=None, target=None):
        self.archive = archive
        self.file_name = file_name
        self.full_name = full_name
        self.size_b = size_b
        self.samples = samples
        self._date_created_s = date_created
        self.data_created = time.ctime(date_created)
        self._date_modified_s = date_modified
        self.date_modified = time.ctime(date_modified)
        self.date_augmented = date_augmented
        self.target = target

class DataArchive(object):
    """A class for exploring a remote data archive.
    Generally all the telescope data will be archived in one or more locations. This may take
    the form of raw correlator data, intermediate products or science ready products such as images.
    This class provides a portal for exploring these archives and discovering what products are
    available.
    Objects can then be handed off to remote processing tasks or used in objects
    such as the RemoteSignalDisplayStore (provides local signal display processing on a remote data file)

    Parameters
    ----------
    archive : Archive
        The primary archive to use
    """
    def __init__(self, archive):
        self.archives = {'primary':archive}
        self.files = {}

    def add_archive(self, archive_name, archive):
        if self._archive_ips.has_key(archive_name):
            logger.warn("Archive name " + str(archive_name) + " already exists. Replacing with newly specified archive")
        self.archives[archive_name] = archive

    def list_files(self, archive_name='primary'):
        self.files = {}
        a = self.archives[archive_name]
        ret = a.node.rexec_block('cd ' + str(a.data_directory) + '; /usr/local/bin/archive_ls.sh','ffuser')
        print "Index".ljust(5), "Filename".ljust(65), "Size (GB)".ljust(9),"Samples".ljust(8), "Date Created".ljust(25), "Last Modified".ljust(25), "Date Augmented".ljust(25), "Target".ljust(60)
        print "".center(5,"="),"".center(65,"="), "".center(9,"="), "".center(8,"="), "".center(25,"="), "".center(25,"="), "".center(25,"="), "".center(60,"=")
        index = 1
        for line in ret[0].split("\n"):
            if line.startswith("File"):
                f = line.split(" ")
                sz = "%.02f" % (float(f[2]) / (1024 * 1024))
                try:
                    created = time.ctime(int(f[1].split("/")[-1].split(".")[0]))
                except ValueError:
                    # no create timestamp encoded in filename. Will use stat time
                    created = "*" + time.ctime(int(f[4]))
                modified = time.ctime(int(f[5]))
                print str(index).ljust(5),f[1].ljust(65),sz.ljust(9),f[6].ljust(8),created.ljust(25),modified.ljust(25),
                df = DataFile(a, f[1].split("/")[-1], str(a.data_directory) + f[1], int(f[2]), int(f[6]), int(f[4]), int(f[5]))
            if line.startswith("Augmented: Augment"):
                aug_date = " ".join(line.split(" ")[4:])
            if line.rfind("Target") > -1:
                if line.startswith("Target:"):
                    tgt = line[8:]
                else:
                    aug_date = "N/A"
                    tgt = line[19:]
                if tgt.rfind("Data:") > 0:
                    tgt = "None specified"
                print aug_date.ljust(25),tgt.ljust(60)
                # marks the end of a file entry
                df.target = tgt
                df.date_augmented = aug_date
                self.files[index] = df
                index += 1


class CorrProdRef(object):
    """A small wrapper class to handle interaction with and
    conversion to and frame correlator product id's and real world
    antennas and polarisations.

    The object stores the current mapping between correlator inputs and real antennas.

    A correlation product id refers to a single pol from a single correlated antenna pair.

    Parameters
    ----------
    n_ants : integer
        The number of antenna inputs in the dbe. Usually total number of dbe inputs / 2
    katconfig : config
        If supplied then this configuration is used for n_ants as well as for physical antenna to dbe input mapping.
        default: None
    """

    def __init__(self, n_ants=2, katconfig=None):
        self._dbe_to_real = {}
        self._real_to_dbe = {}
         # not really necessary to have both, but it is convenient :)
        self.n_ants = n_ants
        self._katconfig = katconfig
        if katconfig is not None:
            try:
                ar = katconfig.get_array_config()
                mapping = ar._sections['dbe1']
                for k,v in mapping.iteritems():
                    if k.startswith("input"):
                        dbe = k[5:]
                        rvals = v.split(",")
                        real = rvals[0][3:] + rvals[1][-1].capitalize()
                        self._dbe_to_real[dbe] = real
                        self._real_to_dbe[real] = dbe
                self.n_ants = len(self._dbe_to_real) / 2
            except Exception, err:
                print "Although a config was supplied, construction of real to dbe mapping failed. (" + str(err) + ")"

        self.bl_order = self._calc_bl_order()
        self._pol_dict = ['HH','VV','HV','VH']
        self._dbe_pol_dict = ['xx','yy','xy','yx']

    def _ij2bl(i, j): return ((i+1) << 8) | (j+1)
    def _bl2ij(bl): return ((bl >> 8) & 255) - 1, (bl & 255) - 1

    def _calc_bl_order(self):
        """Return the order of baseline data output by a CASPER correlator
        X engine."""
        order1, order2 = [], []
        for i in range(self.n_ants):
            for j in range(int(self.n_ants/2),-1,-1):
                k = (i-j) % self.n_ants
                if i >= k: order1.append((k, i))
                else: order2.append((i, k))
        order2 = [o for o in order2 if o not in order1]
        return [o for o in order1 + order2]

    def list_baselines(self):
        return self.bl_order

    def user_to_id(self, user_input):
        """Convert user input to a correlation product id.
        User input may be any of the following:
            a correlation product id directly
            a two element tuple (baseline_number, pol)
                pol can be (0,1,2,3) or ('HH','VV','HV','VH')
            a three element tuple (antenna 1, antenna 2, pol)
                pol as before, but we need to convert real antennas into dbe input antennas
        An array of any mix of the above is also accepted.
        Returns
        -------
        corr_product_id : integer | array
            The final product id. Or array of the same
        """
        ret = []
        if type(user_input) != type([]):
            return self._user_to_id(user_input)
        ret = []
        for inp in user_input:
            ret.append(self._user_to_id(inp))
        return ret

    def _convert_pol(self, pol):
        """Turn a user specified polarisation into
        a pol index (0,1,2,3)
        """
        if type(pol) == type(""):
            if pol.upper() in self._pol_dict: pol = self._pol_dict.index(pol)
        if pol < 0 or pol > 3:
            print "Unknown polarisation (" + str(pol) + ") specified."
            return None
        return pol

    def _antenna_to_input(self, antenna, pol):
        """Turn a user specified antenna into a dbe input number.
        """
         # check to see if physical antenna correspsonds to a dbe input
        if antenna < 1:
            print "Physical antennas are numbered from 1 upwards. You have specified " + str(antenna)
            return (None,None)
        if self._katconfig is not None:
            if self._real_to_dbe.has_key(str(antenna) + str(pol)):
                inp = self._real_to_dbe[str(antenna) + str(pol)]
                return (int(inp[0]),inp[1])
            else:
                print "The specified physical input (Antenna " + str(antenna) + ", Pol: " + str(pol) + ") does not appear to be connected to the dbe.\n Please check your configuration."
                return (None,None)
        else:
            print "No antenna mapping config provided. Use direct dbe mapping. "
            return (int(antenna) - 1, {'H':'x','V':'y'}[pol])

    def _user_to_id(self, inp):
        if type(inp) != type(()): return inp
        if len(inp) == 2:
            baseline = inp[0]
            pol = self._convert_pol(inp[1])
        elif len(inp) == 3:
            pol = self._convert_pol(inp[2])
            (inp1,pol1) = self._antenna_to_input(inp[0], self._pol_dict[pol][0])
            (inp2,pol2) = self._antenna_to_input(inp[1], self._pol_dict[pol][1])
            if inp1 is None or inp2 is None: return None
            pol = self._dbe_pol_dict.index(str(pol1) + str(pol2))
             # convert dbe input spec (say xy) to a pol number
            baseline = (inp1,inp2)
            try:
                baseline = self.bl_order.index(baseline)
            except ValueError:
                print "Baseline specified by " + str(baseline) + " is invalid."
                return None
        else:
            print "Product specifier " + str(inp) + " not parseable."
            return None
        if pol is None: return None
        return (baseline * 4) + pol

    def id_to_real_str(self, id, short=False):
        id = self.user_to_id(id)
         # just in case :)
        m = self.id_to_real(id)
        mt = (m[3] == "A" and "Antenna" or "Input")
        a = (short and m[3] or mt)
        return a + str(m[0]) + " * " + a + str(m[1]) + " " + str(m[2])

    def id_to_real(self, id):
        """Takes a correlator product id and returns the physical inputs it corresponds to.

        Parameters
        ----------
        id : integer
            The correlator product id

        Returns
        -------
        (a1, a2, pol) : tuple
            Returns the physical antenna pair and the actual polarisation product (HH,VV,HV,VH)
        """
        input = self.id_to_input(id)
        pol = self._dbe_pol_dict[input[2]]
        map_type = 'I'
        try:
            inp1 = self._dbe_to_real[str(input[0]) + str(pol[0])]
            inp2 = self._dbe_to_real[str(input[1]) + str(pol[1])]
            input = (inp1[:-1], inp2[:-1])
            pol = str(inp1[-1]) + str(inp2[-1])
            map_type = 'A'
        except KeyError, err:
            if self._katconfig is not None:
                print "Error mapping dbe input to physical antenna. Please ensure your configuration is correct."
        return tuple([input[0],input[1],pol,map_type])
         # straight through for antennas for now

    def id_to_input(self, id):
        """Takes a correlator product id and returns the corresponding physical correlator inputs...

        Parameters
        ----------
        id : integer
            The correlator product id

        Returns
        -------
        (inp1, inp2, pol) : tuple
            Returns the two correlated inputs and the pol number (0-3)
        """
        bl = self.bl_order[id / 4]
         # integer calc on purpose
        return tuple([bl[0],bl[1],id % 4])

    def real_to_id():
        pass

    def input_to_id():
        pass

class SignalDisplayFrame(object):
    """A class to store a single frame of signal display data.
    """
    def __init__(self, timestamp_ms, corr_prod_id, length, data):
        self.timestamp_ms = timestamp_ms
        self.corr_prod_id = corr_prod_id
        self.length = length
        self.data = np.zeros(length, dtype=np.float32)
         # zero data initially
        self._current_length = 0
         # how much data we currently have
        self._valid = False
         # frame is invalid until _current_length = length
        self._allowed_views = ['complex','re','im','mag','phase']

    def add_data(self, offset, data):
        self.data[offset:offset + len(data)] = data
        self._current_length += len(data)
        if self._current_length == self.length: self._valid = True

    def get_data(self, dtype='complex', start_channel=0, stop_channel=None):
        """Return data of a specific type.
        Parameters
        ----------
        dtype : string
            Type can be 'complex','re','im','mag','phase'
        start_channel : integer
        stop_channel : integer
        """
        if not dtype in self._allowed_views:
            print "Specified type",dtype,"is unknown. Must be in",self._allowed_views
        return getattr(self,'get_' + dtype)(start_channel, stop_channel)

    def get_complex(self, start_channel=0, stop_channel=None):
        return self.data.view(dtype=np.complex64)[start_channel:stop_channel]

    def get_re(self, start_channel=0, stop_channel=None):
        return self.data[start_channel:stop_channel:2]

    def get_im(self, start_channel=0, stop_channel=None):
        return self.data[start_channel+1:stop_channel+1:2]

    def get_mag(self, start_channel=0, stop_channel=None):
        """Return a np array of mag data for each channel"""
        return np.abs(self.data.view(dtype=np.complex64))[start_channel:stop_channel]

    def get_phase(self, start_channel=0, stop_channel=None):
        """Return a np array of phase angle (deg) for each channel"""
        return np.angle(self.data.view(dtype=np.complex64))[start_channel:stop_channel]

    def get_avg_power(self, start_channel=0, stop_channel=None):
        """Return the power averaged over frequency channels specified.
           Default is all channels in the frame."""
        return np.average(np.abs(self.data.view(dtype=np.complex64)[start_channel:stop_channel]))

class SignalDisplayStore(object):
    """A class to store signal display data and provide a variety of views onto the data
    for it's clients.
    Parameters
    ----------
    capacity : integer
        The overall number of correlator dumps to store.
        The size of a single, complete dump is: channels * correlation_products * 8 bytes
        default: 3600
    """
    def __init__(self, capacity=3600):
        self.capacity = capacity
        self.time_frames = {}
         # a dictionary of SignalDisplayFrames. Organised by timestamp and then correlation product id
        self.corr_prod_frames = {}
         # a dictionary of SignalDisplayFrames. Organised by correlation product id and then timestamp (ref same data as time_frames)
        self._timestamp_count = 0
        self._last_frame = None
        self._last_data = None
        self._last_offset = None

    """Add some data to the store.
    In general this a fragment of a signal display frame and hence
    the data must be inserted in the correct location within an existing frame.

    Parameters
    ----------
    timestamp_ms :
        Timestamp of the start of this frame of data in epoch milliseconds.
    corr_prod_id : integer
        Each correlation product is the correlation of Ax with *By where A/B is the antenna number and x/y is the polarisation.
    offset : integer
        The offset of this chunk of data within the complete frame. This is specified in array index form
    length : integer
        The overall array length.
    data : array
        A numpy array of complex frequency channels for the specified correlation product.
    """
    def add_data(self, timestamp_ms, corr_prod_id, offset, length, data):
        frame = SignalDisplayFrame(timestamp_ms, corr_prod_id, length, data)
         # check top level containers
        if not self.time_frames.has_key(timestamp_ms):
            self.time_frames[timestamp_ms] = {}
            self._timestamp_count += 1
        if not self.corr_prod_frames.has_key(corr_prod_id):
            self.corr_prod_frames[corr_prod_id] = {}
        if not self.time_frames[timestamp_ms].has_key(corr_prod_id):
            f = SignalDisplayFrame(timestamp_ms, corr_prod_id, length, data)
            self.time_frames[timestamp_ms][corr_prod_id] = f
            self.corr_prod_frames[corr_prod_id][timestamp_ms] = f
             # add the blank frame

        if self._timestamp_count > self.capacity:
            ts = min(self.time_frames.keys())
            x = self.time_frames[timestamp_ms].pop(ts)
             # pop out the oldest time element
            for id in x.iterkeys():
                self.corr_prod_frames[id].pop(ts)
             # remove the stale timestamps from individual ids

        self._last_frame = self.time_frames[timestamp_ms][corr_prod_id]
        self._last_data = data
        self._last_offset = offset
        self.time_frames[timestamp_ms][corr_prod_id].add_data(offset, data)
        self.corr_prod_frames[corr_prod_id][timestamp_ms].add_data(offset, data)

    def load(self, filename, scan=0, start=None, end=None):
        """Load signal display data from a previously captured HDF5 file.
        A base filename is specified. A search is made for <filename>.00x.h5
        Baselines are filled in based on the files found. (1 - A1A1, 2 - A1A2, 3 - A2A2)
        Generally the file is flatenned and all data is read in. If the scan parameter is set
        then only the specified scan will be read in. At the moment only CompoundScan0 is used.

        The start and end frame can be specified to limit to data that is retrieved.
        """
        import os
        import h5py
        for b in range(1,4):
            fullname = filename + str(b) + '.h5'
            try:
                os.stat(fullname)
                d = h5py.File(fullname)
                for s in d['Scans']['CompoundScan0']:
                    data = d['Scans']['CompoundScan0'][s]['data'].value[start:end]
                    ts = d['Scans']['CompoundScan0'][s]['timestamps'].value[start:end]
                    print "Adding",len(ts),"timestamps from",s,"for baseline",b
                    for i,t in enumerate(ts):
                        t = t / 1000
                        d = data[i]
                        (mx,px) = self._make_spectrum(d['XX'])
                        (my,py) = self._make_spectrum(d['YY'])
                        (mxy,pxy) = self._make_spectrum(d['XY'])
                        (myx,pyx) = self._make_spectrum(d['YX'])
                        data_id = (b - 1)
                        self.add_data(t,1,data_id,[mx],[my],[mxy],[myx])
                        self.add_data(t,2,data_id + 3,[px],[py],[pxy],[pyx])
            except OSError:
                print "Baseline",b,"could not be found. (filename=",fullname,")."

    def __getitem__(self, name):
        try:
            return self.time_frames[name]
        except KeyError:
            return None

    def stats(self):
        print "Correlation Product ID".center(7),"Frames".center(6),"Earliest Stored Data".center(50),"Latest Stored Data".center(50)
        print "".center(22,"="), "".center(6,"="), "".center(50,"="), "".center(50,"=")
        for id in self.corr_prod_frames.keys():
            times = self.corr_prod_frames[id].keys()
            te = str(min(times)) + " (" + time.ctime(min(times)/1000)  + ")"
            tl = str(max(times)) + " (" + time.ctime(max(times)/1000)  + ")"
            print str(id).center(22),str(len(times)).center(6),te.center(50),tl.center(50)

class NullReceiver(object):
    """Null class used when loading historical data into signal displays...
    """
    def __init__(self, storage, channels=512):
        self.storage = storage
        self.data_rate = 0
        self.channels = channels
        self.spectrum = {}
        self.spectrum['XX'] = [[0] * channels,[0] * channels,[0] * channels, [0] * channels, [0] * channels, [0] * channels]
        self.spectrum['YY'] = [[0] * channels,[0] * channels,[0] * channels, [0] * channels, [0] * channels, [0] * channels]
        self.spectrum['XY'] = [[0] * channels,[0] * channels,[0] * channels, [0] * channels, [0] * channels, [0] * channels]
        self.spectrum['YX'] = [[0] * channels,[0] * channels,[0] * channels, [0] * channels, [0] * channels, [0] * channels]
        self.tp = {}
        self.tp['XX'] = [0,0,0]
        self.tp['YY'] = [0,0,0]
        self.tp['XY'] = [0,0,0]
        self.tp['YX'] = [0,0,0]
        self.current_timestamp = 0
        self.last_ip = None

class SignalDisplayReceiver(threading.Thread):
    """A class to receive and decode signal display data, and store it in a SignalDisplayData object.

    Parameters
    ----------
    port : integer
        The port to listen on for signal display udp packets.
    storage : SignalDispayStore
        The object in which to store the received signal display data. If none specified then only the current frame
        of data will be available at any given time.
        default: None
    recv_buffer : integer
        The size in bytes to set the udp receive buffer to.
        default: 512000
    """
    def __init__(self, port, store=None, recv_buffer=512000):
        self.port = port
        self.storage = store
        self._running = True
        self.data_rate = 0
        self.process_time = 0
        threading.Thread.__init__(self)
        self.packet_count = 0
        self.recv_buffer = recv_buffer
        self.rfi_mask = set()
        self._one_shot = -1
        self.current_frames = {}
        self.last_timestamp = 0
        self.last_ip = None
        self._last_frame = None
        quitter.register_callback("Signal Display Receiver", self.stop)

    def stop(self):
        self._running = False

    def check_header(self, header):
        """Checks the supplied string for the presence of signal display header information.
           The header should start with ASCII 'SD' and will contain information on the timestamp,
           packet id and data type. More information on the signal display data format is in the
           online documentation.

        Parameters
        ----------
        header : string
            A string containing only the header.

        Returns
        -------
        header_values : tuple
            A tuple containing (data_type, data_id, timestamp, packets_per_id, packet_id)
        """
        magic = unpack('2c',header[:2])
        if magic == ('S','D'):
            (corr_prod_id, offset, length) = unpack('>3h', header[2:8])
            timestamp_ms = unpack('Q',header[8:16])[0]
            return (corr_prod_id, offset, length, timestamp_ms)
        else:
            print "Invalid magic (" + str(magic) + "). Not a signal display packet"
            return (0, 0, 0, 0)

    def stats(self):
        print "Data rate (over last 10 packets):",self.data_rate
        print "Packet process time (us - avg for last 10 packets):",self.process_time
        print "Last packet from IP:",self.last_ip
        print "Number of received packets:",self.packet_count
        print "Number of timestamps in storage:",(self.storage is None and "N/A" or len(self.storage.time_frames))

    def one_shot(self, data_id=0):
        self._one_shot = data_id

    def run(self):
        """Main thread loop. Creates socket connection, handles incoming data and marshalls it into
           the storage object.
        """
        udpIn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            udpIn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.recv_buffer)
        except Exception, err:
            logger.error("Failed to set requested receive buffer size of " + str(self.recv_buffer) + " bytes")
        udpIn.bind(('', self.port))
        udpIn.setblocking(True)
        self.packet_count = 0
        d_start = 0
        while self._running:
            if self.packet_count % 10 == 0:
                d_start = time.time()
            data, self.last_ip = udpIn.recvfrom(9200)
            self._last_frame = data
            if d_start > 0:
                self.data_rate = int(len(data)*10 / (time.time() - d_start) / 1024)
                self.process_time = (time.time() - d_start) * 100000
                d_start = 0
             # block for incoming data
            (corr_prod_id, offset, length, timestamp_ms) = self.check_header(data[:16])
            length = length / 4
            data_offset = offset / 4
             # length and offset are in bytes
            if (len(data[16:]) % 4 == 0):
                packet_data = unpack('<' + str(len(data[16:]) / 4) + 'f', data[16:])
            else:
                logger.error("Data payload is not composed of an integer number of 32bit floats")
                continue
             # decode packet data into np array
            self.storage.add_data(timestamp_ms, corr_prod_id, data_offset, length, packet_data)
            self.last_timestamp = timestamp_ms
            self.packet_count += 1

class AnimatablePlot(object):
    """A plot container that contains sufficient meta information for the plot to be animated by another thread.

    Essentially you add a reference to a matplotlib plot along with a function pointer that can provide updated plot
    data when called. Arguments for the update function can also be supplied in keyword form.

    Examples
    --------
    Say you want to make an animated image of some random data:

    >>> from matplotlib.pyplot import figure
    >>> from pylab import standard_normal
    >>> from ffuilib.data import AnimatablePlot
    >>> img = standard_normal(size = (100,100))
    >>> f = figure()
    >>> f.gca().imshow(img)
    >>> f.show()
    >>> ap = AnimatablePlot(f, standard_normal, size=(100,100))
    >>> ap.animate()

    Parameters
    ----------
    figure : matplotlib.figure.Figure
        The displayed figure to animate
    update_function : function pointer
        A pointer to the function to be called when the plot is updated
    update_args : kwargs
        The keyword arguments to be supplied to the update_function
    """
    def __init__(self, figure, update_function, **update_args):
        self.figure = figure
        self.ax = figure.gca()
        self._yautoscale = True
        self.ymin = 0
        self.ymax = 0
	self.fixed_x = False
        self.update_functions = {}
        self.update_arguments = {}
        self.update_functions[0] = update_function
        self.update_arguments[0] = update_args
        self._update_counter = 1
        self._square_scale = False
        self._markers = {}
        self._marker_count = 0
        self._cbar = None
        self._styles = ['b','g','r','c','m','y','k']

    def set_colorbar(self, cbar):
        self._cbar = cbar

    def add_marker(self, name):
        self._markers[time.time()] = name

    def set_square_scale(self, sq):
        self._square_scale = sq

    def set_y_autoscale(self, yautoscale):
        self._yautoscale = yautoscale
        self.update()

    def set_y_limits(self, ymin,ymax):
        self.ymin = ymin
        self.ymax = ymax
        if self._yautoscale:
            self._yautoscale = False
            print "Turning off y autoscaling. To re-enable use set_y_autoscale(True)"
        self.update()

    def set_y_scale(self, scale_type):
        if scale_type in ('linear','log'):
            self.ax.set_yscale(scale_type)
        else:
            print "Please choose either linear or log for the y scale."
        self.redraw()

    def add_sensor(self, sensor, **update_args):
        line = matplotlib.lines.Line2D([],[],linewidth=1,linestyle='-',marker='o',color=self._styles[self._update_counter % 7],label=sensor.name)
        self.ax.add_line(line)
        self.ax.legend()
        self.add_update_function(sensor.get_cached_history,plot_data=True, **update_args)
        self.update()

    def add_stored_sensor(self, sensor, **update_args):
        line = matplotlib.lines.Line2D([],[],linewidth=1,linestyle='-',marker='o',color=self._styles[self._update_counter % 7],label=sensor.name)
        self.ax.add_line(line)
        self.ax.legend()
        self.add_update_function(sensor.get_stored_history, select=False, plot_data=True, **update_args)
        self.update()

    def add_update_function(self, update_function, **update_args):
        self.update_functions[self._update_counter] = update_function
        self.update_arguments[self._update_counter] = update_args
        self._update_counter += 1

    def show_legend(self):
        self.ax.legend()

    def redraw(self):
        """Redraw the current figure.
        Generally called after the chart data has been modified this method should
        ensure that the figure is on screen and that it get's correctly redrawn.
        Differences between OSX and Linux matplotlibiness mean that we need a bit of
        overkill to get a correct redraw.
        """
        self.figure.show()
        self.figure.canvas.draw()
        pl.draw()

    def animate(self, interval=1, **override_args):
        """Animate the plot.

        Parameters
        ----------
        interval : float
            The number of second to wait between each update to the plot.
            default: 1
        override_args: kwargs
            A number of keyword arguments that can be used to override the default
            keyword argument provided to the update function that gets called on each animation cycle.
        """
        print "Animating plot. Press Ctrl-C to halt..."
        while True:
            try:
                self.update(**override_args)
                time.sleep(interval)
            except KeyboardInterrupt:
                print "Animation halted."
                break

    def update(self, **override_args):
        """Single shot update of the plot.

        See the docstring for animate for more on the override_args.
        """
        base = 0
        offset = 0
        ymin = xmin = np.inf
        ymax = xmax = None
        for slot in self.update_functions.keys():
            offset = 0
            for override in override_args.keys():
                self.update_arguments[slot][override] = override_args[override]
                 # any user specified overrides will be passed down to update function
            new_data = self.update_functions[slot](**self.update_arguments[slot])
            if len(new_data) == 0:
                print "Failed to retrieve new plot data. Not updating."
                continue
            try:
                if len(self.ax.lines) > 0:
                    if (type(new_data[0]) == list or type(new_data[0]) == np.ndarray) and len(new_data) > 1:
                        if len(new_data) > 2:
                            if slot == 0:
                                base = new_data[2]
                                 # also draw any outstanding markers we have
                                for marker in self._markers:
                                    self._marker_count += 1
                                    name = self._markers[marker]
                                    self.ax.axvline(marker - base, color=self._styles[self._marker_count % 7], alpha=0.5, lw=2, label=name)
                                    self.ax.annotate(self._markers[marker], (marker - base, self.ax.get_ylim()[0]),label=name, rotation=90)
                                self._markers = {}
                            else: offset = base - new_data[2]
                        xmin = min(xmin,min(new_data[0] - offset))
                        xmax = max(xmax,max(new_data[0] - offset))
                        ymin = min(ymin,min(new_data[1]))
                        ymax = max(ymax,max(new_data[1]))
                        self.ax.lines[slot].set_xdata(new_data[0] - offset)
                        self.ax.lines[slot].set_ydata(new_data[1])
                        if slot == max(self.update_functions.keys()):
                            if not self.fixed_x: self.ax.set_xlim(xmin,xmax)
                            if self._yautoscale:
                                if self._square_scale:
                                    self.ax.set_xlim(min(ymin,xmin) * 0.95, max(ymax,xmax) * 1.05)
                                    self.ax.set_ylim(min(ymin,xmin) * 0.95, max(ymax,xmax) * 1.05)
                                else:
                                    self.ax.set_ylim(ymin * 0.95,ymax * 1.05)
                            else:
                                self.ax.set_ylim(self.ymin,self.ymax)
                        if len(new_data) > 2 and slot == 0:
                            self.ax.set_xlabel("Time since " + time.ctime(new_data[2]))
                    else:
                        self.ax.lines[slot].set_ydata(new_data)
                elif len(self.ax.images) > 0:
                    if self._cbar is not None:
                        self._cbar.set_array(new_data)
                        self._cbar.set_clim(vmin=np.min(new_data),vmax=np.max(new_data))
                        self._cbar.autoscale()
                        self._cbar.draw_all()
                    self.ax.set_ylim(len(new_data) - 1,0)
                    self.ax.images[slot].set_data(new_data)
                elif len(self.ax.patches) > 0:
                    vertices = self.figure.axes[0].patches[0]._path.vertices
                     # set the top of each bar to the new data value
                    vertices[1::5,1] = new_data[0]
                    vertices[2::5,1] = new_data[0]
                    self.ax.set_ylim(0,max(new_data[0]))
                else:
                    print "Figure does not appear to have lines or images in it. Unsure how to update."
                self.redraw()
            except KeyboardInterrupt:
                raise KeyboardInterrupt

class PlotAnimator(object):
    """An animated plot container that allows the user to add a number of AnimatablePlot instances to the container
    and animate these children.

    General use is to create a PlotAnimator object and then using add_plot add a number of AnimatablePlot instances (which are returned
    by most plot_x functions). This group of plots can then be animated together.

    Examples
    --------
    To create an animated signal display chain showing the signal from adc through correlation:
    (assuming you have created a top level ff object using configure or tbuild)

    >>> pa = PlotAnimator()
    >>> ap1 = ff.dh.plot_snapshot('adc')
    >>> ap2 = ff.dh.plot_snapshot('quant')
    >>> ap3 = ff.dh.sd.plot_spectrum()
    >>> ap4 = ff.dh.sd.plot_waterfall()
    >>> pa.add_plot('adc',ap1); pa.add_plot('quant', ap2); pa.add_plot('spectrum', ap3); pa.add_plot('waterfall', ap4)
    >>> pa.animate_all()

    Parameters
    ----------
    interval : integer
        Specify the time interval between successive plot updates (in float seconds).
        default: 1
    """
    def __init__(self, interval=1):
        self.interval = interval
        self.plots = {}
        self.states = ["|","/","-","\\"]

    def add_plot(self, plot_name, plot):
        """Add a plot to the list of plots to be animated.

        Parameters
        ----------
        plot_name : string
            An arbitrary name used to uniquely identify this plot. Generally something descriptive like 'waterfall'
        plot : AnimatablePlot
            An AnimatablePlot instance. Typically as returned by on the of plot_x functions in this library.
        """
        self.plots[plot_name] = plot

    def update_all(self):
        """Do a single refresh of the all the plots in this object."""
        for plot_name in self.plots.keys():
            print plot_name," ",
            self.plots[plot_name].update()
            time.sleep(self.interval)

    def animate_all(self):
        """Animate all registered plots in a round robin fashion."""
        update_count = 0
        try:
            while True:
                status = "\r%s" % str(self.states[update_count % 4])
                sys.stdout.write(status)
                self.update_all()
                sys.stdout.flush()
                update_count += 1
        except KeyboardInterrupt:
            print "\n\nAnimation halted. (" + str(update_count) + " cycles)"

class DataHandler(object):
    """A class that provides high level wrapping of the SignalDisplayReceiver and SignalDisplayData
    object to allow easier user interaction and manipulation.
    Provides support routines for extracting and interacting with the stored data.

    On init we try to determine the local host's IP address and instruct k7w to start sending signal display
    data to this address

    Parameters
    ----------
    dbe : FFDevice
        A reference to an FFDevice object connected to a dbe proxy that has a k7writer reference. This is used to add this current host as a signal display data listener.
    port : integer
        The port on which to receive signal display data.
        default: 7006
    ip : string
        Override the IP detection code by providing a specific IP address to which to send the signal data.
        default: None
    n_ants : integer
        The number of antenna's to use in the internal mapping object. If a katconfig is provided then this value will be overriden by the data from the config file.
    katconfig : config
        Used to construct physical antenna to dbe input mappings.
        default: None
    """
    def __init__(self, dbe=None, port=7006, ip=None, store=None, n_ants=2, katconfig=None):
        if dbe is not None:
            self.dbe = dbe
            if ip is None:
                self._local_ip = socket.gethostbyname(socket.gethostname())
            else:
                self._local_ip = ip
            print "Adding IP",self._local_ip,"to K7W listeners..."
            self.dbe.req.k7w_add_sdisp_ip(self._local_ip)
        if store is None:
            self.storage = SignalDisplayStore()
        else:
            self.storage = store
        self.cpref = CorrProdRef(n_ants=n_ants, katconfig=katconfig)
        if dbe is not None:
            self.receiver = SignalDisplayReceiver(port, self.storage)
            self.receiver.setDaemon(True)
            self.receiver.start()
        else:
            self.receiver = NullReceiver(self.storage)
             # a null receiver used when reading historical data
        self.default_product = 0
        self.default_products = [0]
        self._debug = False

    def set_default_product(self, product):
        """Sets a default product to use for command within the data handler.
        Can be specified either as a scalar or an array which will set the default
        for the plots appropriate to scalar or array product input.
        """
        if type(product) == type([]): self.default_products = product
        else: self.default_product = product

    @property
    def stats(self):
        return self.storage.stats()

    def stop(self):
        """Stop the signal display receiver and deregister our IP from the subscribers to the k7w signal data stream.
        """
        self.receiver.stop()
        print "Removing local IP from K7W listeners..."
        self.dbe.req.k7w_remove_sdisp_ip(self._local_ip)

    def plot_fringe_dashboard(self, product=None, dumps=360, dtype='phase', channels=512):
        """Show a fringe dashboard that includes a phase spectrogram, mag/phase vs time/frequency plots, and re vs im.
        Clicking on the spectrogram defines the time slice / channel number for the surrounding plots.

        Parameters
        ----------
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        dumps : integer
            The number of time dumps to show in the spectrogram.
            defaults: 360
        dtype : string
            The type of spectrogram to display ['mag'|'phase']
            default: 'phase'
        channels : integer
            The number of channels to display int the spectrogram.
            default: 512
        """
        if product is None: product = self.default_product
        # definitions for the axes
        left = bottom = 0.06
        height_s = width_s = 0.1
        height_l = width_l = 0.6
        width_l2 = 0.56
        spacing = 0.05

        rect_reim = [left, bottom + height_l + spacing, width_s * 2 + spacing, height_s * 2 + spacing]
        rect_mag_t = [left, bottom, width_s, height_l]
        rect_phase_t = [left + width_s + spacing, bottom, width_s, height_l]
        rect_wfall = [left + (width_s + spacing) * 2, bottom, width_l, height_l]
        rect_phase_f = [left + (width_s + spacing) * 2, bottom + height_l + spacing, width_l2, height_s]
        rect_mag_f = [left + (width_s + spacing) * 2, bottom + height_l + height_s + (spacing * 2), width_l2, height_s]

        # start with a rectangular Figure
        pl.figure(1, figsize=(14,10))

        # initially we only plot the spectrogram
        #sk = self.storage.frames['PHA1A2'].keys()
        #sk.sort()
        #sk = sk[-frames:]
        #sk.reverse()
        wfall_data = self.select_data(dtype=dtype, product=product, end_time=-dumps, stop_channel=channels, include_ts=True)
        if len(wfall_data[1]) < dumps:
            print "User asked for",dumps,"dumps. Only",len(wfall_data[1]),"are available. Truncating further calls to this length."
            dumps = len(wfall_data[1])
        tstamps = wfall_data[0]
        #wfall_data.reverse()

        ax_wfall = pl.axes(rect_wfall)
        cax = ax_wfall.imshow(wfall_data[1], aspect='auto', interpolation='bicubic', animated=True)
        cbar = pl.colorbar(cax, pad=0.02, fraction=0.05)
        ax_wfall.set_title("Xcorr phase spectrogram")

        ax_mag_t = pl.axes(rect_mag_t, sharey = ax_wfall)
        ax_mag_t.set_ylabel("Xcorr mag vs time")
        pl.setp(ax_mag_t.get_yticklabels(), visible=False)
        ax_mag_t.text(0,-bottom - 0.01,"Click the waterfall plot to choose the channel and time slices for the ancillary plots. Right click to draw the new selection over the previous one.", transform = ax_mag_t.transAxes)

        ax_mag_f = pl.axes(rect_mag_f, sharex = ax_wfall)
        ax_mag_f.set_title("Xcorr mag spectrum")
        pl.setp(ax_mag_f.get_xticklabels(), visible=False)

        ax_phase_t = pl.axes(rect_phase_t, sharey = ax_wfall)
        ax_phase_t.set_ylabel("Xcorr phase vs time")
        pl.setp(ax_phase_t.get_yticklabels(), visible=False)

        ax_phase_f = pl.axes(rect_phase_f, sharex = ax_wfall)
        ax_phase_f.set_title("Xcorr phase spectrum")
        pl.setp(ax_phase_f.get_xticklabels(), visible=False)

        ax_reim = pl.axes(rect_reim)
        ax_reim.set_aspect("equal")
        ax_reim.set_title("Re vs Im")

        ax_wfall.set_xlim((0,channels))
        #ax_wfall.set_ylim((0,frames))

        f = pl.gcf()
         # clear the ancillary plots
        def clear_plots():
            ax_mag_t.clear()
            pl.setp(ax_mag_t.get_yticklabels(), visible=False)
            ax_mag_t.text(0,-bottom - 0.01,"Click the waterfall plot to choose the channel and time slices for the ancillary plots. Right click to draw the new selection over the previous one.", transform = ax_mag_t.transAxes)
            ax_phase_t.clear()
            pl.setp(ax_phase_t.get_yticklabels(), visible=False)
            ax_mag_f.clear()
            pl.setp(ax_mag_f.get_xticklabels(), visible=False)
            ax_phase_f.clear()
            pl.setp(ax_phase_f.get_xticklabels(), visible=False)
            ax_reim.clear()
            ax_reim.set_aspect("equal")

         # define chart updater
        def populate(t_ref, f_ref):
             # time plots
            fringe_data = self.get_fringes(product=product, channel=f_ref, dtype='re', start_time=min(tstamps), end_time=max(tstamps))
            phase_t_data = self.get_time_series(product=product, dtype='phase', start_channel=f_ref, stop_channel=f_ref+1, start_time=min(tstamps), end_time=max(tstamps))
            ax_mag_t.plot(fringe_data[1], range(0,len(wfall_data[1]))) #, fringe_data[0][::-1])
            ax_phase_t.plot(phase_t_data[1], range(0, len(wfall_data[1]))) #, phase_t_data[0][::-1])
            ax_wfall.set_ylim((dumps,0))
             # spectral plots
            power_f = self.storage.time_frames[int(tstamps[t_ref] * 1000)][product].get_mag()
            #phase_f = self.storage.frames['PHA1A2'][sk[-frames:][t_ref]]
            phase_f = self.storage.time_frames[int(tstamps[t_ref] * 1000)][product].get_phase()
            ax_mag_f.plot(power_f)
            ax_mag_f.set_yscale("log")
            ax_phase_f.plot(phase_f)
            ax_wfall.set_xlim((0,channels))
             # re vs im
            reim = self.get_fringes(product=product, channel=f_ref, dtype='complex', end_time=-dumps)
            ax_reim.plot(reim[0],reim[1], 'o')

         # define event handler for clicking...
        def onpress(event):
            if event.inaxes != ax_wfall: return
            if event.button == 1: clear_plots()
            x1,y1 = event.xdata, event.ydata
            t_ref = int(y1)
            t = time.ctime(tstamps[t_ref])
            f_ref = int(x1)
            populate(t_ref, f_ref)
            ax_mag_t.set_ylabel("Xcorr mag vs time for channel " + str(f_ref))
            ax_phase_t.set_ylabel("Xcorr phase vs time for channel " + str(f_ref))
            ax_mag_f.set_title("Xcorr mag spectrum for " + t)
            ax_phase_f.set_title("Xcorr phase spectrum for " + t)
            ax_reim.set_title("Re vs Im for channel " + str(f_ref))
            f.canvas.draw()
            pl.draw()
        f.canvas.mpl_connect('button_release_event', onpress)
        pl.show()

    def select_data(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=512, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False):
        """Used to select a particular window of data from the store for use in the signal displays...
        Once the window has been chosen then the particular plot will subsample and reformat the data window
        to suit it's requirements.

        Parameters
        ----------
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        dtype : string
            Type can be 'complex','re','im','mag','phase'
        start_time : integer
            Either a direct specification of the start_time or zero to indicate the earliest available time.
        end_time : integer
            If a positive number then the time window is (start_time - end_time). If negative then start_time is ignored and the most
            recent abs(end_time) entries from the store are selected.
        start_channel : integer
        stop_channel : integer
        reverse_order : boolean
            Reverse the time order of the returned data. Useful for waterfall plots...
        avg_axis : integer
            Choose an axis to average over. 0 - time, 1 - frequency
            default: None
        sum_axis : integer
            Choose an axis to sum over. 0 - time, 1 - frequency
            default: None
        include_ts : boolean
            If set the timestamp of each frame is included as the first column of the array
        """
        if product is None: product = self.default_product
        product = self.cpref.user_to_id(product)
        if self._debug:
            print "Select data called with product: %i, start_time: %i , end_time: %i, start_channel: %i, end_channel: %i" % (product, start_time, end_time, start_channel, stop_channel)
        fkeys = self.storage.corr_prod_frames[product].keys()
        fkeys.sort()
        ts = []
        if end_time >= 0:
            start_time = start_time * 1000
            end_time = end_time * 1000
            frames = [self.storage.corr_prod_frames[product][f].get_data(dtype=dtype, start_channel=start_channel, stop_channel=stop_channel) for f in fkeys if f >= start_time and f <= end_time]
            if include_ts:
                ts = [f for f in fkeys if f >= start_time and f <= end_time]
        else:
            frames = [self.storage.corr_prod_frames[product][f].get_data(dtype=dtype, start_channel=start_channel, stop_channel=stop_channel) for f in fkeys[end_time:]]
            if include_ts:
                ts = fkeys[end_time:]
        if avg_axis is not None:
            frames = np.average(frames, avg_axis)
        if sum_axis is not None:
            frames = np.sum(frames, sum_axis)
        if include_ts:
            frames = [np.array([t / 1000.0 for t in ts]),frames]
        return frames

    def plot_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=512):
        """Show a waterfall plot for the specified baseline and polarisation.

        A waterfall plot shows frequency vs time with intensity represented by colour. The frequency channels run along
        the X axis, with time on the Y. Basically each row is a flatenned spectrum at a particular time.

        Parameters
        ----------
        dtype : string
            Either 'mag' or 'phase'
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        start_time : integer
            Either a direct specification of the start_time or zero to indicate the earliest available time.
        end_time : integer
            If a positive number then the time window is (start_time - end_time). If negative then start_time is ignored and the most
            recent abs(end_time) entries from the store are selected.
        start_channel : integer
            default: 0
        stop_channel : integer
            default: 512
        Returns
        -------
        ap : AnimatablePlot
        """
        if product is None: product = self.default_product
        if self.storage is not None:
            tp = self.select_data(dtype=dtype, product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            mapping = self.cpref.id_to_real_str(product)
            pl.ion()
            fig = pl.figure()
            ax = fig.gca()
            ax.set_title("Spectrogram (" + str(dtype) + ") for " + mapping)
            ax.set_ylabel("Time in seconds before now") # since " + time.ctime(sk[-frames:][0]))
            ax.set_xlabel("Freq Channel")
            cax = ax.imshow(tp, aspect='auto', interpolation='bicubic', animated=True)
            cbar = fig.colorbar(cax)
            fig.show()
            pl.draw()
            ap = AnimatablePlot(fig, self.select_data, product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            ap.set_colorbar(cbar)
            return ap
        else:
            print "No stored data available..."

    def plot_lfr(self, product=None, dumps=120):
        """Show a Lag - Fringe Rate plot.
        Basically this takes the complex spectrogram for the cross correlated baseline (f vs t) and
        performs a 2D fft. The abs if this is shown as an image with axes that correspond to Lag
        and Fringe Rate.

        Parameters
        ----------
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        dumps : integer
            The number of frames of data to use for the FFT time axis.
            default: 120
        """
        if product is None: product = self.default_product
        f = pl.figure()
        ax = f.gca()
        ax.set_title("Lag - Fringe Rate for " + self.cpref.id_to_real_str(product))
        ax.set_ylabel("Fringe Rate")
        ax.set_xlabel("Lag")
        cax = ax.imshow(self.get_lfr(product=product, dumps=dumps), aspect='auto', interpolation='bicubic', animated=True)
        cbar = f.colorbar(cax)
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_lfr, product=product, dumps=dumps)
        ap.set_colorbar(cbar)
        return ap

    def plot_waterfalls(self, dtype='phase', products=None, start_time=0, end_time=-120, start_channel=0, stop_channel=512, interval=1):
        """
        Plot a number of waterfall plots with a single command. See the usage for plot_waterfall.
        The main difference is that an array of desired products is provided.

        Returns
        -------
        pa : PlotAnimator
            A collection of animatable plots representing the produced waterfalls.
        """
        if products is None: products = self.default_products
        pa = PlotAnimator(interval=interval)
        for product in products:
            pa.add_plot('waterfall' + str(product),self.plot_waterfall(product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        return pa

    def get_time_function(self, pol='XX'):
        """Return the data required for the time function plot.
        See the docstring for plot_time_function for more detail.
        """
        mag = self.receiver.spectrum[pol][1]
        phase = self.receiver.spectrum[pol][3]
        c = []
        for cpair in np.column_stack((mag,phase)):
            c.append(np.sqrt(cpair[0])*np.e**(1j*cpair[1]))
        ch = len(c)
        x = np.arange(-ch + (ch/2),ch - (ch/2))
        d = np.fft.fftshift(abs(np.fft.fft(c)))
        return [x,d]

    def get_time_function2(self, pol='XX'):
        """Return the data required for the time function plot.
        See the docstring for plot_time_function for more detail.
        """
        mag = np.array(self.receiver.spectrum[pol][1])
        phase = np.array(self.receiver.spectrum[pol][3])
        c1 = mag * np.exp(1j*phase)
        c = np.hstack([c1, [0], np.flipud(c1).conjugate()[:-1]])
        ch = len(c)
        x = np.arange(-ch + (ch/2),ch - (ch/2))
        d = np.fft.fftshift(np.fft.fft(c))
        return [x,abs(d.real)]

    def get_time_function3(self, product=None, end_time=-120, start_channel=128):
        """Return the data required for the time function plot.
        See the docstring for plot_time_function for more detail.
        """
        if product is None: product = self.default_product
        if start_channel < 0 or start_channel > 255:
            print "Please choose a starting channel between 0 and 255..."
            return
        c1 = self.select_data(dtype='complex', product=product, end_time=end_time, start_channel=start_channel, stop_channel=start_channel+256, avg_axis=1)
        c2 = c1 * np.exp(-1j * np.angle(c1[0]))
         # move the phase slope so that channel 0 as zero phase (i.e. DC)
        c = np.hstack([c1, [0] * 512, [0], np.flipud(c1).conjugate()[:-1]])
        ch = len(c)
        x = np.arange(-ch + (ch/2),ch - (ch/2))
        d = np.fft.fftshift(np.fft.fft(c))
        return [x,abs(d.real)]

    def get_lfr(self, product=None, dumps=120):
        if product is None: product = self.default_product
        c = self.select_data(dtype='complex', product=product, end_time=-dumps)
        return np.fft.fftshift(abs(np.fft.fft2(c)))

    def get_fringes(self, channel='256', product=None, dtype='complex', start_time=0, end_time=-120):
        """See docstring from plot_fringes for details"""
        if product is None: product = self.default_product
        if dtype == 'complex':
            data = self.select_data(product=product, dtype='complex', start_channel=channel, stop_channel=channel+1, start_time=start_time, end_time=end_time, avg_axis=1)
            return [data.real, data.imag]
        else:
            data = self.select_data(product=product, dtype=dtype, start_channel=channel, stop_channel=channel+1, start_time=start_time, end_time=end_time, avg_axis=1, include_ts=True)
            return [data[0],data[1],data[0][0]]

    def get_time_series(self, dtype='mag', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=512):
        if product is None: product = self.default_product
        tp = self.select_data(dtype=dtype, sum_axis=1, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel)
        xlabel = tp[0][0]
        ts = tp[0] - tp[0][0]
        return [ts,tp[1],xlabel]

    def get_periodogram(self, product=None, end_time=-120):
        """Return the data required for plotting a periodogram.
        See the docstring for get_total_power for more detail on the parameters.
        """
        if product is None: product = self.default_product
        tp = self.get_time_series(product=product, end_time=end_time)
        return abs(np.fft.fft(tp[1]))

    def plot_time_series(self, dtype='mag', products=None, end_time=-120, scale='log', start_channel=0, stop_channel=512):
        """Plot a time series for the specified correlation products.

        To plot a single frequency channel simply make start and stop differ by 1 :) Otherwise the band of interest is averaged together
        for the display.

        Parameters
        ----------
        dtype : string
            Choose to plot either 'mag' or 'phase'. Note that the time series is averaged over the specified channels. So plotting phase may not
            make much sense over a wide number of channels.
        products : array
            Select the desired products from the store.
            If an array of integers is specified they are treated as a correlation product id directly (ordered as it comes out of the correlator)
            If an array of tuples is provided this should be either (baseline, pol) or (antenna1, antenna2, pol) in form.
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        end_time : integer
            default: -120
        scale : string
            Scale can be 'log' or 'linear'.
            defaulk: 'log'
        """
        if products is None: products = self.default_products
        pl.figure()
        pl.title("Summed " + str(dtype) + " for channels " + str(start_channel) + " to " + str(stop_channel))
        f = pl.gcf()
        for i,product in enumerate(products):
            data = self.get_time_series(dtype=dtype,product=product, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            pl.plot(data[0],data[1], label=self.cpref.id_to_real_str(product, short=True))
            if i == 0: ap = AnimatablePlot(f, self.get_time_series, dtype=dtype, product=product, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            else: ap.add_update_function(self.get_time_series, dtype=dtype, product=product, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
        pl.legend(loc=0)
        pl.xlabel("Time since " + time.ctime(data[2]))
        if dtype == 'phase': pl.ylabel("Phase [radians]")
        else: pl.ylabel("Power [arbitrary units]")
        pl.yscale(scale)
        f.show()
        pl.draw()
        return ap

    def plot_re_vs_im(self, channel=0, products=None, end_time=-120):
        """Plot the real part of the visibility vs the imaginary part.

        Parameters
        ----------
        channel : integer
            The channel number to plot. 0 based
            Default: 0
        products : array
            Select the desired products from the store.
            If an array of integers is specified they are treated as a correlation product id directly (ordered as it comes out of the correlator)
            If an array of tuples is provided this should be either (baseline, pol) or (antenna1, antenna2, pol) in form.
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        end_time : integer
            default: -120
        """
        if products is None: products = self.default_products
        pl.figure()
        pl.title("Re vs Im for channel " + str(channel))
        pl.ylabel("Imaginary")
        pl.xlabel("Real")
        f = pl.gcf()
        for i, product in enumerate(products):
            data = self.get_fringes(channel=channel, product=product, dtype='complex', end_time=end_time)
            pl.plot(data[0],data[1],'o',label=self.cpref.id_to_real_str(product, short=True))
            if i == 0: ap = AnimatablePlot(f, self.get_fringes, channel=channel, product=product, dtype='complex', end_time=end_time)
            else: ap.add_update_function(self.get_fringes, channel=channel, product=product, dtype='complex', end_time=end_time)
        pl.legend(loc=0)
        ax = pl.gca()
        ax.set_aspect("equal")
        f.show()
        pl.draw()
        ap.set_square_scale(True)
        return ap

    def plot_fringes(self,channel=256, product=None, dtype='complex', dumps=120):
        """Plot the real or imaginary part of the specified channel and polarisation versus time.
        This should produce the fabled 'fringe' plot :)

        Parameters
        ----------
        channel : integer
            The channel number to plot. 0 based
            Default: 0
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        dtype : string
            Choose to plot either or 're', 'im' or 'complex' (re and im plotted on same graph)
            default: complex
        dumps : integer
            The number of frames of data to display on the time axes. Generally one frame per second.
            default: 120
        """
        if product is None: product = self.default_product
        pl.figure()
        f = pl.gcf()
        pl.title("Fringe for channel " + str(channel) + ", " + self.cpref.id_to_real_str(product))
        pl.ylabel("Visibility [" + str(dtype) + "]")
        if dtype == 'complex':
            data = self.get_fringes(dtype='re', product=product, channel=channel, end_time=-dumps)
            pl.plot(data[0],data[1],label="Re")
            data = self.get_fringes(dtype='im', product=product, channel=channel, end_time=-dumps)
            pl.plot(data[0],data[1],label="Im")
            pl.legend(loc=0)
            ap = AnimatablePlot(f, self.get_fringes, dtype='re', product=product, channel=channel, end_time=-dumps)
            ap.add_update_function(self.get_fringes, dtype='im', product=product, channel=channel, end_time=-dumps)
        else:
            ap = AnimatablePlot(f, self.get_fringes, dtype=dtype, product=product, channel=channel, end_time=-dumps)
            data = self.get_fringes(dtype=dtype, product=product, channel=channel, end_time=-dumps)
            pl.plot(data[0],data[1])
        pl.xlabel("Time since " + time.ctime(data[2]))
        f.show()
        pl.draw()
        return ap

    def plot_periodogram(self, product=None, end_time=-120, scale='log'):
        """Plot the periodogram for the specified baseline, polarisation and duration.
        The periodiogram is the absolute value of the FFT of the total power time series.
        See the docstring for get_time_series for more detail on the parameters.
        """
        if product is None: product = self.default_product
        pl.figure()
        pl.title("Periodogram for " + self.cpref.id_to_real_str(product))
        pl.xlabel("Bins")
        pl.ylabel("Power")
        pl.yscale(scale)
        pl.plot(self.get_periodogram(product=product, end_time=end_time))
        f = pl.gcf()
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_periodogram, product=product, end_time=end_time)
        return ap

    def plot_time_function(self, product=None, dumps=120, start_channel=128, scale='linear'):
        """Plot the time function of the specified polarisation.

        The time function plot is produced by first merging the total power and phase spectra to produce
        a complex spectrum. This is then FFT'ed and the absolute value taken.

        Parameters
        ----------
        product : integer, tuple
            Select the desired product from the store.
            If a single integer is specified it is treated as a correlation product id directly (ordered as it comes out of the correlator)
            If a tuple is provided this should be either (baseline, pol) or (antenna1, antenna2, pol).
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        dumps : integer
            The number of dumps to include in the calculation
            default: 120
        start_channel : integer
            The starting channel for the data to use. A band of start_channel + 256 is used.
            default: 128
        scale : string
            Either 'log' or 'linear'
            default: 'log'

        Returns
        -------
        ap : AnimatablePlot
        """
        if product is None: product = self.default_product
        pl.figure()
        pl.title("Cross-correlation Time Function for " + self.cpref.id_to_real_str(product))
        pl.xlabel("Lag")
        pl.ylabel("Power")
         # get complex cross correlation spectrum
        x = self.get_time_function3(product=product, end_time=-dumps, start_channel=start_channel)
        pl.plot(x[0],x[1])
        pl.yscale(scale)
        f = pl.gcf()
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_time_function3, product=product, end_time=-dumps, start_channel=start_channel)
        return ap

    def plot_spectrum(self, type='mag', products=None, start_channel=0, stop_channel=512, scale='log', average=1):
        """Plot spectra for the specified products.
        The most recently received signal display data is used for the display.

        Parameters
        ----------
        type : string
            Either 'mag' or 'phase'.
            default: 'mag'
        products : array
            Select the desired products from the store.
            If an array of integers is specified they are treated as a correlation product id directly (ordered as it comes out of the correlator)
            If an array of tuples is provided this should be either (baseline, pol) or (antenna1, antenna2, pol) in form.
            Pol can be either an integer from 0 to 3 or one of {'HH','VV','HV','VH'}
            e.g. products = [9, (2,'VV'), (1,1,1)] are actually all product id 9
        start_channel : integer
            default: 0
        stop_channel : integer
            default: 512
        average : integer
            The number of dumps to average over (from most recent dump backwards)
            default: None
        Returns
        -------
        ap : AnimatablePlot
        """
        if products is None: products = self.default_products
        pl.figure()
        pl.xlabel("Channel Number")
        f = pl.gcf()
        ax = f.gca()
        avg = ""
        if average > 1: avg = " (" + str(average) + " dump average.)"
        if type == 'phase':
            pl.ylabel("Phase (degrees)")
            pl.title("Phase Spectrum" + avg)
            ax.set_ylim(ymin=-180,ymax=180)
        else:
            pl.title("Power Spectrum" + avg)
            pl.ylabel("Power (arb units)")
            pl.yscale(scale)
        for i,product in enumerate(products):
            pl.plot(self.select_data(product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0), label=self.cpref.id_to_real_str(product, short=True))
            if i == 0:
                ap = AnimatablePlot(f, self.select_data, product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0)
            else:
                ap.add_update_function(self.select_data, product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0)
        pl.legend(loc=0)
        f.show()
        pl.draw()
        return ap

class FFData(object):
    """A class to encapsulate various fringe finder data handling functions.

    Essentially this class provides a mechanism for retrieving and plotting raw data directly from the dbe, as well
    as interacting with and plotting of the signal display data stream.

    Parameters
    ----------
    dbe : FFDevice
        A reference to an FFDevice object connected to the fringe finder dbe proxy. This is used for making data calls to the dbe.
    """
    def __init__(self, dbe=None, katconfig=None):
        self.dbe = dbe
        self._katconfig = katconfig
        self.sd = None

    def register_dbe(self, dbe):
        self.dbe = dbe

    def load_data(self, filename):
        """Load the data from the specified file(s) and use this to populate a signal display storage object.
        The signal display plots can the be accessed as they were at the time of data capture. The new data handler
        is available as .sd_hist

        Parameters
        ==========
        filename : string
            The full qualified root filename (without the baseline number or .h5 extension). (e.g. /var/kat/data/1260384145.00)
            Checks for files of the type <filename>1.h5, <filename>2.h5, and <filename>3.h5
        """
        st = SignalDisplayStore()
        st.load(filename)
        self.sd_hist = DataHandler(dbe=None, store=st)
        print "Historical signal display data available as .sd_hist"

    def start_sdisp(self, ip=None):
        """Connect the data handler object to the signal display data stream and create a new DataHandler service
        for the incoming data.

        This command instructs k7writer to send signal display data to the current host (in addition to all other listeners). A new DataHandler
        is created to receive and interpret the incoming signal display frames.
        """
        logger.info("Starting signal display capture")
        if self.dbe is not None:
            self.sd = DataHandler(self.dbe, ip=ip, katconfig=self._katconfig)
        else:
            print "No dbe device known. Unable to start capture"

    def stop_sdisp(self):
        """Stop the signal display data receiving thread.
        """
        if self.sd is not None:
            self.sd.stop()

    def get_snapshot(self, type='adc', input='0x'):
        """Get snapshot data from the dbe and interpret according to type.

        Parameters
        ----------
        type : string
            Either 'adc' (raw 8-bit signed integers from the ADC) or 'quant' (real part 8 consecutive 512 channel spectra taken post quantisation) or 'quanti' (imaginary part) are available.
            default: 'adc'
        input : string
            Follows the dbe input labelling pattern (<board><input> where board is 0 or 1 and input is x or y. e.g. 0x for board 0 input x)
            default: '0x'

        Returns
        -------
        raw : array
            An array of values. In the 'adc' case 8-bit signed integers. In 'quant' an array of abs(complex64)
        """

        raw = []
        rettype = type
        if type == 'quanti': rettype = 'quant'
        if self.dbe is not None:
            try:
                raw = unpack('>8192b',self.dbe.req.dbe_poco_snap_shot(rettype,input,tuple=True)[0][2][1])
            except AttributeError:
                logger.error("Current dbe device does not support poco-snap-shot command.")
            except IndexError:
                logger.error("poco-snap-shot command failed.")
        else:
            logger.error("No dbe device known. Unable to capture snapshot.")
        if type == 'quant' or type == 'quanti':
            rawn = np.array(raw,dtype=np.float32)
            raw = rawn.view(dtype=np.complex64)
            if type == 'quant': return [x.real for x in raw]
            else: [x.imag for x in raw]
        return raw

    def get_histogram_data(self, type='adc', input='0x'):
        """Get ADC snapshot data and produce a histogram of the data.
        """
        data = self.get_snapshot(type=type, input=input)
        n, bins = np.histogram(data, bins=256, range=(-127,128), new=True)
        if len(n) == len(bins): bins.append(bins[-1])
         # fix for older numpy versions that did not return a rightmost bin edge
        return n,bins

    def plot_hist(self, type='adc', input='0x'):
        """Plot a histogram of the ADC sampling bins for the specified input.
        This plots a histogram of an 8192 sample snapshot of raw signed 8 bit ADC data.

        Parameters
        ----------
        type : string
            Either 'adc' (raw 8-bit signed integers from the ADC) or 'quant' (real part 8 consecutive 512 channel spectra taken post quantisation) or 'quanti' (imaginary part) are available.
            default: 'adc'
        input : string
            Follows the dbe input labelling pattern (<board><input> where board is 0 or 1 and input is x or y. e.g. 0x for board 0 input x)
            default: '0x'

        Returns
        -------
        ap : AnimatablePlot
        """
        import matplotlib.patches as patches
        import matplotlib.path as path
         # in order to animate this plot we are going to use a path instead of
         # using pl.hist which produces a whole wack of individual patches
        pl.figure()
        pl.title("Histogram (" + type + ") for input " + input)
        pl.xlabel("Bins")
        pl.ylabel("Count")
        f = pl.gcf()
        ax = f.gca()
        n, bins = self.get_histogram_data(type=type, input=input)
        left = np.array(bins[:-1])
        right = np.array(bins[1:])
        bottom = np.zeros(len(left))
        top = bottom + n
         # define the arrays that contain the four vertices for each bar to draw
        nrects = len(left)
        nverts = nrects*(1+3+1)
        verts = np.zeros((nverts, 2))
        codes = np.ones(nverts, int) * path.Path.LINETO
        codes[0::5] = path.Path.MOVETO
        codes[4::5] = path.Path.CLOSEPOLY
         # create the codes block. Basically we want to first move the cursor to the start point of the block. Then connect the four vertices
         # using LINETO and finally close the just drawn polygon. So our code array looks like [n x [MOVETO, LINETO, LINETO, LINETO, CLOSEPOLY]]
        verts[0::5,0] = left
        verts[0::5,1] = bottom
        verts[1::5,0] = left
        verts[1::5,1] = top
        verts[2::5,0] = right
        verts[2::5,1] = top
        verts[3::5,0] = right
        verts[3::5,1] = bottom
         # flesh out the vertices array with the coordinate pairs of each of the four block vertexes

        barpath = path.Path(verts, codes)
        patch = patches.PathPatch(barpath, facecolor='blue', edgecolor='red', alpha=0.5)
         # create a patch from the specified path
        ax.add_patch(patch)

        ax.set_xlim(left[0], right[-1])
        ax.set_ylim(bottom.min(), top.max())
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_histogram_data, type=type, input=input)
        return ap

    def plot_snapshot(self, type='adc', input='0x'):
        """Plot a snapshot of the specified type for the specified dbe input.
        A snapshot is basically a katcp dump of a particular block of dbe memory. At the moment a snapshot of the current ADC
        sampling and of the post quantisation data is available.

        Parameters
        ----------
        type : string
            Either 'adc' (raw 8-bit signed integers from the ADC) or 'quant' (real part 8 consecutive 512 channel spectra taken post quantisation)  or 'quanti' (imaginary part) are available.
            default: 'adc'
        input : string
            Follows the dbe input labelling pattern (<board><input> where board is 0 or 1 and input is x or y. e.g. 0x for board 0 input x)
            default: '0x'

        Returns
        -------
        ap : AnimatablePlot
        """
        pl.figure()
        pl.title("Snapshot (" + type + ") " + input)
        pl.xlabel((type == 'adc' and "Time" or 'Channel (groups of 512)'))
        pl.ylabel("Voltage")
        ax = pl.gca()
        raw = self.get_snapshot(type=type, input=input)
        pl.plot(raw)
        if type == 'quant' or type == 'quanti':
            for x in range(0,4096,512):
                pl.axvline(x,color='green', lw=1, alpha=0.5)
            pl.xticks(range(0,4096,256),[x % 512 for x in range(0,4096,256)])
        f = pl.gcf()
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_snapshot, type=type, input=input)
        return ap

    def plot_snapshots(self, type='adc', interval=1):
        """Plot snapshots of the specified type for each of the four input channels available
        in the fringe finder pocket correlator.

        Parameters
        ----------
        type : string
            Either 'adc' (raw 8-bit signed integers from the ADC) or 'quant' (8 consecutive 512 channel spectra taken post quantisation) are available.
            default: 'adc'
        interval : integer
            For the returned PlotAnimator object, specify the time interval between successive plot updates (in float seconds).
            default: 1

        Returns
        -------
        pa : PlotAnimator
            A collection of animatable plots representing the four produced snapshots.
        """
        pa = PlotAnimator(interval=interval)
        pa.add_plot('snap 0x',self.plot_snapshot(type=type, input='0x'))
        pa.add_plot('snap 0y',self.plot_snapshot(type=type, input='0y'))
        pa.add_plot('snap 1x',self.plot_snapshot(type=type, input='1x'))
        pa.add_plot('snap 1y',self.plot_snapshot(type=type, input='1y'))
        return pa
