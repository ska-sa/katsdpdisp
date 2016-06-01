# This library contains classes and routines that aid with data stream integration into katuilib

import threading
import socket
import logging
import numpy as np
import time
import warnings
import sys
import datetime
import calendar
from struct import unpack
import gc
import spead2
import spead2.recv
import six

from quitter import Quitter

datalock = threading.RLock()

quitter = Quitter("exit")
 # create a quitter to handle exit conditions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("katsdpdisp.data")
logger.setLevel(logging.INFO)

try:
    import matplotlib.pyplot as pl
    import matplotlib.lines
    import matplotlib.dates
    import matplotlib.ticker
    from matplotlib import cm
except:
    pl = None
    warnings.warn("Could not import matplotlib.pyplot -- plotting functions will not work.")

try:
    import netifaces
except:
    netifaces = None

class InvalidBaseline(Exception):
    """Specifying and invalid baseline or product id."""
    pass

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
        from .utility import KATNode
        self.node = KATNode(ip,ip)

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
    """Another small wrapper class to handle conversion between product id's.
    This time it will actually be small :)

    Typically a baseline ordering dictionary (as produced by the correlator) will be provided.
    This maps a baseline name (e.g. ant1H_ant1V) to a product id.

    If no dictionary is provided the class starts with a default mapping which has input 0x mapped to
    antenna 1 H, input 0y to antenna 1 V and so on...

    Parameters
    ----------
    bls_ordering : dict
        A dict mapping antenna description strings to a specific product id
    n_ants : int
        The antenna limit for default mapping production.
    no_bls : boolean
        No accurate information is known. Use inp notation (e.g. 0x) instead of real antenna notation
    """
    def __init__(self, bls_ordering=None, n_ants=8, no_bls=False):
        self.bls_ordering = bls_ordering
        self.no_bls = no_bls
        self.n_ants = n_ants
        if self.bls_ordering is None: self.bls_ordering = self.get_default_bl_map(n_ants, no_bls)
        self._id_to_real = {}
        self._id_to_real_long = {}
        self.antennas = {}
        self.labels = {}
        self.autos = []
        self.inputs = []
        self._pol_dict = ['hh','vv','hv','vh']
        self.precompute()
         # precompute a number of lookups to save processing later on. (Some of these are called a lot...)
         # populates id_to_real, id_to_real_long, updates n_ants,

    def precompute(self):
        self.autos = []
        self.inputs = []
        self.ant_pol_autos = []
        self._pol_ids = dict([(pol,[]) for pol in self._pol_dict])
        self._id_to_real = {}
        self._id_to_real_long = {}
        for i,bls in enumerate(self.bls_ordering):
            a,b = bls
            self.labels[a] = 1
            if not a[:-1] in self.antennas: self.antennas[a[:-1]] = {}
            self.antennas[a[:-1]][a[-1]] = 1
            if a == b:
                self.autos.append(i)
                self.inputs.append(a)
            self._id_to_real[i] = a + " * " + b
            self._id_to_real_long[i] = "%s %s * %s %s" % (a[:-1].replace("ant","Antenna "),a[-1],b[:-1].replace("ant","Antenna "),b[-1])
            pol=a[-1]+b[-1]
            if (pol in self._pol_ids):
                self._pol_ids[pol].append(i)

    def get_default_bl_map(self, n_ants, no_bls):
        """Return a default baseline mapping by replacing inputs with proper antenna names."""
        bls = []
        order1, order2 = [], []
        for i in range(n_ants):
            for j in range(int(n_ants/2),-1,-1):
                k = (i-j) % n_ants
                if i >= k: order1.append((k, i))
                else: order2.append((i, k))
        order2 = [o for o in order2 if o not in order1]
        bls_raw = tuple([o for o in order1 + order2])
        for b in bls_raw:
            if no_bls:
                for p in ['xx','xy','yx','yy']:
                    bls.append(["inp%i%s" % (b[0],p[0]), "inp%i%s" % (b[1],p[1])])
            else:
                for p in ['hh','hv','vh','vv']:
                    bls.append(["ant%i%s" % (b[0]+1,p[0]), "ant%i%s" % (b[1]+1,p[1])])
        return bls

    def get_auto_from_cross(self, id):
        """Returns the pair of ids that are correspond to the auto correlations of the two inputs used
        in the specified baseline."""
        i1,i2 = self.bls_ordering[id]
        a1,a2 = self.autos[self.inputs.index(i1)], self.autos[self.inputs.index(i2)]
        return (a1,a2)

    def id_to_real_str(self, id, short=False):
        id = self.user_to_id(id)
        if self._id_to_real.has_key(id):
            return (short and self._id_to_real[id] or self._id_to_real_long[id])
        else:
            return "Unknown id (%i)" % id

    def _convert_pol(self, pol):
        """Turn a user specified polarisation into
        a pol index (0,1,2,3)
        """
        if type(pol) == type(""):
            if pol.lower() in self._pol_dict: pol = self._pol_dict.index(pol.lower())
            else: pol = -1
        if pol < 0 or pol > 3:
            logger.warning("Unknown polarisation (" + str(pol) + ") specified.")
            return None
        return pol

    def _user_to_id(self, inp):
        if type(inp) != type(()): return inp
        if len(inp) == 2:
            try:
                return self.bls_ordering.index([inp[0].lower(),inp[1].lower()])
            except ValueError:
                logger.warning("Unknown label pair (%s,%s) provided. Consult cpref.labels for valid labels (usually located under sd or sd_hist)." % (inp[0],inp[1]))
                return None
        if len(inp) == 3:
            pol = self._pol_dict[self._convert_pol(inp[2])]
            blkey = ["ant%s%s" % (str(inp[0]),pol[0]),"ant%s%s" % (str(inp[1]),pol[1])]
            try:
                prod_id = self.bls_ordering.index(blkey)
            except ValueError:
                logger.warning("Unknown antenna / polarisation triple (ant%s%s * ant%s%s) specified. It may be that the form of the input labels from the dbe do not support direct antenna addressing (ant\w+[H|V] e.g. ant1H). Consult cpref.bls_ordering to see the mapping provided by the correlator (usually located under sd or sd_hist)." % (str(inp[0]),pol[0],str(inp[1]),pol[1]))
                return None
        else:
            logger.warning("Product specifier " + str(inp) + " not parseable.")
            return None
        return prod_id

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

class SignalDisplayFrame(object):
    """A class to store a single frame of signal display data.
    """
    def __init__(self, timestamp_ms, corr_prod_id, length):
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
            logger.warning("Specified type "+dtype+" is unknown. Must be in "+repr(self._allowed_views))
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

    def get_avg_power(self, start_channel=0, stop_channel=None, rfi_mask=set()):
        """Return the power averaged over frequency channels specified.
           Default is all channels in the frame.
           An rfiMask in set form can be given as well which will exclude the masked channels from the calculation."""
        mag = self.get_mag(start_channel,stop_channel)
        return np.average(np.ma.masked_array(mag, [x in rfi_mask for x in range(1,len(mag)+1)]))

        #return np.average(np.abs(self.data.view(dtype=np.complex64)[start_channel:stop_channel]))

class SignalDisplayStore2(object):
    """A class to store signal display data. Basically a pre-allocated numpy array of sufficient size to store incoming data.
    This will have issues when the incoming sizes change (different channels, baselines) - thus a complete purge of the datastore
    is done whenever channel or baseline count changes."""
    def __init__(self, n_ants=2, capacity=0.2):
        try:
            import psutil
            self.mem_cap = int(psutil.virtual_memory()[0] * capacity)
        except ImportError:
            self.mem_cap = 1024*1024*128
             # default to 128 megabytes if we cannot determine system memory
        logger.info("Store will use %.2f MBytes of system memory." % (self.mem_cap / (1024.0*1024.0)))
        self.n_ants = n_ants
        self.center_freqs_mhz = []
         # currently this only gets populated on loading historical data
        self.n_chans = 0
        self.n_bls = 0
        self._last_ts = 0
        self.roll_point = 0
        self.cpref = None
        self.frame_count = 0
        self.ts = None
        self.first_pass = True
        self.blmxfirst_pass = True
        self.timeseriesfirst_pass = True
        self.timeseriesmaskstr=''

    def init_storage(self, n_chans=512, blmxn_chans=256, n_bls=0):
        gc.collect()#garbage collect before large memory allocation to help prevent fragmentation
        self.n_chans = n_chans
        self.n_bls = n_bls
        self._frame_size_bytes = np.dtype(np.complex64).itemsize * self.n_chans
        nperc = 5*8 #5 percentile levels [0% 100% 25% 75% 50%] times 8 standard collections [auto,autohh,autovv,autohv,cross,crosshh,crossvv,crosshv]
        self.slots = self.mem_cap / (self._frame_size_bytes * (self.n_bls+nperc))
        self.data = np.zeros((self.slots, self.n_bls, self.n_chans),dtype=np.complex64)
        self.flags = np.zeros((self.slots, self.n_bls, self.n_chans), dtype=np.uint8)
        self.ts = np.zeros(self.slots, dtype=np.uint64)
        self.timeseriesslots=self.slots
        self.timeseriesdata = np.zeros((self.timeseriesslots, self.n_bls),dtype=np.complex64)
        self.timeseriests = np.zeros(self.timeseriesslots, dtype=np.uint64)
        self.timeseriesroll_point = 0
        self.blmxslots = 256
        self.blmxn_chans = blmxn_chans
        self.blmxdata = np.zeros((self.blmxslots, self.n_bls, self.blmxn_chans),dtype=np.complex64)#low resolution baseline matrix data
        self.blmxvalue = np.zeros((self.n_bls),dtype=np.complex64)#instantaneous value showing standard deviation in real, and number of phase wraps in imag
        self.blmxts = np.zeros(self.blmxslots, dtype=np.uint64)
        self.blmxroll_point = 0
        self.outliertime=  5
        self.percdata = np.zeros((self.slots, nperc, self.n_chans),dtype=np.complex64)
        self.timeseriespercdata = np.zeros((self.timeseriesslots, nperc),dtype=np.complex64)
        self.percflags = np.zeros((self.slots, nperc, self.n_chans),dtype=np.uint8)
        self.percrunavg = []
        self.frame_count = 0
        self.roll_point = 0
        self._last_ts = 0
        self.first_pass = True
        self.blmxfirst_pass = True
        self.timeseriesfirst_pass = True
        self.timeseriesmaskstr=''
        gc.collect()#garbage collect after large memory allocation to release previous large block of memory

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
    def add_data(self, timestamp_ms, corr_prod_id, offset, length, data, flags=None):
        if timestamp_ms != self._last_ts: self.frame_count += 1
        if self.first_pass and self.frame_count > self.slots: self.first_pass = False
        self.roll_point = (self.frame_count-1) % self.slots
        self.ts[self.roll_point] = timestamp_ms
        self.data[self.roll_point][corr_prod_id][offset:offset+len(data)] = data.view(np.complex64)
        if flags is not None:
            self.flags[self.roll_point][corr_prod_id][offset:offset+len(data)] = flags
        self._last_ts = timestamp_ms

    #data is one timestamps worth of timeseries data [bls] complex data
    #sorts this collection of data into 0% 100% 25% 75% 50%
    #return shape is [5]
    def percsort(self,data,percrunavg):
        nsignals=data.shape[0]
        isort=np.argsort(np.abs(data),axis=0)
        ilev=(nsignals*25)/100;
        #define outlier threshold percentile level eg 90%
        #define outlier halflife eg 20s
        #if signal falls outside threshold, within its collection, for outlier period or longer (in past from now backwards), then outlier
        
        #outlier calculation based not on spectrum, only on timeseries for given halflife period; look at channel[0]
        #for this (out of 8) collection product, the list of signals that is >threshold now is [....]
        #for all 8 collections *[all signals in collection] store running average percentile score for each signal in collection at each time
        iisort=np.argsort(isort)#uses timeseries
        curoutlierlevel=100.0*(np.abs(iisort-(nsignals-1)/2.0)/(nsignals-1)+0.5)#percent, not fraction
        #nsamplesdelay=outlierdelay/dumptime
        nsamplesdelay=self.outliertime        
        percrunavg=(curoutlierlevel+percrunavg*(nsamplesdelay-1.0))/nsamplesdelay
        
        return [[data.reshape(-1)[isort[0]],
            data.reshape(-1)[isort[-1]],
            data.reshape(-1)[isort[ilev]],
            data.reshape(-1)[isort[-1-ilev]],
            data.reshape(-1)[isort[nsignals/2]]],percrunavg]
        
        
    #calculate percentile statistics
    #calculates masked average for this single timestamp for each data product (incl for percentiles)
    #assumes bls_ordering of form [['ant1h','ant1h'],['ant1h','ant1v'],[]]
    def add_data2(self, timestamp_ms, data, flags=None, data_index=None, timeseries=None, percspectrum=None, percspectrumflags=None, blmxdata=None, blmxflags=None):
        with datalock:
            if timestamp_ms != self._last_ts: self.frame_count += 1
            if self.first_pass and self.frame_count > self.slots: self.first_pass = False
            if self.blmxfirst_pass and self.frame_count > self.blmxslots: self.blmxfirst_pass = False
            if self.timeseriesfirst_pass and self.frame_count > self.timeseriesslots: self.timeseriesfirst_pass = False
            self.roll_point = (self.frame_count-1) % self.slots
            self.ts[self.roll_point] = timestamp_ms
            self.timeseriesroll_point = (self.frame_count-1) % self.timeseriesslots
            self.timeseriests[self.timeseriesroll_point] = timestamp_ms
            #calculate timeseries masked average for all signals and overwrite it into channel 0
            if (timeseries is not None):
                self.timeseriesdata[self.timeseriesroll_point,:] = timeseries
                #calculate percentile statistics [0% 100% 25% 75% 50%] for autohhvv,autohh,autovv,autohv,crosshhvv,crosshh,crossvv,crosshv
                #percdata bl ordering: autohhvv 0% 100% 25% 75% 50%,autohh 0% 100% 25% 75% 50%,autovv,autohv,crosshhvv,crosshh,crossvv,crosshv        
                perctimeseries=[]
                #only calculate percentiles for timeseries (for spectrum, percentiles are calculated by ingest)
                for ip,iproducts in enumerate(self.collectionproducts):
                    if (len(iproducts)>0):
                        pdata,self.percrunavg[ip]=self.percsort(timeseries[iproducts],self.percrunavg[ip])
                        perctimeseries.extend(pdata)
                    else:
                        perctimeseries.extend(np.nan*np.zeros([5],dtype=np.complex64))
                self.percdata[self.roll_point,:,:]=np.array(percspectrum,dtype=np.complex64).swapaxes(0,1)                
                self.percflags[self.roll_point,:,:]=np.array(percspectrumflags,dtype=np.uint8).swapaxes(0,1)
                self.timeseriespercdata[self.timeseriesroll_point,:] = np.array(perctimeseries,dtype=np.complex64)
                self.blmxroll_point = (self.frame_count-1) % self.blmxslots
                self.blmxdata[self.blmxroll_point,:,:] = blmxdata
                self.blmxts[self.blmxroll_point] = timestamp_ms
                #blmx calculation
                if (blmxflags is None):
                    self.blmxvalue = np.std(blmxdata,axis=1) # for now but should improve, perhaps std of diff, and phase is number of wraps
                else:
                    for iprod in range(blmxdata.shape[0]):
                        valid=np.nonzero(blmxflags[iprod,:]==0)[0]
                        absdata=np.abs(blmxdata[iprod,valid])
                        meanabs=np.mean(absdata)
                        diffabs=np.diff(absdata)
                        stddiffabs=np.std(diffabs)
                        diffangle=np.diff(np.angle(blmxdata[iprod,valid]))
                        stddiffangle=np.std(diffangle)
                        if (stddiffangle==0):
                            self.blmxvalue[iprod]=meanabs/stddiffabs
                        else:
                            meandiffangle=np.mean(diffangle)
                            validangle=np.nonzero(np.abs(diffangle-meandiffangle)<stddiffangle)[0]
                            #filtered_anglestd=np.std(diffangle[validangle])
                            filtered_anglemean=np.mean(diffangle[validangle])
                            self.blmxvalue[iprod]=meanabs/stddiffabs+1j*filtered_anglemean

            if (data_index is not None):
                if (flags is not None):
                    self.flags[self.roll_point,data_index,:] = flags
                self.data[self.roll_point,data_index,:] = data

            self._last_ts = timestamp_ms

