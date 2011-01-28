#!/usr/bin/python

# Capture utility for a relatively generic packetised correlator data output stream.

# The script performs two primary roles:
#
# Storage of stream data on disk in hdf5 format. This includes placing meta data into the file as attributes.
#
# Regeneration of a SPEAD stream suitable for us in the online signal displays. At the moment this is basically
# just an aggregate of the incoming streams from the multiple x engines scaled with n_accumulations (if set)

import numpy as np
import spead
import h5py
import sys
import time
import optparse
import threading
import Queue
from katcp import DeviceServer, Sensor, Message
from katcp.kattypes import request, return_reply, Str

hdf5_version = "2.0"
 # initial version describing indicating compatibility with our HDF5v2 spec. Minor revision may be incremented by augment at a later stage.

mapping = {'xeng_raw':'/Data/correlator_data',
           'timestamp':'/Data/raw_timestamps'}
 # maps SPEAD element names to HDF5 paths
timestamps = '/Data/timestamps'
correlator_map = '/MetaData/Configuration/Correlator/'
observation_map = '/MetaData/Configuration/Observation/'
 # default path for things that are not mentioned above
config_sensors = ['script_arguments','script_description','script_experiment_id','script_name','script_nd_params','script_observer','script_rf_params','script_starttime','script_status']
 # sensors to pull from the cfg katcp device

def small_build(system):
    print "Creating KAT connections..."
    katconfig = katuilib.conf.KatuilibConfig(system)
    cfg_config = katconfig.clients['cfg']
    cfg = katuilib.utility.build_device(cfg_config.name, cfg_config.ip, cfg_config.port)
    count=0
    while not cfg.is_connected() and count < 6:
        count+=1
        print "Waiting for cfg device to become available... (wait %i/5)" % count
        time.sleep(2)
        if not cfg.is_connected():
            print "Failed to connect to cfg device (ip: %s, port: %i)\n" % (cfg_config.ip, cfg_config.port)
            sys.exit(0)
        return cfg

def parse_opts(argv):
    parser = optparse.OptionParser()
    parser.add_option('--include_cfg', action='store_true', default=False, help='pull configuration information via katcp from the configuration server')
    parser.add_option('--ip', default='192.168.4.20', help='signal display ip')
    parser.add_option('--data-port', default=7148, type=int, help='port to receive data on')
    parser.add_option('--acc-scale', action='store_true', default=False, help='scale by the reported number of accumulations per dump')
    parser.add_option("-s", "--system", default="systems/local.conf", help="system configuration file to use. [default=%default]")
    parser.add_option('-p', '--port', dest='port', type=long, default=2040, metavar='N', help='attach to port N (default=2040)')
    parser.add_option('-a', '--host', dest='host', type="string", default="", metavar='HOST', help='listen to HOST (default="" - all hosts)')
    return parser.parse_args(argv)

