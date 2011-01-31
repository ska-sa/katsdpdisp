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

def remap(name):
    return name in mapping and mapping[name] or correlator_map + name

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
    return parser.parse_args(argv)

def receive(data_port, acc_scale, sd_ip, cfg):
    print 'Initalising SPEAD transports...'
    print "Data reception on port", data_port
    rx = spead.TransportUDPrx(data_port, pkt_count=1024, buffer_size=51200000)
    print "Sending Signal Display data to", sd_ip
    tx_sd = spead.Transmitter(spead.TransportUDPtx(sd_ip, 7149))
    ig = spead.ItemGroup()
    ig_sd = spead.ItemGroup()
    fname = str(int(time.time())) + ".pc.h5"
    f = h5py.File(fname, mode="w")
    f['/'].attrs['version_number'] = hdf5_version
    f['/'].create_group('Data')
    f['/'].create_group('MetaData')
    f['/'].create_group('MetaData/Configuration')
    f['/'].create_group('MetaData/Configuration/Correlator')
    idx = 0
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
                f.create_dataset(remap(name),[1] + new_shape, maxshape=[None] + new_shape, dtype=dtype)
                dump_size += np.multiply.reduce(shape) * dtype.itemsize
                datasets[name] = f[remap(name)]
                datasets_index[name] = 0
                if name == 'timestamp':
                    f.create_dataset(timestamps,[1] + new_shape, maxshape=[None] + new_shape, dtype=np.float64)
                if not item._changed:
                    continue
                 # if we built from and empty descriptor
            else:
                print "Adding",name,"to dataset. New size is",datasets_index[name]+1
                f[remap(name)].resize(datasets_index[name]+1, axis=0)
                if name == 'timestamp':
                    f[timestamps].resize(datasets_index[name]+1,axis=0)

            if sd_frame is not None and name.startswith("xeng_raw"):
                sd_timestamp = ig['sync_time'] + (ig['timestamp'] / ig['scale_factor_timestamp'])
                print "SD Timestamp:", sd_timestamp," (",time.ctime(sd_timestamp),")"
                if sd_slots is None:
                    ig_sd = spead.ItemGroup()
                     # reinit the group to force meta data resend
                    sd_frame.dtype = np.dtype(np.float32) if acc_scale else ig[name].dtype
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
                print "Sending signal display frame with timestamp %i. %s. Max: %i, Mean: %i" % (sd_timestamp, "Unscaled" if not acc_scale else "Scaled by %i" % ((meta['n_accs'] if meta.has_key('n_accs') else 1)), np.max(ig[name]),np.mean(ig[name]))
                ig_sd['sd_data'] = ig[name] if not acc_scale else (ig[name] / float(meta['n_accs'] if meta.has_key('n_accs') else 1)).astype(np.float32)
                ig_sd['sd_timestamp'] = int(sd_timestamp * 100)
                tx_sd.send_heap(ig_sd.get_heap())
            f[remap(name)][datasets_index[name]] = ig[name]
            if name == 'timestamp':
                try:
                    f[timestamps][datasets_index[name]] = ig['sync_time'] + (ig['timestamp'] / ig['scale_factor_timestamp'])
                     # insert derived timestamps
                except KeyError:
                    f[timestamps][datasets_index[name]] = -1.0;
            datasets_index[name] += 1
            item._changed = False
              # we have dealt with this item so continue...
        if idx==0 and cfg is not None:
            # add config store metadata after receiving first frame. This should ensure that the values pulled are fresh.
            for s in config_sensors:
                f[observation_map].attrs[s] = kat.cfg.sensor.__getattribute__(s).get_value()
            print "Added initial observation sensor values...\n"
        idx+=1
    for (name,idx) in datasets_index.iteritems():
        if idx == 1:
            print "Repacking dataset",name,"as an attribute as it is singular."
            f[correlator_map].attrs[name] = f[remap(name)].value[0]
            del f[remap(name)]
    f.flush()
    f.close()
    return fname

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
    while True:
        fname = receive(opts.data_port, opts.acc_scale, opts.ip, cfg)
        print "Capture complete. Data recored to %s" % fname
        time.sleep(2) # wait for sockets to close