class SignalDisplayStore(object):
    """A class to store signal display data and provide a variety of views onto the data
    for it's clients.
    Parameters
    ----------
    n_ants : integer
        The number of antennas in the system. used for conversion. !!To be replaced by antenna config file!!
    capacity : float
        The fraction of total physical memory to use for data storage on this machine.
        default: 0.2
    """
    def __init__(self, n_ants=2, capacity=0.2):
        try:
            import psutil
            self.mem_cap = int(psutil.virtual_memory()[0] * capacity)
        except ImportError:
            self.mem_cap = 1024*1024*128
             # default to 128 megabytes if we cannot determine system memory
        print "Store will use %.2f MBytes of system memory." % (self.mem_cap / (1024.0*1024.0))
        self.n_ants = n_ants
        self.center_freqs_mhz = []
         # currently this only gets populated on loading historical data
        self.n_chans = 512
         # a default value, that gets overwritten on loading data
        self.cpref = None
        self.init_storage()
        self.frame_count = 0

    def get_capacity(self):
        """Print out the current store capacity..."""
        print "Used %.2f/%.2f MB." % (self.bytes_used / (1024.0*1024), self.mem_cap / (1024.0*1024))
        if self._frame_size_bytes is not None:
            print "In total %is of data can be stored." % (self.mem_cap / (self._frame_size_bytes * len(self.cur_frames)))
        else:
            print "Unable to estimate number of integrations to be stored until capture has started."

    def init_storage(self):
        """Clear all data storage structures in the store."""
        self.time_frames = {}
         # a dictionary of SignalDisplayFrames. Organised by timestamp and then correlation product id
        self.corr_prod_frames = {}
         # a dictionary of SignalDisplayFrames. Organised by correlation product id and then timestamp (ref same data as time_frames)
        self._last_frame = None
        self._last_data = None
        self._last_offset = None
        self._frame_size_bytes = None
        self.frame_count = 0
        self.bytes_used = 0
        self.cur_frames = {}
         # a dict of the most recently completed frames for each corr_prod_id. Not guaranteed to be for the same timestamp...

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
        if not self.time_frames.has_key(timestamp_ms):
            self.time_frames[timestamp_ms] = {}
        if not self.corr_prod_frames.has_key(corr_prod_id):
            self.corr_prod_frames[corr_prod_id] = {}

        if not self.time_frames[timestamp_ms].has_key(corr_prod_id):
            frame = SignalDisplayFrame(timestamp_ms, corr_prod_id, length)
            self.frame_count += 1
            self.time_frames[timestamp_ms][corr_prod_id] = frame
            self.corr_prod_frames[corr_prod_id][timestamp_ms] = frame
             # add the blank frame
        else:
            frame = self.time_frames[timestamp_ms][corr_prod_id]

        frame.add_data(offset, data)
        if frame._valid:
            self.cur_frames[corr_prod_id] = frame
             # always point to the most recently completed valid frame
         # if we have run up against our storage capacity we should complete the current frame and the pop the earliest frame from the stack...
        if self._frame_size_bytes is None:
            self._frame_size_bytes = data.dtype.itemsize * length
        self.bytes_used = self.frame_count * self._frame_size_bytes
        if self.bytes_used > self.mem_cap:
            ts = min(self.time_frames.keys())
            x = self.time_frames.pop(ts)
             # pop out the oldest time element
            for prod_id in x.iterkeys():
                self.corr_prod_frames[prod_id].pop(ts)
                self.frame_count -= 1
             # remove the stale timestamps from individual ids
            del x

        self._last_frame = frame
        self._last_data = data
        self._last_offset = offset

    def pc_load_letter(self, filename, rows=None, startrow=None, cf=1.8e9, nc=512):
        """Load signal display data from an hdf5 v2 generated by the packetised correlator."""
        import os
        import h5py
        try:
            os.stat(filename)
            d = h5py.File(filename)
        except OSError:
            print "Specified file (%s) could not be found." % filename
            return
        bls_ordering = None

        try:
            cc = d['/MetaData/Configuration/Correlator']
            bls_ordering = [[bl[0].lower(),bl[1].lower()] for bl in cc.attrs['bls_ordering']]
            bw = cc.get('bandwidth') and cc['bandwidth'][0] or cc.attrs['bandwidth']
            nc = cc.get('n_chans') and cc['n_chans'][0] or cc.attrs['n_chans']
            self.n_chans = nc
            cf = d['/MetaData/Sensors/RFE/center-frequency-hz'][0][1]
            self.center_freqs_mhz = [(cf + (bw/nc*1.0)*c + 0.5*(bw/nc*1.0))/1000000 for c in range(-nc/2, nc/2)]
            self.center_freqs_mhz.reverse()
             # channels mapped in reverse order
        except KeyError:
            print "Did not find the required attributes bandwidth and n_chans. Frequency information not populated\n"
            pass
        self.cpref = CorrProdRef(bls_ordering=bls_ordering)

        frame_len = nc * 2
        if (startrow!=None):
            tss = d['/Data/timestamps'][startrow:startrow+rows]
            print "Loading %i integrations..." % tss.shape[0]
            data = d['/Data/correlator_data']
            for i,t in enumerate(tss):
                print ".",
                d = data[i+startrow].swapaxes(0,1)
                # now in baseline, freq, complex order
                for id in range(d.shape[0]):
                    self.add_data(t*1000, id, 0, frame_len, d[id].flatten())
                sys.stdout.flush()
        else:
            tss = d['/Data/timestamps'][:rows]
            print "Loading %i integrations..." % tss.shape[0]
            data = d['/Data/correlator_data']
            for i,t in enumerate(tss):
                print ".",
                d = data[i].swapaxes(0,1)
                # now in baseline, freq, complex order
                for id in range(d.shape[0]):
                    self.add_data(t*1000, id, 0, frame_len, d[id].flatten())
                sys.stdout.flush()
        print "\nLoad complete..."

    def load(self, filename, cscan=None, scan=None, start=None, end=None):
        """Load signal display data from a previously captured HDF5 file.
        Generally the file is flatenned and all data is read in.
        If cscan is set then only the specified CompoundScan will be used. Likewise for scan.
        The start and end frame can be specified to limit to data that is retrieved.
        If channel information like the center_frequency and bandwidth is available a freqs table is populated.
        """
        import os
        import h5py
        try:
            os.stat(filename)
            d = h5py.File(filename)
            try:
                cf = d['Correlator'].attrs['center_frequency_hz']
                bw = d['Correlator'].attrs['channel_bandwidth_hz']
                nc = int(d['Correlator'].attrs['num_freq_channels'])
                self.n_chans = nc
                self.center_freqs_mhz = [(cf + bw*c + 0.5*bw)/1000000 for c in range(-nc/2, nc/2)]
                self.center_freqs_mhz.reverse()
                 # channels mapped in reverse order
            except KeyError:
                pass # no frequency information

            bls_ordering = None
            try:
                ant_to_inp = {}
                for antenna in d['/Antennas/']:
                    for pol in d['/Antennas/'][antenna]:
                        if pol in ['H','V']: ant_to_inp[d['/Antennas'][antenna][pol].attrs['dbe_input']] = "ant" + str(antenna)[7:] + str(pol)
                im = d['/Correlator/input_map'].value
                bls_ordering = []
                for v in im:
                    bls_ordering.append([ant_to_inp[v[1][:2]].lower(),ant_to_inp[v[1][2:]].lower()])
            except KeyError:
                pass #no default baseline information
            self.cpref = CorrProdRef(bls_ordering=bls_ordering)

            for cscan in (cscan in d['Scans'].keys() and [cscan] or d['Scans'].keys()):
                for s in (scan in d['Scans'][cscan].keys() and [d['Scans'][cscan][scan]] or [d['Scans'][cscan][s] for s in d['Scans'][cscan].keys()]):
                    print "Adding data from %s" % s.name
                    data = s['data'].value[start:end]
                    ts = s['timestamps'].value[start:end]
                    for i,t in enumerate(ts):
                        dt = data[i]
                        for id in range(len(dt[0])):
                            d_float = np.ravel(np.array([np.real(dt[str(id)]),np.imag(dt[str(id)])]), order='F')
                            self.add_data(t, id, 0, len(d_float), d_float)
        except OSError:
            print "Specified file (%s) could not be found." % filename

    def __getitem__(self, name):
        try:
            return self.time_frames[name]
        except KeyError:
            return None

    def stats(self):
        """Print out the current state of the data store."""
        print "Data ID".center(7),"Frames".center(6),"Earliest Stored Data".center(26),"Latest Stored Data".center(26)
        print "".center(7,"="), "".center(6,"="), "".center(26,"="), "".center(26,"=")
        for id in self.corr_prod_frames.keys():
            times = self.corr_prod_frames[id].keys()
            print str(id).center(7),str(len(times)).center(6),time.ctime(min(times)/1000).center(26), time.ctime(max(times)/1000).center(26)