class k7Capture(threading.Thread):
    def __init__(self, data_port, acc_scale, sd_ip, cfg, pkt_sensor, status_sensor):
        self.data_port = data_port
        self.acc_scale = acc_scale
        self.sd_ip = sd_ip
        self.cfg = cfg
        self._current_hdf5 = None
        self.pkt_sensor = pkt_sensor
        self.status_sensor = status_sensor
        self.status_sensor.set_value("init")
        self.fname = "None"
        threading.Thread.__init__(self)

    def remap(self, name):
        return name in mapping and mapping[name] or correlator_map + name

    def write_sensor(location, name, value):
        """Write a sensor value directly into the current hdf5 at the specified locations.
           Note that this will create a new HDF5 file if one does not already exist..."""
        f = (self._current_hdf5 is None and self.init_file() or self._current_hdf5)

    def init_file(self):
        self.fname = str(int(time.time())) + ".pc.h5"
        f = h5py.File(self.fname, mode="w")
        f['/'].attrs['version_number'] = hdf5_version
        f['/'].create_group('Data')
        f['/'].create_group('MetaData')
        f['/'].create_group('MetaData/Configuration')
        f['/'].create_group('MetaData/Observation')
        f['/'].create_group('MetaData/Configuration/Correlator')
        f['/'].create_group('Markup')
        f['/Markup'].create_dataset('labels', [], maxshape=None, dtype=h5py.new_vlen(str))
         # create a label storage of variable length strings
        self._current_hdf5 = f
        return f

    def run(self):
        print 'Initalising SPEAD transports...'
        print "Data reception on port", self.data_port
        rx = spead.TransportUDPrx(self.data_port, pkt_count=1024, buffer_size=51200000)
        print "Sending Signal Display data to", self.sd_ip
        tx_sd = spead.Transmitter(spead.TransportUDPtx(self.sd_ip, 7149))
        ig = spead.ItemGroup()
        ig_sd = spead.ItemGroup()
        idx = 0
        f = None
        self.status_sensor.set_value("idle")
        dump_size = 0
        datasets = {}
        datasets_index = {}
        meta_required = set(['n_chans','n_bls','n_stokes'])
         # we need these bits of meta data before being able to assemble and transmit signal display data
        meta_desired = ['n_accs']
         # if we find these, then what hey :)
        meta = {}
        sd_frame = None
        sd_slots = None
        sd_timestamp = None
        for heap in spead.iterheaps(rx):
            if idx == 0:
                f = (self._current_hdf5 is None and self.init_file() or self._current_hdf5)
                self.status_sensor.set_value("capturing")
            ig.update(heap)
            for name in ig.keys():
                item = ig.get_item(name)
                if not item._changed and datasets.has_key(name): continue
                 # the item is not marked as changed, and we have a record for it
                if name in meta_desired:
                    meta[name] = ig[name]
                if name in meta_required:
                    meta[name] = ig[name]
                    meta_required.remove(name)
                    if not meta_required:
                        sd_frame = np.zeros((meta['n_chans'],meta['n_bls'],meta['n_stokes'],2),dtype=np.int32)
                        print "Initialised sd frame to shape",sd_frame.shape
                        meta_required = set(['n_chans','n_bls','n_stokes'])
                        sd_slots = None
                if not name in datasets:
                 # check to see if we have encountered this type before
                    shape = ig[name].shape if item.shape == -1 else item.shape
                    dtype = np.dtype(type(ig[name])) if shape == [] else item.dtype
                    if dtype is None:
                        dtype = ig[name].dtype
                     # if we can't get a dtype from the descriptor try and get one from the value
                    print "Creating dataset for name:",name,", shape:",shape,", dtype:",dtype
                    new_shape = list(shape)
                    if new_shape == [1]:
                        new_shape = []
                    f.create_dataset(self.remap(name),[1] + new_shape, maxshape=[None] + new_shape, dtype=dtype)
                    dump_size += np.multiply.reduce(shape) * dtype.itemsize
                    datasets[name] = f[self.remap(name)]
                    datasets_index[name] = 0
                    if name == 'timestamp':
                        f.create_dataset(timestamps,[1] + new_shape, maxshape=[None] + new_shape, dtype=np.float64)
                    if not item._changed:
                        continue
                     # if we built from and empty descriptor
                else:
                    print "Adding",name,"to dataset. New size is",datasets_index[name]+1
                    f[self.remap(name)].resize(datasets_index[name]+1, axis=0)
                    if name == 'timestamp':
                        f[timestamps].resize(datasets_index[name]+1, axis=0)
                if sd_frame is not None and name.startswith("xeng_raw"):
                    sd_timestamp = ig['sync_time'] + (ig['timestamp'] / ig['scale_factor_timestamp'])
                    print "SD Timestamp:", sd_timestamp," (",time.ctime(sd_timestamp),")"
                    if sd_slots is None:
                        ig_sd = spead.ItemGroup()
                         # reinit the group to force meta data resend
                        sd_frame.dtype = np.dtype(np.float32) if self.acc_scale else ig[name].dtype
                         # make sure we have the right dtype for the sd data
                        sd_slots = np.zeros(meta['n_chans']/ig[name].shape[0])
                        n_xeng = len(sd_slots)
                         # this is the first time we know how many x engines there are
                        f[correlator_map].attrs['n_xeng'] = n_xeng
                        ig_sd.add_item(name=('sd_data'),id=(0x3501), description="Combined raw data from all x engines.", ndarray=(sd_frame.dtype,sd_frame.shape))
                        ig_sd.add_item(name=('sd_timestamp'), id=0x3502, description='Timestamp of this sd frame in centiseconds since epoch (40 bit limitation).', shape=[], fmt=spead.mkfmt(('u',spead.ADDRSIZE)))
                        t_it = ig_sd.get_item('sd_data')
                        print "Added SD frame dtype",t_it.dtype,"and shape",t_it.shape,". Metadata descriptors sent."
                        tx_sd.send_heap(ig_sd.get_heap())
                    print "Sending signal display frame with timestamp %i. %s. Max: %i, Mean: %i" % (sd_timestamp, "Unscaled" if not self.acc_scale else "Scaled by %i" % ((meta['n_accs'] if meta.has_key('n_accs') else 1)), np.max(ig[name]),np.mean(ig[name]))
                    ig_sd['sd_data'] = ig[name] if not self.acc_scale else (ig[name] / float(meta['n_accs'] if meta.has_key('n_accs') else 1)).astype(np.float32)
                    ig_sd['sd_timestamp'] = int(sd_timestamp * 100)
                    tx_sd.send_heap(ig_sd.get_heap())
                f[self.remap(name)][datasets_index[name]] = ig[name]
                if name == 'timestamp':
                    try:
                        f[timestamps][datasets_index[name]] = ig['sync_time'] + (ig['timestamp'] / ig['scale_factor_timestamp'])
                         # insert derived timestamps
                    except KeyError:
                        f[timestamps][datasets_index[name]] = 0
                datasets_index[name] += 1
                item._changed = False
                  # we have dealt with this item so continue...
            if idx==0 and self.cfg is not None:
                # add config store metadata after receiving first frame. This should ensure that the values pulled are fresh.
                for s in config_sensors:
                    f[observation_map].attrs[s] = kat.cfg.sensor.__getattribute__(s).get_value()
                print "Added initial observation sensor values...\n"
            idx+=1
            self.pkt_sensor.set_value(idx)
        for (name,idx) in datasets_index.iteritems():
            if idx == 1:
                print "Repacking dataset",name,"as an attribute as it is singular."
                f[correlator_map].attrs[name] = f[self.remap(name)].value[0]
                del f[self.remap(name)]
        print "Capture complete."
        self.status_sensor.set_value("complete")
        f.flush()
        f.close()
        self._current_hdf5 = None