class NullReceiver(object):
    """Null class used when loading historical data into signal displays...
    """
    def __init__(self, storage, channels=512, n_ants=8):
        self.storage = storage
        self.center_freqs_mhz = self.storage.center_freqs_mhz
         # trickle loaded center frequencies upwards
        self.channels = channels
        self.cpref = CorrProdRef(n_ants=n_ants)
        self.current_timestamp = 0
        self.last_ip = None

class MultiStream(six.Iterator):
    """Provides an interface similar to :class:`spead2.recv.Stream` that is
    useful when a single receiver wants to receive multiple streams, one after
    the other. It transparently tears down and recreates the underlying stream
    when an end-of-stream heap is received.

    Iterating over this object will terminate only when :meth:`stop` is
    called.

    It presents a subset of the interface of :class:`spead2.recv.Stream`. This
    class is in general *not* thread-safe, but it is safe to call :meth:`stop`
    from another thread.
    """

    def __init__(self, *args, **kwargs):
        self._lock = threading.Lock()   # Protects _stream and _stopped
        self._construct = lambda: spead2.recv.Stream(*args, **kwargs)
        self._updaters = []
        self._stream = self._make_stream()
        self._stopped = False

    def _make_stream(self):
        stream = self._construct()
        for func in self._updaters:
            func(stream)
        return stream

    def _add_updater(self, func, args, kwargs):
        self._updaters.append(lambda stream: func(stream, *args, **kwargs))
        func(self._stream, *args, **kwargs)

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            if self._stopped:
                raise StopIteration
            stream = self._stream
        try:
            return six.next(stream)
        except StopIteration:
            # Stream has stopped, so start the next one, unless
            # stop() was called
            with self._lock:
                if self._stopped:
                    raise StopIteration
                self._stream = self._make_stream()
            return None

    def stop(self):
        """Stop the multi-stream, and break out of the iteration. It is safe
        to call this function from another thread while iterating over the
        stream."""
        with self._lock:
            self._stopped = True
            self._stream.stop()

    @classmethod
    def _add_wrapper(cls, name):
        wrapped = getattr(spead2.recv.Stream, name)
        @six.wraps(wrapped)
        def wrapper(self, *args, **kwargs):
            self._add_updater(wrapped, args, kwargs)
        setattr(cls, name, wrapper)

for name in ['add_udp_reader', 'add_buffer_reader', 'set_memory_pool']:
    MultiStream._add_wrapper(name)

class SpeadSDReceiver(threading.Thread):
    """A class to receive signal display data via SPEAD and store it in a SignalDisplayData object.

    Parameters
    ----------
    port : integer
        The port on which to listen for SPEAD udp packets.
    storage : SignalDispayStore
        The object in which to store the received signal display data. If none specified then only the current frame
        of data will be available at any given time.
        default: None
    direct : boolean
        If true then receive and parse a direct correlator emitted SPEAD stream as opposed to the sanitised signal display version...
    """
    def __init__(self, port, storage, notifyqueue=None, direct=False):
        self._port = port
        self.storage = storage
        self.cpref = CorrProdRef()
         # this will start off with a default mapping that will get updated when bls_ordering received via SPEAD
        self.rx = MultiStream(spead2.ThreadPool(), bug_compat=spead2.BUG_COMPAT_PYSPEAD_0_5_2)
        self.rx.add_udp_reader(self._port)
        self.ig = spead2.ItemGroup()
        self.heap_count = 0
        self.bls_ordering = None
        self.center_freq = 0
        self.channels = 0
        self.channel_bandwidth = 0
        self.center_freqs_mhz = []
        self.direct = direct
        self._direct_meta_required = ['sync_time','scale_factor_timestamp','n_chans','center_freq','bandwidth','bls_ordering']
        self._direct_meta = {}
        self.notifyqueue = notifyqueue
        threading.Thread.__init__(self)

    def stop(self):
        if self.rx is not None: self.rx.stop()

    def update_center_freqs(self):
        """Update the table containing the center frequencies for each channels."""
        logger.info("Attempting to update center frequencies...")
        try:
            self.center_freq = self.ig['center_freq'].value or 1284.0e6 #temporary hack because center_freq not available in AR1
            self.channels = self.ig['n_chans'].value
            self.channel_bandwidth = self.ig['bandwidth'].value / self.channels
            self.center_freqs_mhz = [(self.center_freq + self.channel_bandwidth*c + 0.5*self.channel_bandwidth)/1000000 for c in range(-self.channels/2, self.channels/2)]
            #self.center_freqs_mhz.reverse() #temporary hack because center_freq not available in AR1
             # channels mapped in reverse order
        except ValueError:
            logger.warning("Failed to update center frequency table due to missing metadata.")

    def run(self):
        """Main thread loop. Creates socket connection, handles incoming data and marshalls it into
           the storage object.
        """
        if self.direct:
            for heap in self.rx:
                self.ig.update(heap)
                self.heap_count += 1
                if self._direct_meta_required == []:
                 # we have enough meta data to handle direct responses
                    if self.ig['xeng_raw'].value is not None:
                        ts = int((self._direct_meta['sync_time'] + (self.ig['timestamp'].value / self._direct_meta['scale_factor_timestamp'])) * 1000)
                        if isinstance(self.storage,SignalDisplayStore2):
                            data = self.ig['xeng_raw'].value.astype(np.float32).view(np.complex64).swapaxes(0,1)[:,:,0]
                            self.storage.add_data2(ts, data)
                        else:
                            data = self.ig['xeng_raw'].value.swapaxes(0,1)
                            for id in range(data.shape[0]):
                                fdata = data[id].flatten()
                                self.storage.add_data(ts, id, 0, len(fdata), fdata)
                else:
                    for name in self.ig.keys():
                        if name in self._direct_meta_required:
                            self._direct_meta[name] = self.ig[name].value
                            self._direct_meta_required.remove(name)
                    if self._direct_meta_required == []:
                        self.update_center_freqs()
                        self.cpref.bls_ordering = [[bl[0].lower(),bl[1].lower()] for bl in self._direct_meta['bls_ordering']]
                        logger.info("\nAll Metadata for direct stream acquired")
                        logger.info("=======================================")
                        logger.info("Channels: %i, Bandwidth: %.2e, Center Freq: %.3e" % (self._direct_meta['n_chans'], self._direct_meta['bandwidth'], self._direct_meta['center_freq']))
                        logger.info("Sync Time: %i, Scale Factor: %i" % (self._direct_meta['sync_time'], self._direct_meta['scale_factor_timestamp']))
                        logger.info("Baseline Ordering Mapping: %i entries\n" % len(self.cpref.bls_ordering))
                        self.cpref.precompute()
                        if isinstance(self.storage, SignalDisplayStore): self.storage.init_storage()
                        else:
                            self.storage.init_storage(n_chans = self._direct_meta['n_chans'], blmxn_chans = self.ig['sd_blmxdata'].shape[0], n_bls = len(self.cpref.bls_ordering))
                            self.storage.collectionproducts,self.storage.percrunavg=set_bls(self.cpref.bls_ordering)
                            self.storage.timeseriesmaskind,weightedmask,self.storage.spectrum_flag0,self.storage.spectrum_flag1=parse_timeseries_mask(self.storage.timeseriesmaskstr,self.storage.n_chans)
        else:
            bls_ordering_version = -1
            for heap in self.rx:
                if (heap is None):
                    if (self.notifyqueue):
                        self.notifyqueue.put('end of stream')
                    logger.info("End of stream notification")
                    continue
                elif (heap.is_start_of_stream()):
                    if (self.notifyqueue):
                        self.notifyqueue.put('start of stream')
                    logger.info("Start of stream notification")
                    continue
                self.ig.update(heap)
                self.heap_count += 1
                try:
                    if self.ig['n_chans'].value is not None:
                        if self.ig['n_chans'].value != self.channels:
                            logger.info("Signal display store data purged due to changed n_chans from "+str(self.channels)+" to "+str(self.ig['n_chans'].value))
                            self.update_center_freqs()
                            if isinstance(self.storage, SignalDisplayStore): self.storage.init_storage()
                            else:
                                self.storage.init_storage(n_chans = self.ig['n_chans'].value, blmxn_chans = self.ig['sd_blmxdata'].shape[0], n_bls = len(self.cpref.bls_ordering))
                                self.storage.collectionproducts,self.storage.percrunavg=set_bls(self.cpref.bls_ordering)
                                self.storage.timeseriesmaskind,weightedmask,self.storage.spectrum_flag0,self.storage.spectrum_flag1=parse_timeseries_mask(self.storage.timeseriesmaskstr,self.storage.n_chans)
                    if self.ig['center_freq'].value is not None and self.ig['bandwidth'].value is not None and self.ig['n_chans'].value is not None:
                        if self.ig['center_freq'].value != self.center_freq or self.ig['bandwidth'].value / self.ig['n_chans'].value != self.channel_bandwidth:
                            self.update_center_freqs()
                            logger.info("New center frequency:"+str(self.center_freq)+" channel bandwidth: "+str(self.channel_bandwidth))
                    if self.ig['bls_ordering'].version != bls_ordering_version:
                        if [[bl[0].lower(),bl[1].lower()] for bl in self.ig['bls_ordering'].value] != self.bls_ordering:
                            logger.info("Previous bls ordering: {}".format(self.bls_ordering))
                            self.bls_ordering = [[bl[0].lower(),bl[1].lower()] for bl in self.ig['bls_ordering'].value]
                            self.cpref.bls_ordering = self.bls_ordering
                            self.cpref.precompute()
                            logger.info("Signal display store data purged due to changed baseline ordering...")
                            logger.info("New bls ordering: {}".format(self.bls_ordering))
                            if isinstance(self.storage, SignalDisplayStore): self.storage.init_storage()
                            else:
                                self.storage.init_storage(n_chans = self.ig['n_chans'].value, blmxn_chans = self.ig['sd_blmxdata'].shape[0], n_bls = len(self.cpref.bls_ordering))
                                self.storage.collectionproducts,self.storage.percrunavg=set_bls(self.cpref.bls_ordering)
                                self.storage.timeseriesmaskind,weightedmask,self.storage.spectrum_flag0,self.storage.spectrum_flag1=parse_timeseries_mask(self.storage.timeseriesmaskstr,self.storage.n_chans)
                        bls_ordering_version = self.ig['bls_ordering'].version
                    hasdata = (self.ig['sd_data'].value is not None)
                    if (hasdata) or (self.ig['sd_percspectrum'].value is not None):
                        ts = self.ig['sd_timestamp'].value * 10.0
                         # timestamp is in centiseconds since epoch (40 bit spead limitation)
                        if isinstance(self.storage, SignalDisplayStore2):
                            self.storage.add_data2(ts,  self.ig['sd_data'].value.astype(np.float32).view(np.complex64).swapaxes(0,1)[:,:,0] if hasdata else None, \
                                                        self.ig['sd_flags'].value.swapaxes(0,1) if hasdata and ('sd_flags' in self.ig.keys()) else None , \
                                                        self.ig['sd_data_index'].value.astype(np.uint32) if hasdata else None, \
                                                        self.ig['sd_timeseries'].value.astype(np.float32).view(np.complex64)[:,0], \
                                                        self.ig['sd_percspectrum'].value.astype(np.float32), \
                                                        self.ig['sd_percspectrumflags'].value.astype(np.uint8), \
                                                        self.ig['sd_blmxdata'].value.astype(np.float32).view(np.complex64).swapaxes(0,1)[:,:,0], \
                                                        self.ig['sd_blmxflags'].value.astype(np.uint8).swapaxes(0,1))
                        elif (hasdata):
                            data = self.ig['sd_data'].value.swapaxes(0,1)
                            for id in range(data.shape[0]):
                                fdata = data[id].flatten()
                                self.storage.add_data(ts, id, 0, len(fdata), fdata)
                except Exception, e:
                    logger.warning("Failed to add signal display frame. (" + str(e) + ")", exc_info=True)
        self.rx.stop()

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
    def __init__(self, port, storage, n_ants=2, recv_buffer=512000):
        self.port = port
        self.storage = storage
        self._running = True
        self.data_rate = 0
        self.process_time = 0
        self.n_ants = n_ants
        self.cpref = CorrProdRef(n_ants=self.n_ants,no_bls=True)
         # default to 2 antennas as this receiver only used by fringe finder
        threading.Thread.__init__(self)
        self.packet_count = 0
        self.recv_buffer = recv_buffer
        self.rfi_mask = set()
        self._one_shot = -1
        self.current_frames = {}
        self.last_timestamp = 0
        self.center_freqs_mhz = []
        self.last_ip = None
        self._last_frame = None

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
        """Print out a listing of the current data handler statistics. This includes packet arrival and processing times, as well as the number of frames
        in storage."""
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
        udpIn.settimeout(2)
         # one second timeout. Needed for handling shutdown properly.
        self.packet_count = 0
        d_start = 0
        while self._running:
            try:
                data, self.last_ip = udpIn.recvfrom(9200)
            except socket.timeout:
                continue
            self._last_frame = data
            if self.packet_count % 10 == 0:
                d_start = time.time()
            elif d_start > 0:
                # do this on the next packet
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
        print "Receiver loop terminated..."

class AnimatablePlot(object):
    """A plot container that contains sufficient meta information for the plot to be animated by another thread.

    Essentially you add a reference to a matplotlib plot along with a function pointer that can provide updated plot
    data when called. Arguments for the update function can also be supplied in keyword form.

    Examples
    --------
    Say you want to make an animated image of some random data:

    >>> from matplotlib.pyplot import figure
    >>> from pylab import standard_normal
    >>> from katuilib.data import AnimatablePlot
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
    dh : DataHandler
        A reference to the parent datahandler for this plot
        default: None
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
        self._stopEvent = threading.Event()
        self._styles = ['b','g','r','c','m','y','k']
        self._last_update = time.time()
        self._thread = None

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
        #self.figure.show()
        self.figure.canvas.draw()
        #pl.draw()

    def threaded_animate(self, interval=0.2):
        """Start the animation in another thread...."""
        self._stopEvent.clear()
        self._thread = threading.Thread(target=self.animate, args=((interval,)))
        self._thread.daemon = True
        self._thread.start()

    def stop_threaded_animate(self):
        self._stopEvent.set()
        self._thread = None

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
        while not self._stopEvent.isSet():
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
        self._last_update = time.time()
        stamppos = 0.9
        if self.ax.get_yscale() == 'log': stamppos = 0.1
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
                        #print new_data[1][0:10]
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
                            self.ax.annotate("Timestamp:" + time.ctime(new_data[2]), xy=((xmax*0.2),(ymax*stamppos)))
                    else:
                        self.ax.lines[slot].set_ydata(new_data)
                elif len(self.ax.images) > 0:
                    if self._cbar is not None:
                        new_cax = self._cbar.ax.imshow(new_data, aspect='auto', interpolation='bicubic', animated=True)
                        self._cbar.update_bruteforce(new_cax)
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


class AnimatableSensorPlot(object):
    """A sensor plot container that contains sufficient meta information for the plot to be animated by another thread.

    A list of sensors and plotting parameters is maintained.

    Parameters
    ----------
    sensors : list of katuilib sensor objects
        Sensors whose value to plot. Optional.
    source : "cached" or "stored"
        How to retrieve data.
        "cached" uses .get_cached_history (i.e. the local cache).
        "stored" uses .get_stored_history (i.e. from katstore).
        The default is "cached".
    start_time : datetime or float (seconds since Unix epoch).
        Start of time range (passed to get_cached_histor or get_stored_history).
        Default is 0 (i.e. no limit). Datetime objects are converted to seconds
        since the Unix epoch.
    end_time : datetime or float (seconds since Unix epoch).
        End of time range (passed to get_cached_histor or get_stored_history).
        Default is 0 (i.e. no limit). Datetime objects are converted to seconds
        since the Unix epoch. Negative values select the most recent time period.
    title : str
        Title to give figure.
        Default title is "Sensor Plot".
    legend_loc : object
        Any valid matplotlib legend loc parameter.
        Default is 0 (best guess).

    Examples
    --------
    If you wanted to animate three temperature sensors:

    >>> from katuilib.data import AnimatableSensorPlot
    >>> ap = AnimatableSensorPlot(title="Temperature Sensors")
    >>> ap.add_sensor(kat.ped1.sensor.rfe3_temperature)
    >>> ap.add_sensor(kat.ped2.sensor.rfe5_temperature)
    >>> ap.add_sensor(kat.anc.sensor.bms1_chiller_supply_temperature)
    >>> ap.animate()

    Alternatively, to plot stored sensor histories without a katui configuration:

    >>> from katuilib.data import AnimatableSensorPlot
    >>> site_katstore = "postgresql://kat:kat@kat-monctl.karoo.kat.ac.za/katstore"
    >>> ap = AnimatableSensorPlot(title="Temperature Sensors", source="stored")
    >>> rfe3_temp = katuilib.katcp_client.KATBaseSensor(
    ...    "ped2", "rfe3.temperature", "RFE3 Temperature (Pedestal 2)", "degC", "float",
    ...    katstore=site_katstore)
    ...
    >>> rfe5_temp = katuilib.katcp_client.KATBaseSensor(
    ...    "ped2", "rfe5.temperature", "RFE5 Temperature (Pedestal 2)", "degC", "float",
    ...    katstore=site_katstore)
    ...
    >>> ap.add_sensor(rfe3_temp)
    >>> ap.add_sensor(rfe5_temp)
    >>> ap.show()
    """
    def __init__(self, sensors=None, source="cached", start_time=0, end_time=0, title="Sensor Plot", legend_loc=0):
        if pl is None:
            raise RuntimeError("Can't create AnimatableSensorPlot -- matplotlib not available.")
        if sensors is None:
            self.sensors = []
        else:
            self.sensors = list(sensors)
        self.source = source
        self.figure = pl.figure()
        self.ax = self.figure.gca()
        self.legend_loc = legend_loc
        self._thread = None
        self._stopEvent = threading.Event()
        self._colors = ['b','g','r','c','m','y','k']

        if hasattr(start_time, "timetuple"):
            self.start_time = calendar.timegm(start_time.timetuple())
        else:
            self.start_time = start_time

        if hasattr(end_time, "timetuple"):
            self.end_time = calendar.timegm(end_time.timetuple())
        else:
            self.end_time = end_time

        self.ax.set_xlabel("Time (UTC)")
        self.ax.set_ylabel("Sensor Value")
        self.ax.set_title(title)

    def add_sensor(self, sensor):
        """Add a katuilib sensor to the list of sensors to plot.

        Call .update() or .show() afterwards to update the figure.

        Parameters
        ----------
        sensor : katuilib sensor object
            Sensor to add to the figure.
        """
        self.sensors.append(sensor)

    def threaded_animate(self, interval=0.2):
        """Start the animation in another thread...."""
        self._stopEvent.clear()
        self._thread = threading.Thread(target=self.animate, args=((interval,)))
        self._thread.daemon = True
        self._thread.start()

    def stop_threaded_animate(self):
        self._stopEvent.set()
        self._thread = None

    def animate(self, interval=1):
        """Animate the plot.

        Parameters
        ----------
        interval : float
            The number of second to wait between each update to the plot.
            default: 1
        """
        print "Animating plot. Press Ctrl-C to halt..."
        try:
            self.show()
            while not self._stopEvent.isSet():
                time.sleep(interval)
                self.update()
        except KeyboardInterrupt:
            print "Animation halted."

    def _fetch_data(self, sensor):
        """Retrieve data for updating a sensor plot."""
        if self.source == "stored":
            time_data, value_data, status_data = sensor.get_stored_history(
                select=False,
                start_time=self.start_time,
                end_time=self.end_time,
            )
        else:
            time_data, value_data, status_data = sensor.get_cached_history(
                start_time=self.start_time,
                end_time=self.end_time,
            )

        time_data = np.array(time_data, dtype=float)

        # convert from seconds since epoch to days since 1 AD.
        time_data = time_data / (24.0 * 60.0 * 60.0) + (datetime.datetime(1970, 1, 1) - datetime.datetime(1, 1, 1)).days

        return time_data, value_data, status_data

    def _add_line(self, slot, sensor, limits):
        """Add a new line to the plot."""
        time_data, value_data, _status_data = self._fetch_data(sensor)
        self._update_limits(time_data, value_data, limits)
        label = "%s.%s" % (sensor.parent_name, sensor.name)
        if sensor.units:
            label += " (%s)" % sensor.units
        self.ax.plot_date(time_data, value_data,
            label=label, color=self._colors[slot % len(self._colors)], linestyle="-", marker='')

    def _update_line(self, slot, sensor, limits):
        """Update an existing line in the plot."""
        time_data, value_data, _status_data = self._fetch_data(sensor)
        self._update_limits(time_data, value_data, limits)
        line = self.ax.lines[slot]
        line.set_xdata(time_data)
        line.set_ydata(value_data)

    def _update_limits(self, data_x, data_y, limits):
        """Update the sets of limits."""
        if len(data_x) > 0:
            limits[0][0].append(np.min(data_x))
            limits[0][1].append(np.max(data_x))
            limits[1][0].append(np.min(data_y))
            limits[1][1].append(np.max(data_y))

    def _date_tick_heuresitcs(self, dt):
        """Apply some date tick heurestics."""
        if dt < 10.0 / (24.0 * 60.0):
            # less than ten minutes
            self.ax.xaxis.set_minor_locator(matplotlib.ticker.AutoLocator())
            self.ax.xaxis.set_major_locator(matplotlib.ticker.AutoLocator())
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M:%S'))
        elif dt < 4.0 / 24.0:
            # less than a four hours
            self.ax.xaxis.set_minor_locator(matplotlib.dates.MinuteLocator(interval=1))
            self.ax.xaxis.set_major_locator(matplotlib.dates.MinuteLocator(interval=15))
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d-%b-%Y %H:%M'))
        elif dt < 1.0:
            # less than a day
            self.ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator(interval=1))
            self.ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=6))
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d-%b-%Y %H:%M'))
        elif dt < 7.0:
            # less than a week
            self.ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator(interval=6))
            self.ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=1))
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d-%b-%Y'))
        elif dt < 30:
            # less than a month
            self.ax.xaxis.set_minor_locator(matplotlib.dates.DayLocator(interval=1))
            self.ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=7))
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%d-%b-%Y'))
        else:
            # greater than a month
            self.ax.xaxis.set_minor_locator(matplotlib.dates.DayLocator(interval=1))
            self.ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(interval=1))
            self.ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%b-%Y'))

    def update(self):
        """Single shot update of the plot.
        """
        # xmins, xmaxes, ymins, ymaxes
        limits = ( ([], []), ([], []))

        for slot, sensor in enumerate(self.sensors):
            if slot < len(self.ax.lines):
                self._update_line(slot, sensor, limits)
            else:
                self._add_line(slot, sensor, limits)

        if limits[0][0]:
            xmin, xmax = min(limits[0][0]), max(limits[0][1])
            ymin, ymax = min(limits[1][0]), max(limits[1][1])
            self.ax.set_xlim((xmin, xmax))
            self.ax.set_ylim((ymin*0.95, ymax*1.05))
            self._date_tick_heuresitcs(xmax - xmin)

        self.ax.legend(loc=self.legend_loc)

        self.figure.canvas.draw()

    def show(self):
        """Show the figure."""
        self.update()
        self.figure.show()


class PlotAnimator(object):
    """An animated plot container that allows the user to add a number of AnimatablePlot instances to the container
    and animate these children.

    General use is to create a PlotAnimator object and then using add_plot add a number of AnimatablePlot instances (which are returned
    by most plot_x functions). This group of plots can then be animated together.

    Examples
    --------
    To create an animated signal display chain showing the signal from adc through correlation:
    (assuming you have created a top level kat object using configure or tbuild)

    >>> pa = PlotAnimator()
    >>> ap1 = kat.dh.plot_snapshot('adc')
    >>> ap2 = kat.dh.plot_snapshot('quant')
    >>> ap3 = kat.dh.sd.plot_spectrum()
    >>> ap4 = kat.dh.sd.plot_waterfall()
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
    dbe : KATClient
        A reference to an KATClient object connected to a dbe proxy that has a k7writer reference. This is used to add this current host as a signal display data listener.
    port : integer
        The port on which to receive signal display data.
        default: 7006
    ip : string
        Override the IP detection code by providing a specific IP address to which to send the signal data.
        default: None
    receiver : DataReceiver
        The receiver to use for this data handler. If not specified then a default is created and started.
        default: None
    store : SignalDisplayStore
        The storage to use in the default receiver. If none specified then a default is created.
        default: None
    """
    def __init__(self, dbe=None, port=7006, ip=None, receiver=None, store=None):
        self.dbe = dbe
        if dbe is not None:
            self._local_ip = ip if ip is not None else external_ip()
            if self._local_ip is None:
                print "DataHandler failed to determine external IP address."
            else:
                print "Adding IP",self._local_ip,"to list of signal display destination addresses."
                self.dbe.req.k7w_add_sdisp_ip(self._local_ip)

        self.storage = store
        if store is None:
            self.storage = SignalDisplayStore()

        self.receiver = receiver
        if receiver is None:
            self.receiver = SignalDisplayReceiver(port, self.storage)
            self.receiver.setDaemon(True)
            self.receiver.start()

        quitter.register_callback("Data Handler", self.stop)

        self.cpref = self.receiver.cpref
        self.default_product = (1, 2, 'hh')
        self.default_products = [(1, 2, 'hh')]
        self._debug = False
        self._plots = {}

    def set_default_product(self, product):
        """Sets a default product to use for command within the data handler.
        Can be specified either as a scalar or an array which will set the default
        for the plots appropriate to scalar or array product input.
        """
        if type(product) == type([]): self.default_products = product
        else: self.default_product = product

    def _add_plot(self, fname, ap):
        ap._fname = fname
        self._plots[ap.figure.number] = ap

    def get_plot(self, number):
        if self._plots.has_key(number):
            return self._plots[number]
        else:
            print "Figure %i is not in the active figures list." % number

    def close_plot(self, number):
        if self._plots.has_key(number):
            ap = self._plots.pop(number)
            ap.figure.close()
            del ap
        else:
            print "Figure %i is not in the active figures list." % number

    def list_plots(self):
        print "Figure".center(8),"Calling Function".center(20),"Animating".center(12), "Last Update".center(40)
        print "".center(8,"="), "".center(20,"="), "".center(12,"="), "".center(40,"=")
        for fnumber, ap in self._plots.iteritems():
            print str(fnumber).ljust(8), ap._fname.ljust(20), (ap._thread is None and "No" or "Yes").ljust(12), time.ctime(ap._last_update).ljust(40)

    @property
    def spectrum(self):
        return self.receiver.spectrum

    @property
    def spectrum_xx(self):
        return self.receiver.spectrum['XX']

    @property
    def spectrum_yy(self):
        return self.receiver.spectrum['YY']

    @property
    def spectrum_xy(self):
        return self.receiver.spectrum['XY']

    @property
    def spectrum_yx(self):
        return self.receiver.spectrum['YX']

    @property
    def tp(self):
        return self.receiver.tp

    @property
    def tp_x(self):
        return self.receiver.tp['XX']

    @property
    def tp_y(self):
        return self.receiver.tp['YY']

    def __getattr__(self, name):
        return self.receiver.__getattribute__(name)

    def stop(self):
        """Stop the signal display receiver and deregister our IP from the subscribers to the k7w signal data stream.
        """
        self.receiver.stop()
        if self.dbe is not None and self._local_ip is not None:
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
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
        product = self.cpref.user_to_id(product)
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
        pl.figure(figsize=(14,10))

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
        ax_wfall.set_title("Xcorr phase spectrogram: Click waterfall plot to update other graphs.")

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
            t = time.time()
            fringe_data = self.get_fringes(product=product, channel=f_ref, dtype='re', start_time=min(tstamps), end_time=max(tstamps))
            t = time.time()
            phase_t_data = self.get_time_series(product=product, dtype='phase', start_channel=f_ref, stop_channel=f_ref+1, start_time=min(tstamps), end_time=max(tstamps))
            t = time.time()
            ax_mag_t.plot(fringe_data[1], range(0,len(fringe_data[1]))) #, fringe_data[0][::-1])
            ax_phase_t.plot(phase_t_data[1], range(0, len(phase_t_data[1]))) #, phase_t_data[0][::-1])
            #print "Plotting both mag and phase took %f s" % (time.time() - t)
            ax_wfall.set_ylim((dumps,0))
             # spectral plots
            t = time.time()
            power_f = self.storage.time_frames[np.uint64(tstamps[t_ref] * 1000)][product].get_mag()
            t = time.time()
            #phase_f = self.storage.frames['PHA1A2'][sk[-frames:][t_ref]]
            phase_f = self.storage.time_frames[np.uint64(tstamps[t_ref] * 1000)][product].get_phase()
            sys.stdout.flush()
            t = time.time()
            ax_mag_f.plot(power_f)
            ax_mag_f.set_yscale("log")
            ax_phase_f.plot(phase_f)
            #print "Plotting both mag and phase took %f s" % (time.time() - t)
            t = time.time()
            ax_wfall.set_xlim((0,channels))
             # re vs im
            reim = self.get_fringes(product=product, channel=f_ref, dtype='complex', end_time=-dumps)
            ax_reim.plot(reim[0],reim[1], 'o')

         # define event handler for clicking...
        def onpress(event):
            #print "Dash click event at",time.ctime()
            if event.inaxes != ax_wfall: return
            if event.button == 1: clear_plots()
            x1,y1 = event.xdata, event.ydata
            t_ref = int(y1)
            t = time.ctime(tstamps[t_ref])
            f_ref = int(x1)
            ts = time.time()
            populate(t_ref, f_ref)
            #print "Populate took %f s" % (time.time() - ts)
            ax_mag_t.set_ylabel("Xcorr mag vs time for channel " + str(f_ref))
            ax_phase_t.set_ylabel("Xcorr phase vs time for channel " + str(f_ref))
            ax_mag_f.set_title("Xcorr mag spectrum for " + t)
            ax_phase_f.set_title("Xcorr phase spectrum for " + t)
            ax_reim.set_title("Re vs Im for channel " + str(f_ref))
            ts = time.time()
            f.canvas.draw()
            #print "Draw took %f s" % (time.time() - ts)
            #pl.draw()
            #print "Finished click event at",time.ctime()
        f.canvas.mpl_connect('button_release_event', onpress)
        f.show()
        pl.draw()


    def select_data(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=None, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False, include_flags=False, incr_channel=1):
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
        include_flags : boolean
            Include flags in the return data if available
        """
        if isinstance(self.storage, SignalDisplayStore2):
            lv = locals()
            lv.pop('self')
            return self._select_data2(**lv)
        if product is None: product = self.default_product
        orig_product = product
        product = self.cpref.user_to_id(product)
        if self._debug:
            print "Select data called with product: %i, start_time: %i , end_time: %i, start_channel: %i, end_channel: %i" % (product, start_time, end_time, start_channel, stop_channel)
        try:
            fkeys = self.storage.corr_prod_frames[product].keys()
        except KeyError, exc:
            raise InvalidBaseline("No data for the specified product (%s) was found. Antenna notation (ant_idx, ant_idx, pol) is only available if the DBE inputs have been labelled correctly, otherwise use (label, label) notation. If you are using a valid product then it may be that the system is not configured to send signal display data to your IP address." % (str(orig_product),)), None, None
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
        if reverse_order:
            frames.reverse()
            ts.reverse()
        if include_flags:
            frames = [frames, np.zeros(np.shape(frames))]
        if include_ts:
            ts_ms = np.array([t / 1000.0 for t in ts])
            frames = [ts_ms,frames[0],frames[1]] if include_flags else [ts_ms,frames]
        return frames

    def _select_data2(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=None, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False, include_flags=False, incr_channel=1):
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return

        with datalock:
            if product is None: product = self.default_product
            orig_product = product
            product = self.cpref.user_to_id(product)

            ts = []
            roll_point = (0 if self.storage.first_pass else (self.storage.roll_point+1))
             # temp value in case of change during search...
            rolled_ts = np.roll(self.storage.ts,-roll_point)
            if end_time >= 0:
                split_start = min(np.where(rolled_ts >= start_time * 1000)[0]) + roll_point
                validind=np.where(rolled_ts[:(self.storage.frame_count if self.storage.first_pass else None)] <= end_time * 1000)[0]
                split_end = 1 + max(validind) + roll_point if (len(validind)) else split_start
            else:
                if abs(end_time) > self.storage.slots: end_time = -self.storage.slots
                 # ensure we do not ask for more data than is available
                split_end = self.storage.frame_count #rolled_ts.argmax() + roll_point
                split_start = max(split_end + end_time,0)
            split_end = split_start + self.storage.slots if split_end - split_start > self.storage.slots else split_end

            arraylen=self.storage.data.shape[0];
            _split_start=split_start%arraylen;
            _split_end=split_end%arraylen;
                    
            if (_split_start<_split_end):
                frames=self.storage.data[_split_start:_split_end,product,start_channel:stop_channel:incr_channel]
                if include_flags:
                    flags = self.storage.flags[_split_start:_split_end,product,start_channel:stop_channel:incr_channel]
            else:
                frames=np.concatenate((self.storage.data[_split_start:,product,start_channel:stop_channel:incr_channel], self.storage.data[:_split_end,product,start_channel:stop_channel:incr_channel]),axis=0)
                if include_flags:
                    flags = np.concatenate((self.storage.flags[_split_start:,product,start_channel:stop_channel:incr_channel], self.storage.flags[:_split_end,product,start_channel:stop_channel:incr_channel]),axis=0)

            frames = frames.squeeze()
            if include_flags: flags = flags.squeeze()

            if dtype == 'mag':
                frames = np.abs(frames)
            if dtype == 're':
                frames = np.real(frames)
            if dtype == 'imag':
                frames = np.imag(frames)
            if dtype == 'phase':
                frames = np.angle(frames)
            if avg_axis is not None:
                frames = frames if len(frames.shape) < 2 else np.average(frames, avg_axis)
                if include_flags: flags = flags if len(flags.shape) < 2 else np.sum(flags, avg_axis)
            if sum_axis is not None:
                frames = np.sum(frames, sum_axis)
                if include_flags: flags = flags if len(flags.shape) < 2 else np.sum(flags, sum_axis)
            if reverse_order:
                frames = frames[::-1,...]
                if include_flags: flags = flags[::-1,...]
            if include_ts:
                frames = [np.take(self.storage.ts, range(split_start,split_end),mode='wrap') / 1000.0, frames]
                if reverse_order: frames[0] = frames[0][::-1]
            if include_flags:
                frames = [frames[0], frames[1], flags] if include_ts else [frames, flags]
            return frames

    def select_timeseriesdata(self, product=None, dtype='mag', start_time=0, end_time=-120, reverse_order=False, include_ts=False):
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return

        with datalock:
            if product is None: product = self.default_product
            orig_product = product
            product = self.cpref.user_to_id(product)

            ts = []
            roll_point = (0 if self.storage.timeseriesfirst_pass else (self.storage.timeseriesroll_point+1))
             # temp value in case of change during search...
            rolled_ts = np.roll(self.storage.timeseriests,-roll_point)
            if end_time >= 0:
                split_start = min(np.where(rolled_ts >= start_time * 1000)[0]) + roll_point
                validind=np.where(rolled_ts[:(self.storage.frame_count if self.storage.timeseriesfirst_pass else None)] <= end_time * 1000)[0]
                split_end = 1 + max(validind) + roll_point if (len(validind)) else split_start
            else:
                if abs(end_time) > self.storage.timeseriesslots: end_time = -self.storage.timeseriesslots
                 # ensure we do not ask for more data than is available
                split_end = self.storage.frame_count #rolled_ts.argmax() + roll_point
                split_start = max(split_end + end_time,0)
            split_end = split_start + self.storage.timeseriesslots if split_end - split_start > self.storage.timeseriesslots else split_end

            arraylen=self.storage.timeseriesdata.shape[0];
            _split_start=split_start%arraylen;
            _split_end=split_end%arraylen;

            if (_split_start<_split_end):
                frames=self.storage.timeseriesdata[_split_start:_split_end,product]
            else:
                frames=np.concatenate((self.storage.timeseriesdata[_split_start:,product], self.storage.timeseriesdata[:_split_end,product]),axis=0)

            frames = frames.squeeze()

            if dtype == 'mag':
                frames = np.abs(frames)
            if dtype == 're':
                frames = np.real(frames)
            if dtype == 'imag':
                frames = np.imag(frames)
            if dtype == 'phase':
                frames = np.angle(frames)
            if reverse_order:
                frames = frames[::-1,...]
            if include_ts:
                frames = [np.take(self.storage.timeseriests, range(split_start,split_end),mode='wrap') / 1000.0, frames]
                if reverse_order: frames[0] = frames[0][::-1]
            return frames

    #icollection is index to [auto,autohh,autovv,autohv,cross,crosshh,crossvv,crosshv]
    def get_data_outlier_products(self, icollection, threshold):
        outlierproducts=[]
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return outlierproducts
            
        with datalock:
            iproducts=self.storage.collectionproducts[icollection]
            if (len(iproducts)>0):
                ind=np.nonzero(self.storage.percrunavg[icollection]>threshold)[0]
                sind=np.argsort(self.storage.percrunavg[icollection][ind])[::-1]
                #outlierproducts=iproducts[ind[sind]]# but not np.array
                outlierproducts=[iproducts[ip] for ip in ind[sind]]
                #self.percrunavg[ip][ind[sind]]
            
            return outlierproducts
            
    #product is index to [0,100,25,75,50] for each of [auto,autohh,autovv,autohv,cross,crosshh,crossvv,crosshv]
    def select_data_collection(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=None, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False, include_flags=False, incr_channel=1):
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return

        with datalock:
            ts = []
            roll_point = (0 if self.storage.first_pass else (self.storage.roll_point+1))
             # temp value in case of change during search...
            rolled_ts = np.roll(self.storage.ts,-roll_point)
            if end_time >= 0:
                split_start = min(np.where(rolled_ts >= start_time * 1000)[0]) + roll_point
                validind=np.where(rolled_ts[:(self.storage.frame_count if self.storage.first_pass else None)] <= end_time * 1000)[0]
                split_end = 1 + max(validind) + roll_point if (len(validind)) else split_start
            else:
                if abs(end_time) > self.storage.slots: end_time = -self.storage.slots
                 # ensure we do not ask for more data than is available
                split_end = self.storage.frame_count #rolled_ts.argmax() + roll_point
                split_start = max(split_end + end_time,0)
            split_end = split_start + self.storage.slots if split_end - split_start > self.storage.slots else split_end

            arraylen=self.storage.percdata.shape[0];
            _split_start=split_start%arraylen;
            _split_end=split_end%arraylen;

            if (_split_start<_split_end):
                frames=self.storage.percdata[_split_start:_split_end,product,start_channel:stop_channel:incr_channel]
                if include_flags:
                    flags = self.storage.percflags[_split_start:_split_end,product,start_channel:stop_channel:incr_channel]
            else:
                frames=np.concatenate((self.storage.percdata[_split_start:,product,start_channel:stop_channel:incr_channel], self.storage.percdata[:_split_end,product,start_channel:stop_channel:incr_channel]),axis=0)
                if include_flags:
                    flags = np.concatenate((self.storage.percflags[_split_start:,product,start_channel:stop_channel:incr_channel], self.storage.percflags[:_split_end,product,start_channel:stop_channel:incr_channel]),axis=0)

            frames = frames.squeeze()
            if include_flags: flags = flags.squeeze()

            if dtype == 'mag':
                frames = np.abs(frames)
            if dtype == 're':
                frames = np.real(frames)
            if dtype == 'imag':
                frames = np.imag(frames)
            if dtype == 'phase':
                frames = np.angle(frames)
            if avg_axis is not None:
                frames = frames if len(frames.shape) < 2 else np.average(frames, avg_axis)
                if include_flags: flags = flags if len(flags.shape) < 2 else np.sum(flags, avg_axis)
            if sum_axis is not None:
                frames = np.sum(frames, sum_axis)
                if include_flags: flags = flags if len(flags.shape) < 2 else np.sum(flags, sum_axis)
            if reverse_order:
                frames = frames[::-1,...]
                if include_flags: flags = flags[::-1,...]
            if include_ts:
                frames = [np.take(self.storage.ts, range(split_start,split_end),mode='wrap') / 1000.0, frames]
                if reverse_order: frames[0] = frames[0][::-1]
            if include_flags:
                frames = [frames[0], frames[1], flags] if include_ts else [frames, flags]
            return frames

    def select_timeseriesdata_collection(self, product=None, dtype='mag', start_time=0, end_time=-120, reverse_order=False, include_ts=False):
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return
        with datalock:
            ts = []
            roll_point = (0 if self.storage.timeseriesfirst_pass else (self.storage.timeseriesroll_point+1))
             # temp value in case of change during search...
            rolled_ts = np.roll(self.storage.timeseriests,-roll_point)
            if end_time >= 0:
                split_start = min(np.where(rolled_ts >= start_time * 1000)[0]) + roll_point
                validind=np.where(rolled_ts[:(self.storage.frame_count if self.storage.timeseriesfirst_pass else None)] <= end_time * 1000)[0]
                split_end = 1 + max(validind) + roll_point if (len(validind)) else split_start
            else:
                if abs(end_time) > self.storage.timeseriesslots: end_time = -self.storage.timeseriesslots
                 # ensure we do not ask for more data than is available
                split_end = self.storage.frame_count #rolled_ts.argmax() + roll_point
                split_start = max(split_end + end_time,0)
            split_end = split_start + self.storage.timeseriesslots if split_end - split_start > self.storage.timeseriesslots else split_end

            arraylen=self.storage.timeseriespercdata.shape[0];
            _split_start=split_start%arraylen;
            _split_end=split_end%arraylen;

            if (_split_start<_split_end):
                frames=self.storage.timeseriespercdata[_split_start:_split_end,product]
            else:
                frames=np.concatenate((self.storage.timeseriespercdata[_split_start:,product], self.storage.timeseriespercdata[:_split_end,product]),axis=0)

            frames = frames.squeeze()

            if dtype == 'mag':
                frames = np.abs(frames)
            if dtype == 're':
                frames = np.real(frames)
            if dtype == 'imag':
                frames = np.imag(frames)
            if dtype == 'phase':
                frames = np.angle(frames)
            if reverse_order:
                frames = frames[::-1,...]
                if include_flags: flags = flags[::-1,...]
            if include_ts:
                frames = [np.take(self.storage.timeseriests, range(split_start,split_end),mode='wrap') / 1000.0, frames]
                if reverse_order: frames[0] = frames[0][::-1]
            return frames

    #pol can be any of 'hh','hv','vh','vv'
    def select_blxvalue(self,pol='hh'):
        with datalock:
            if (pol in self.cpref._pol_ids):
                return np.real(self.storage.blmxvalue[self.cpref._pol_ids[pol]]),np.imag(self.storage.blmxvalue[self.cpref._pol_ids[pol]])
        return []

    def select_blmxdata(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=None, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False, include_flags=False, incr_channel=1):
        if self.storage.ts is None:
            print "Signal display store not yet initialised... (most likely has not received SPEAD headers yet)"
            return
            
        with datalock:
            if product is None: product = self.default_product
            orig_product = product
            product = self.cpref.user_to_id(product)

            ts = []
            roll_point = (0 if self.storage.blmxfirst_pass else (self.storage.blmxroll_point+1))
             # temp value in case of change during search...
            rolled_ts = np.roll(self.storage.blmxts,-roll_point)
            if end_time >= 0:
                split_start = min(np.where(rolled_ts >= start_time * 1000)[0]) + roll_point
                validind=np.where(rolled_ts[:(self.storage.frame_count if self.storage.blmxfirst_pass else None)] <= end_time * 1000)[0]
                split_end = 1 + max(validind) + roll_point if (len(validind)) else split_start
            else:
                if abs(end_time) > self.storage.blmxslots: end_time = -self.storage.blmxslots
                 # ensure we do not ask for more data than is available
                split_end = self.storage.frame_count #rolled_ts.argmax() + roll_point
                split_start = max(split_end + end_time,0)
            split_end = split_start + self.storage.blmxslots if split_end - split_start > self.storage.blmxslots else split_end

            arraylen=self.storage.blmxdata.shape[0];
            _split_start=split_start%arraylen;
            _split_end=split_end%arraylen;
            if (_split_start<_split_end):
                frames=self.storage.blmxdata[_split_start:_split_end,product,start_channel:stop_channel:incr_channel]
                if include_flags:
                    flags = np.zeros(frames.shape,dtype=np.uint8)
            else:
                frames=np.concatenate((self.storage.blmxdata[_split_start:,product,start_channel:stop_channel:incr_channel], self.storage.blmxdata[:_split_end,product,start_channel:stop_channel:incr_channel]),axis=0)
                if include_flags:
                    flags = np.zeros(frames.shape,dtype=np.uint8)

            frames = frames.squeeze()
            if include_flags: flags = flags.squeeze()

            if dtype == 'mag':
                frames = np.abs(frames)
            if dtype == 're':
                frames = np.real(frames)
            if dtype == 'imag':
                frames = np.imag(frames)
            if dtype == 'phase':
                frames = np.angle(frames)
            if avg_axis is not None:
                frames = frames if len(frames.shape) < 2 else np.average(frames, avg_axis)
            if sum_axis is not None:
                frames = np.sum(frames, sum_axis)
            if reverse_order:
                frames = frames[::-1,...]
            if include_ts:
                frames = [np.take(self.storage.blmxts, range(split_start,split_end),mode='wrap') / 1000.0, frames]
                if reverse_order: frames[0] = frames[0][::-1]
            if include_flags:
                frames = [frames[0], frames[1], flags] if include_ts else [frames, flags]
            return frames
            
    def get_baseline_matrix(self, start_channel=0, stop_channel=-1):
        map = np.array([[0, 0],
           [0, 1],
           [1, 1],
           [0, 2],
           [1, 2],
           [2, 2],
           [0, 3],
           [1, 3],
           [2, 3],
           [3, 3],
           [0, 4],
           [1, 4],
           [2, 4],
           [3, 4],
           [4, 4],
           [1, 5],
           [2, 5],
           [3, 5],
           [4, 5],
           [5, 5],
           [2, 6],
           [3, 6],
           [4, 6],
           [5, 6],
           [6, 6],
           [3, 7],
           [4, 7],
           [5, 7],
           [6, 7],
           [7, 7],
           [0, 5],
           [0, 6],
           [0, 7],
           [1, 6],
           [1, 7],
           [2, 7]])

        def idx(bl, pol):
            (a,b) = map[bl]
            i1 = a * 2 + (pol % 2 == 0 and 1 or 2) - 1
            i2 = b * 2 + (pol % 3 == 0 and 1 or 2) - 1
            return i1,i2

        im = np.zeros((16,16),dtype=np.float32)
        for bl in range(36):
            for pol in range(4):
                (a,b) = idx(bl,pol)
                if a < b:
                    im[a,b] = np.average(self.storage.cur_frames[bl * 4 + pol].get_phase())
                    im[b,a] = np.average(self.storage.cur_frames[bl * 4 + pol].get_mag()) / 1000
                else:
                    im[a,b] = np.average(self.storage.cur_frames[bl * 4 + pol].get_mag()) / 1000
                    im[b,a] = np.average(self.storage.cur_frames[bl * 4 + pol].get_phase())
                if a == b: im[a,b] = -2 + (np.average(self.storage.cur_frames[bl * 4 + pol].get_mag()) / 1000)
        return im

    def plot_baseline_matrix(self, start_channel=0, stop_channel=-1):
        """Plot a matrix showing auto correlation power on the diagonal and cross correlation
        phase and power in the upper and lower segments."""
        if self.storage is not None:
            im = self.get_baseline_matrix(start_channel=0, stop_channel=-1)
            pl.ion()
            fig = pl.figure()
            ax = fig.gca()
            ax.set_title("Baseline matrix")
            cax = ax.matshow(im, cmap=cm.spectral)
            cbar = fig.colorbar(cax)
            ax.set_yticks(np.arange(16))
            ax.set_yticklabels(['A' + str(x) + (x % 2 == 0 and 'x' or 'y') for x in range(16)])
            ax.set_xticks(np.arange(16))
            ax.set_xticklabels(['A' + str(x) + (x % 2 == 0 and 'x' or 'y') for x in range(16)])
            ax.set_ylim((15.5,-0.5))
            fig.show()
            pl.draw()
            ap = AnimatablePlot(fig, self.get_baseline_matrix, start_channel=start_channel, stop_channel=stop_channel)
            ap.set_colorbar(cbar)
            self._add_plot(sys._getframe().f_code.co_name, ap)
            return ap
        else:
            print "No stored data available..."


    def plot_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=1, stop_channel=-1, include_flags=False):
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
        start_time : integer
            Either a direct specification of the start_time or zero to indicate the earliest available time.
        end_time : integer
            If a positive number then the time window is (start_time - end_time). If negative then start_time is ignored and the most
            recent abs(end_time) entries from the store are selected.
        start_channel : integer
            default: 1
        stop_channel : integer
            default: 512
        include_flags : boolean
            If set to true then produce a seperate plot showing flags as a function of time and frequency...
        Returns
        -------
        ap : AnimatablePlot
        
        Examples
        --------
        First ensure that the signal displays have been started for this client (assuming a 'kat' connection object):
        >>> kat.dh.start_sdisp()
        Then make some plots:
        >>> kat.dh.sd.plot_waterfall()
        >>> kat.dh.sd.plot_waterfall('phase',(1,2,'VV'))
        >>> kat.dh.sd.plot_waterfall(dtype='mag',product=1)
        >>> kat.dh.sd.plot_waterfall(dtype='mag',product=(1,1,'HH'))
        Make an animatable plot:
        >>> ap = kat.dh.sd.plot_waterfall()
        >>> ap.animate()
        
        """
        if product is None: product = self.default_product
        if self.storage is not None:
            select_data_kwargs = {
                'dtype': dtype,
                'product': product,
                'start_time': start_time,
                'end_time': end_time,
                'start_channel': start_channel,
                'stop_channel': stop_channel,
                'reverse_order': True,
            }
            if include_flags: (tp, flags) = self.select_data(include_flags=include_flags, **select_data_kwargs)
            else: tp = self.select_data(**select_data_kwargs)
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
            ap = AnimatablePlot(fig, self.select_data, **select_data_kwargs)
            ap.set_colorbar(cbar)
            self._add_plot(sys._getframe().f_code.co_name, ap)
            if include_flags:
                fig_flag = pl.figure()
                ax_flag = fig_flag.gca()
                ax_flag.set_title("Flag spectrogram")
                ax_flag.set_ylabel("Time in seconds before now")
                ax_flag.set_xlabel("Freq Channel")
                ax_flag.imshow(flags, aspect='auto')
                fig_flag.show()
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
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
        self._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

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

    def get_time_series(self, dtype='mag', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=-1):
        if product is None: product = self.default_product
        tp = self.select_data(dtype=dtype, avg_axis=1, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel)
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

    def plot_time_series(self, dtype='mag', products=None, end_time=-120, scale='log', start_channel=0, stop_channel=-1):
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
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
        self._add_plot(sys._getframe().f_code.co_name, ap)
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
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
        self._add_plot(sys._getframe().f_code.co_name, ap)
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
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
        self._add_plot(sys._getframe().f_code.co_name, ap)
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
        self._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

    def _angle_wrap(self, angle, period=2.0 * np.pi):
        return (angle + 0.5 * period) % period - 0.5 * period

    def plot_phase_closure(self, a=(1,2,'VV'), b=(2,3,'VV'), c=(1,3,'VV'), start_channel=100, stop_channel=400, end_time=-120, swap=False, new_figure=True, source_name="", box=True):
        """Plot the closure phase between the 3 specified baselines. (phase = a + b - c)

        Parameters
        ==========
        a : corr_prod_id
            The id of the first baseline.
            default: (1,2,'VV')
        b : corr_prod_id
            The id of the second baseline.
            default: (2,3,'VV')
        c : corr_prod_id
            The id of the third baseline. Note that this is subtracted from the first two (i.e. vector in opposition to the first two)
            default: (1,3,'VV')
        start_channel : integer
            default: 100
        stop_channel : integer
            default: 400
        end_time: integer
            default: -120
        swap: boolean
            By default the produced boxplot will be averaged over time. If swap is set then data is averaged over frequency.
            default: False
        new_figure: boolean
            If set to False then the plot will be drawn in the current figure instead of a new one being created.
            default: True
        """
        if new_figure:
            pl.figure()
        p12 = np.array(self.select_data(product=a, dtype='phase',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        p23 = np.array(self.select_data(product=b, dtype='phase',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        p13 = np.array(self.select_data(product=c, dtype='phase',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        s = p12 + p23 - p13
        s = self._angle_wrap(s)
        s = s * (180/np.pi)
        if swap: s = s.swapaxes(1,0)
        if not box:
            pl.plot(s.mean(axis=0))
            pl.plot(s.min(axis=0))
            pl.plot(s.max(axis=0))
        else:
            pl.boxplot(s)
        pl.title(source_name + " Phase Closure ("+str(a) + "," + str(b) + "," + str(c) + ")")
        pl.xlabel("Time [s]" if swap else "Frequency [" + ("MHz" if len(self.receiver.center_freqs_mhz) > 0 else "channel") + "]")
        pl.ylabel("Phase [deg]")
        pl.ylim(-180,180)
        if len(self.receiver.center_freqs_mhz) > 0 and not swap:
            pl.xticks(range(0,s.shape[1],25), [int(self.receiver.center_freqs_mhz[start_channel+f]) for f in range(0,s.shape[1],25)])
            pl.subplots_adjust(bottom=0.15)
        else:
            pl.xticks(range(0,s.shape[1],4),rotation=90)
        if new_figure:
            f = pl.gcf()
            f.show()
            pl.draw()

    def plot_amp_closure(self, pol='VV', start_channel=100, stop_channel=400, end_time=-120, swap=False, new_figure=True, source_name="", box=True):
        """Plot the closure amplitude around the first 4 antennas. amp = (|A1A2| * |A3A4|) / (|A1A3| * |A2A4|)

        Parameters
        ==========
        pol : string
            The polarisation to plot. ['HH','VV']
            default: 'VV'
        start_channel : integer
            default: 100
        stop_channel : integer
            default: 400
        end_time: integer
            default: -120
        swap: boolean
            By default the produced boxplot will be averaged over time. If swap is set then data is averaged over frequency.
            default: False
        """
        if new_figure:
            pl.figure()
        a12 = np.array(self.select_data(product=(1,2,pol), dtype='mag',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        a34 = np.array(self.select_data(product=(3,4,pol), dtype='mag',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        a13 = np.array(self.select_data(product=(1,3,pol), dtype='mag',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        a24 = np.array(self.select_data(product=(2,4,pol), dtype='mag',end_time=end_time, start_channel=start_channel, stop_channel=stop_channel))
        am = (a12 * a34) / (a13 * a24)
        if swap: am = am.swapaxes(1,0)
        if not box:
            pl.plot(am.mean(axis=0))
            pl.plot(am.min(axis=0))
            pl.plot(am.max(axis=0))
        else:
            pl.boxplot(am)
        pl.title(source_name + " Amplitude Closure (%s)" % (pol))
        pl.xlabel("Time [s]" if swap else "Frequency [" + ("MHz" if len(self.receiver.center_freqs_mhz) > 0 else "channel") + "]")
        pl.ylabel("Amplitude")
        if len(self.receiver.center_freqs_mhz) > 0 and not swap:
            pl.xticks(range(0,am.shape[1],25), [int(self.receiver.center_freqs_mhz[start_channel+f]) for f in range(0,am.shape[1],25)])
            pl.subplots_adjust(bottom=0.15)
        else:
            pl.xticks(range(0,am.shape[1],4),rotation=90)
        if new_figure:
            f = pl.gcf()
            f.show()
            pl.draw()

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
        self._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

    def plot_spectrum(self, type='mag', products=None, start_channel=0, stop_channel=-1, scale='log', average=1, include_flags=False):
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
            e.g. products = [9, (2,'VV'), (2,2,1)] are actually all product id 9
        start_channel : integer
            default: 0
        stop_channel : integer
            default: -1
        average : integer
            The number of dumps to average over (from most recent dump backwards)
            default: None
        include_flags : boolean
            If True, and flag information is available, show flag information on the plot
        Returns
        -------
        ap : AnimatablePlot
        """
        if products is None: products = self.default_products
        pl.figure()
        pl.xlabel("Frequency [" + ("MHz" if len(self.receiver.center_freqs_mhz) > 0 else "channel") + "]")
        f = pl.gcf()
        ax = f.gca()
        avg = ""
        if average > 1: avg = " (" + str(average) + " dump average.)"
        if type == 'phase':
            pl.ylabel("Phase [rad]")
            ax.set_ylim(ymin=-np.pi,ymax=np.pi)
        else:
            pl.ylabel("Power [arb units]")
            pl.yscale(scale)
        if len(self.receiver.center_freqs_mhz) > 0:
            freq_range = self.receiver.center_freqs_mhz[start_channel:stop_channel]
            pl.xticks(range(0,len(freq_range),25), [int(self.receiver.center_freqs_mhz[start_channel+fc]) for fc in range(0,len(freq_range),25)])
        s = [[0]]
        for i,product in enumerate(products):
            if s == [[0]]:
                s = self.select_data(product=product, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
            if include_flags:
                (data, flags) = self.select_data(product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0, include_flags=True)
                pl.plot(data, label=self.cpref.id_to_real_str(product, short=True))
                for j,flag in enumerate(flags):
                    if flag > 0: pl.axvspan(j,j+1,facecolor='r',alpha=0.5)
            else:
                pl.plot(self.select_data(product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0), label=self.cpref.id_to_real_str(product, short=True))
            if i == 0:
                ap = AnimatablePlot(f, self.select_data, product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0)
            else:
                ap.add_update_function(self.select_data, product=product, dtype=type, start_channel=start_channel, stop_channel=stop_channel, end_time=-average, avg_axis=0)
        if type == 'phase': pl.title("Phase Spectrum at " + time.ctime(s[0][0]) + avg)
        else: pl.title("Power Spectrum at " + time.ctime(s[0][0]) + avg)
        pl.legend(loc=0)
        f.show()
        pl.draw()
        self._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

class KATData(object):
    """A class to encapsulate various KAT data handling functions.

    Essentially this class provides a mechanism for retrieving and plotting raw data directly from the dbe, as well
    as interacting with and plotting of the signal display data stream.

    Parameters
    ----------
    dbe : KATClient
        A reference to an KATClient object connected to the KAT dbe proxy. This is used for making data calls to the dbe.
    """
    def __init__(self, dbe=None):
        self.dbe = dbe
        self.sd = None

    def find_dbe(self, dbe):
        """Attempts to find an active connection to the dbe proxy in the current session.

        Parameters
        ----------
        dbe : string
            The name of the dbe proxy to find. Typically dbe / dbe7
        """
        print "Checking local environment for active dbe proxy named %s" % dbe
        try:
            import IPython
        except ImportError:
            print "Proxy detection only works for IPython sessions."
            return

        # Set IPython shell reference
        try:
            # IPython 0.11 and above
            ip_shell = get_ipython()
        except NameError:
            # IPython 0.10 and lower
            ip_shell = __builtins__.get('__IPYTHON__')
        
        try:
            active_hosts = dict([(k, v) for k, v in ip_shell.user_ns['katuilib'].utility._hosts.iteritems() if not v._disconnect])
            if len(active_hosts) > 0:
                k = active_hosts[max(active_hosts)]
                try:
                    self.dbe = getattr(k,dbe)
                except AttributeError:
                    print "Active katuilib seesion found, but no dbe proxy available."
        except (KeyError, AttributeError):
            print "No active katuilib session found."

    def register_dbe(self, dbe):
        self.dbe = dbe

    def start_spead_receiver(self, port=7149, capacity=0.2, notifyqueue=None, store2=False):
        """Starts a SPEAD based signal display data receiver on the specified port.
        
        Parameters
        ----------
        port : integer
            default: 7149
        capacity : float
            The fraction of total physical memory to use for data storage on this machine.
            default: 0.2
        store2 : boolean
            Use the updated signal display store version 2
        """
        if self.dbe is None:
            self.find_dbe("dbe7")

        if self.dbe is None:
            print "No dbe proxy available. Make sure that signal display data is manually directed to this host using the add_sdisp_ip command on an active dbe proxy."

        st = SignalDisplayStore2(capacity=capacity) if store2 else SignalDisplayStore(capacity=capacity)
        r = SpeadSDReceiver(port,st,notifyqueue)
        r.setDaemon(True)
        r.start()
        self.sd = DataHandler(self.dbe, receiver=r, store=st)

    def start_direct_spead_receiver(self, port=7148, capacity=0.2, store2=False):
        """Starts a SPEAD signal display receiver to handle data directly from the correlator.

        Parameters
        ----------
        port : integer
            default: 7149
        capacity : float
            The fraction of total physical memory to use for data storage on this machine.
            default: 0.2
        store2 : boolean
            Use the updated signal display store version 2

        """
        st = SignalDisplayStore2(capacity=capacity) if store2 else SignalDisplayStore(capacity=capacity)
        r = SpeadSDReceiver(port, st, direct=True)
        r.setDaemon(True)
        r.start()
        self.sd = DataHandler(dbe=None, receiver=r, store=st)

    def load_k7_data(self, filename, rows=None, startrow=None):
        """Load k7 data (HDF5 v2) from the specified file and use this to populate a signal display storage object.
        The new data handler is available as .sd_hist

        Parameters
        ==========
        filename : string
            The fully qualified path to the HDF5 file in question
        """
        st = SignalDisplayStore()
        st.pc_load_letter(filename, rows=rows, startrow=startrow)
        r = NullReceiver(st)
        r.cpref = st.cpref
        r.channels = st.n_chans
        self.sd_hist = DataHandler(dbe=None, receiver=r, store=st)
        print "Signal display data available as .sd_hist"

    def load_ff_data(self, filename, cscan=None, scan=None, start=None, end=None):
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
        st.load(filename, cscan=cscan, scan=scan, start=start, end=end)
        r = NullReceiver(st)
        r.cpref = st.cpref
        r.channels = st.n_chans
        self.sd_hist = DataHandler(dbe=None, receiver=r, store=st)
        print "Historical signal display data available as .sd_hist"

    def start_ff_receiver(self, port=7006, capacity=0.2):
        """Connect the data handler object to the signal display data stream and create a new DataHandler service
        for the incoming data.

        This command instructs k7writer to send signal display data to the current host (in addition to all other listeners).
        A new DataHandler is created to receive and interpret the incoming signal display frames.

        Once this command has executed successfully the signal display data will be available under the sd name.

        Parameters
        ----------
        port : integer
            default: 7006
        capacity : float
            The fraction of total physical memory to use for data storage on this machine.
            default: 0.2

        
        Example
        -------
        Start the signal display receiver:
        >>> kat.dh.start_ff_receiver()
        Check that the number of packets received increases over time by running a few times:
        >>> kat.dh.sd.receiver.stats()
        Make a waterfall plot of the data:
        >>> kat.dh.sd.plot_waterfall()
        Animate the last plot:
        >>> _.animate()
        """
        logger.info("Starting signal display capture")

        if self.dbe is None:
            self.find_dbe("dbe")

        if self.dbe is None:
            print "No dbe proxy available. Make sure that signal display data is manually directed to this host using the add_sdisp_ip command on an active dbe proxy."

        st = SignalDisplayStore(capacity=capacity)
        r = SignalDisplayReceiver(port, st)
        r.setDaemon(True)
        r.start()
        self.sd = DataHandler(self.dbe, receiver=r, store=st)

    def stop_sdisp(self):
        """Stop the signal display data receiving thread.
        """
        if self.sd is not None:
            self.sd.stop()

    def get_last_dump(self, block=False):
        """Pull the last complete correlator dump from k7writer."""
        st = time.time()
        result = None
        ts = 0
        data = None
        if self.dbe is not None:
            while block or result is None:
                result = self.dbe.req.k7w_get_last_dump()
                if result.succeeded:
                    try:
                        ts = int(result.messages[1].arguments[0]) / 1000.0
                        data = np.frombuffer(result.messages[2].arguments[0], dtype=np.float32).reshape((512,12,2)).view(np.complex64).squeeze()
                    except IndexError:
                        logger.error("Command returned invalid data. Please try again.")
                    return (ts,data)
                else:
                    result = None
                    if time.time() > st + block:
                        logger.error("Failed to retrieve data within the blocking interval.")
                        break
                    time.sleep(1)
        return (ts,data)

    def get_snapshot(self, dtype='adc', input='0x'):
        """Get snapshot data from the dbe and interpret according to type.

        Parameters
        ----------
        dtype : string
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
        rettype = dtype
        if dtype == 'quanti': rettype = 'quant'
        if self.dbe is not None:
            try:
                raw = unpack('>8192b',self.dbe.req.snap_shot(rettype,input).messages[0].arguments[1])
            except AttributeError:
                logger.error("Current dbe device does not support snap-shot command.")
            except IndexError:
                logger.error("snap-shot command failed.")
        else:
            logger.error("No dbe device known. Unable to capture snapshot.")
        if dtype == 'quant' or dtype == 'quanti':
            rawn = np.array(raw,dtype=np.float32)
            raw = rawn.view(dtype=np.complex64)
            if dtype == 'quant': return [x.real for x in raw]
            else: [x.imag for x in raw]
        return raw

    def get_histogram_data(self, dtype='adc', input='0x'):
        """Get ADC snapshot data and produce a histogram of the data.
        """
        data = self.get_snapshot(dtype=dtype, input=input)
        n, bins = np.histogram(data, bins=256, range=(-127,128), new=True)
        if len(n) == len(bins): bins.append(bins[-1])
         # fix for older numpy versions that did not return a rightmost bin edge
        return n,bins

    def plot_hist(self, dtype='adc', input='0x'):
        """Plot a histogram of the ADC sampling bins for the specified input.
        This plots a histogram of an 8192 sample snapshot of raw signed 8 bit ADC data.

        Parameters
        ----------
        dtype : string
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
        pl.title("Histogram (" + dtype + ") for input " + input)
        pl.xlabel("Bins")
        pl.ylabel("Count")
        f = pl.gcf()
        ax = f.gca()
        n, bins = self.get_histogram_data(dtype=dtype, input=input)
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
        ap = AnimatablePlot(f, self.get_histogram_data, dtype=dtype, input=input)
        if self.sd is not None: self.sd._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

    def plot_snapshot(self, dtype='adc', input='0x'):
        """Plot a snapshot of the specified type for the specified dbe input.
        A snapshot is basically a katcp dump of a particular block of dbe memory. At the moment a snapshot of the current ADC
        sampling and of the post quantisation data is available.

        Parameters
        ----------
        dtype : string
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
        pl.title("Snapshot (" + dtype + ") " + input)
        pl.xlabel((dtype == 'adc' and "Time" or 'Channel (groups of 512)'))
        pl.ylabel("Voltage")
        ax = pl.gca()
        raw = self.get_snapshot(dtype=dtype, input=input)
        pl.plot(raw)
        if dtype == 'quant' or dtype == 'quanti':
            for x in range(0,4096,512):
                pl.axvline(x,color='green', lw=1, alpha=0.5)
            pl.xticks(range(0,4096,256),[x % 512 for x in range(0,4096,256)])
        f = pl.gcf()
        f.show()
        pl.draw()
        ap = AnimatablePlot(f, self.get_snapshot, dtype=dtype, input=input)
        self._add_plot(sys._getframe().f_code.co_name, ap)
        if self.sd is not None: self.sd._add_plot(sys._getframe().f_code.co_name, ap)
        return ap

    def plot_snapshots(self, dtype='adc', interval=1):
        """Plot snapshots of the specified type for each of the four input channels available
        in the KAT pocket correlator.

        Parameters
        ----------
        dtype : string
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
        pa.add_plot('snap 0x',self.plot_snapshot(dtype=dtype, input='0x'))
        pa.add_plot('snap 0y',self.plot_snapshot(dtype=dtype, input='0y'))
        pa.add_plot('snap 1x',self.plot_snapshot(dtype=dtype, input='1x'))
        pa.add_plot('snap 1y',self.plot_snapshot(dtype=dtype, input='1y'))
        return pa


def external_ip(preferred_prefixes=('eth', 'en')):
    """Return the external IPv4 address of this machine.

    Attempts to use netifaces module if available, otherwise
    falls back to socket.

    Parameters
    ----------
    preferred_prefixes : tuple
        A tuple of string prefixes for network interfaces to match. e.g. ('eth','en') matches ethX and enX
        with a preference for lowest number first (eth0 over eth3).

    Returns
    -------
    ip : str or None
        IPv4 address string (dotted quad). Returns None if
        ip address cannot be guessed.
    """
    if netifaces is None:
        ips = [socket.gethostbyname(socket.gethostname())]
    else:
        preferred_ips = []
        other_ips = []
        for iface in netifaces.interfaces():
            for addr in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                if 'addr' in addr:
                    for prefix in preferred_prefixes:
                        if iface.startswith(prefix): preferred_ips.append(addr['addr'])
                    other_ips.append(addr['addr'])
                     # will duplicate those in preferred_ips but this doesn't matter as we only
                     # use other_ips if preferred is empty.
        ips = preferred_ips + other_ips
    if ips:
        return ips[0]
    else:
        return None

def parse_timeseries_mask(maskstr,spectrum_width):
    """
    maskstr='500' flags channel 500
    maskstr='..200' flags the first 200 channels
    maskstr='-200..' flags the last 200 channels
    maskstr='300..350' flags channels 300 to 350
    maskstr='..200,300..350,500,-200..' flags the first and last 200 channels, as well as channels 300 to 350, and channel 500
    """
    spectrum_flagmask=np.ones([spectrum_width],dtype=np.float32)
    spectrum_flag0=[]
    spectrum_flag1=[]
    if (spectrum_width>=1):
        try:
            args=maskstr.split(',')
            for c in range(len(args)):
                rng=args[c].split('..');
                if (len(rng)==1):
                    if (args[c]!=''):
                        chan=int(args[c])
                        spectrum_flag0.append(chan)
                        spectrum_flag1.append(chan+1)
                        spectrum_flagmask[chan]=0
                elif (len(rng)==2):
                    if (rng[0]==''):
                        chan0=0
                    else:
                        chan0=int(rng[0])
                    if (rng[1]==''):
                        chan1=spectrum_width-1
                    else:
                        chan1=int(rng[1])
                    if (chan0<0):
                        chan0=spectrum_width+chan0
                        if (chan0<0):
                            chan0=0;
                    elif (chan0>=spectrum_width):
                        chan0=spectrum_width-1
                    if (chan1<0):
                        chan1=spectrum_width+chan1
                        if (chan1<0):
                            chan1=0;
                    elif (chan1>=spectrum_width):
                        chan1=spectrum_width-1;
                    if (chan0>chan1):
                        tmp=chan0
                        chan0=chan1
                        chan1=tmp
                    spectrum_flag0.append(chan0)
                    spectrum_flag1.append(chan1)
                    spectrum_flagmask[chan0:(chan1+1)]=0
        except Exception, e:#clears flags if exception occurred during parsing
            spectrum_flagmask=np.ones([spectrum_width],dtype=np.float32)
            spectrum_flag0=[]
            spectrum_flag1=[]
            pass
    timeseriesmaskind=np.nonzero(spectrum_flagmask)[0]
    weightedmask=spectrum_flagmask/len(timeseriesmaskind)
    return timeseriesmaskind,weightedmask,spectrum_flag0,spectrum_flag1


def set_bls(bls_ordering):
    """
    collectionproducts contains product indices of: autohhvv,autohh,autovv,autohv,crosshhvv,crosshh,crossvv,crosshv
    """
    auto=[]
    autohh=[]
    autovv=[]
    autohv=[]
    cross=[]
    crosshh=[]
    crossvv=[]
    crosshv=[]
    for ibls,bls in enumerate(bls_ordering):
        if (bls[0][:-1]==bls[1][:-1]):#auto
            if (bls[0][-1]==bls[1][-1]):#autohh or autovv
                auto.append(ibls)
                if (bls[0][-1]=='h'):
                    autohh.append(ibls)
                else:
                    autovv.append(ibls)                        
            else:#autohv or vh 
                autohv.append(ibls)
        else:#cross
            if (bls[0][-1]==bls[1][-1]):#crosshh or crossvv
                cross.append(ibls)
                if (bls[0][-1]=='h'):
                    crosshh.append(ibls)
                else:
                    crossvv.append(ibls)                        
            else:#crosshv or vh 
                crosshv.append(ibls)
    collectionproducts=[auto,autohh,autovv,autohv,cross,crosshh,crossvv,crosshv]
    percrunavg=[np.zeros(len(bls),dtype='float') for bls in collectionproducts] #clears running percentile average
    return collectionproducts,percrunavg
    