class CaptureDeviceServer(DeviceServer):

    VERSION_INFO = ("k7-capture", 0, 1)
    BUILD_INFO = ("k7-capture", 0, 1, "rc1")

    def __init__(self, *args, **kwargs):
        self.rec_thread = None
        self.current_file = "None"
        self._my_sensors = {}
        self._my_sensors["capture-active"] = Sensor(Sensor.INTEGER, "capture_active", "Is there a currently active capture thread.","",default=0, params = [0,1])
        self._my_sensors["packets-captured"] = Sensor(Sensor.INTEGER, "packets_captured", "The number of packets captured so far by the current session.","",default=0, params=[0,2**63])
        self._my_sensors["status"] = Sensor(Sensor.STRING, "status", "The current status of the capture thread.","","")
        self._my_sensors["label"] = Sensor(Sensor.STRING, "label", "The label applied to the data as currently captured.","","")
        self._my_sensors["script-name"] = Sensor(Sensor.STRING, "script-name", "Current script name", "")
        self._my_sensors["script-experiment-id"] = Sensor(Sensor.STRING, "script-experiment-id", "Current experiment id", "")
        self._my_sensors["script-observer"] = Sensor(Sensor.STRING, "script-observer", "Current experiment observer", "")
        self._my_sensors["script-description"] = Sensor(Sensor.STRING, "script-description", "Current experiment description", "")
        self._my_sensors["script-rf-params"] = Sensor(Sensor.STRING, "script-rf-params", "Current experiment RF parameters", "")
        self._my_sensors["script-nd-params"] = Sensor(Sensor.STRING, "script-nd-params", "Current experiment Noise Diode parameters", "")
        self._my_sensors["script-arguments"] = Sensor(Sensor.STRING, "script-arguments", "Options and parameters of script - from sys.argv", "")
        self._my_sensors["script-status"] = Sensor(Sensor.STRING, "script-status", "Current status reported by running script", "idle")
        self._my_sensors["script-starttime"] = Sensor(Sensor.STRING, "script-starttime", "Start time of current script", "")
        self._my_sensors["script-endtime"] = Sensor(Sensor.STRING, "script-endtime", "End time of current script", "")

        super(CaptureDeviceServer, self).__init__(*args, **kwargs)

    def setup_sensors(self):
        for sensor in self._my_sensors:
            self.add_sensor(self._my_sensors[sensor])
        self._my_sensors["label"].set_value("no_thread")

    def request_capture_start(self, sock, msg):
        """Spawns a new capture thread that waits for a SPEAD start stream packet."""
        self.rec_thread = k7Capture(opts.data_port, opts.acc_scale, opts.ip, cfg, self._my_sensors["packets-captured"], self._my_sensors["status"])
        self.rec_thread.setDaemon(True)
        self.rec_thread.start()
        self._my_sensors["capture-active"].set_value(1)
        return Message.reply(msg.name, "ok", "Capture started at %s" % time.ctime())

    @request(Str(), Str())
    @return_reply(Str())
    def request_set_script_param(self, sock, sensor_string, value_string):
        """Set the desired script parameter.

        Parameters
        ----------
        sensor_string : str
            The script parameter to be set. [script-name, script-experiment-id, script-observer, script-description, script-rf-params, script-nd-params, script-arguments, script-status, script-starttime, script-endtime]
        value_string : str
            A string containing the value to be set
            
        Returns
        -------
        success : {'ok', 'fail'}
            Whether setting the sensor succeeded.
        sensor_string : str
            Name of sensor that was set
        value_string : str
            A string containing the sensor value it was set to
            
        Examples
        --------
        ?set_script_param script-name Test
        !set_script_param ok script-name
        
        """
        try:
            self._my_sensors[sensor_string].set_value(value_string)
            #self._activity_logger.info("Set script parameter %s=%s" % (sensor_string,value_string))
        except ValueError, e:
            return ("fail", "Could not parse sensor name or value string '%s=%s': %s" % (sensor_string, value_string, e))
        return ("ok", "%s=%s" % (sensor_string, value_string))

    @request(Str())
    @return_reply(Str())
    def request_set_label(self, sock, label):
        """Set the current scan label to the supplied value."""
        self._label.set_value(label)
        return ("ok","Label set to %s" % label)

    def request_get_current_file(self, sock, msg):
        """Return the name of the current (or most recent) capture file."""
        if self.rec_thread is not None: self.current_file = self.rec_thread.fname
        return Message.reply(msg.name, "ok", self.current_file)

    def request_capture_stop(self, sock, msg):
        """Attempts to gracefully shut down current capture thread by sending a SPEAD stop packet to local receiver."""
        self.current_file = self.rec_thread.fname
         # preserve current file before shutting thread for use in get_current_file
        tx = spead.Transmitter(spead.TransportUDPtx('localhost',7148))
        tx.end()
        self.rec_thread.join()
        self.rec_thread = None
        self._my_sensors["capture-active"].set_value(0)
        return Message.reply(msg.name, "ok", "Capture stoppped at %s" % time.ctime())

if __name__ == '__main__':
    opts, args = parse_opts(sys.argv)
    cfg = None
    if opts.include_cfg:
        try:
            import katuilib
        except ImportError:
            print "katulib is not available on this host. please run script using --include_cfg=false"
            sys.exit(0)
        cfg = small_build(opts.system)

    restart_queue = Queue.Queue()
    server = CaptureDeviceServer(opts.host, opts.port)
    server.set_restart_queue(restart_queue)
    server.start()
    print "Started k7-capture server."
    try:
        while True:
            try:
                device = restart_queue.get(timeout=0.5)
            except Queue.Empty:
                device = None
            if device is not None:
                print "Stopping ..."
                device.stop()
                device.join()
                print "Restarting ..."
                device.start()
                print "Started."
    except KeyboardInterrupt:
        print "Shutting down ..."
        server.stop()
        server.join()

#    while True:
#        rec_thread = k7Capture(opts.data_port, opts.acc_scale, opts.ip, cfg)
#        rec_thread.setDaemon(True)
#        rec_thread.start()
#        while rec_thread.isAlive():
#            print "."
#            time.sleep(1)
#        #fname = receive(opts.data_port, opts.acc_scale, opts.ip, cfg)
#        print "Capture complete. Data recored to file."



