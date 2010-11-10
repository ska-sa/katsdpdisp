#!/usr/bin/python

# Capture utility for a relatively generic packetised correlator data output stream.

# The script performs two primary roles:
#
# Storage of stream data on disk in hdf5 format. This includes placing meta data into the file as attributes.
#
# Regeneration of a SPEAD stream suitable for us in the online signal displays. At the moment this is basically
# just an aggregate of the incoming streams from the multiple x engines scaled with n_accumulations (if set)

import numpy as np, spead, logging, sys, time, h5py

logging.basicConfig(level=logging.WARNING)

acc_scale = False
 # scale by the reported number of accumulations per dump

data_port = 7148
sd_ip = '192.168.4.20'

def receive():
    print 'Initalising SPEAD transports...'
    print "Data reception on port",data_port
    rx = spead.TransportUDPrx(data_port, pkt_count=1024, buffer_size=51200000)
    print "Sending Signal Display data to",sd_ip
    tx_sd = spead.Transmitter(spead.TransportUDPtx(sd_ip, 7149))
    ig = spead.ItemGroup()
    ig_sd = spead.ItemGroup()
    f = h5py.File(str(int(time.time())) + ".pc.h5", mode="w")
    data_ds = None
    ts_ds = None
    idx = 0
    dump_size = 0
    datasets = {}
    datasets_index = {}
    meta_required = ['n_chans','n_bls','n_stokes']
     # we need these bits of meta data before being able to assemble and transmit signal display data
    meta_desired = ['n_accs']
     # if we find these, then what hey :)
    meta = {}
    sd_frame = None
    sd_slots = None
    sd_timestamp = None
    write_enabled = True
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
                meta_required.pop(meta_required.index(name))
                if len(meta_required) == 0:
                    sd_frame = np.zeros((meta['n_chans'],meta['n_bls'],meta['n_stokes'],2),dtype=np.int32)
                    print "Initialised sd frame to shape",sd_frame.shape
            if not datasets.has_key(name):
             # check to see if we have encountered this type before
                shape = ig[name].shape if item.shape == -1 else item.shape
                dtype = np.dtype(type(ig[name])) if shape == [] else item.dtype
                if dtype is None: dtype = ig[name].dtype
                 # if we can't get a dtype from the descriptor try and get one from the value
                print "Creating dataset for name:",name,", shape:",shape,", dtype:",dtype
                f.create_dataset(name,[1] + ([] if list(shape) == [1] else list(shape)), maxshape=[None] + ([] if list(shape) == [1] else list(shape)), dtype=dtype)
                dump_size += np.multiply.reduce(shape) * dtype.itemsize
                datasets[name] = f[name]
                datasets_index[name] = 0
                if not item._changed: continue
                 # if we built from and empty descriptor
            else:
                print "Adding",name,"to dataset. New size is",datasets_index[name]+1
                f[name].resize(datasets_index[name]+1, axis=0)
            if sd_frame is not None and name.startswith("xeng_raw"):
                sd_timestamp = ig['sync_time'] + (ig['timestamp'] / ig['scale_factor_timestamp'])
                print "SD Timestamp:", sd_timestamp," (",time.ctime(sd_timestamp),")"
                if sd_slots is None:
                    sd_frame.dtype = np.dtype(np.float32) if acc_scale else ig[name].dtype
                     # make sure we have the right dtype for the sd data
                    sd_slots = np.zeros(meta['n_chans']/ig[name].shape[0])
                    n_xeng = len(sd_slots)
                     # this is the first time we know how many x engines there are
                    f['/'].attrs['n_xeng'] = n_xeng
                    ig_sd.add_item(name=('sd_data'),id=(0x3501), description="Combined raw data from all x engines.", ndarray=(sd_frame.dtype,sd_frame.shape))
                    ig_sd.add_item(name=('sd_timestamp'), id=0x3502, description='Timestamp of this sd frame in centiseconds since epoch (40 bit limitation).', shape=[], fmt=spead.mkfmt(('u',spead.ADDRSIZE)))
                    t_it = ig_sd.get_item('sd_data')
                    print "Added SD frame dtype",t_it.dtype,"and shape",t_it.shape
                    tx_sd.send_heap(ig_sd.get_heap())
                print "Sending signal display frame with timestamp %i. %s. Max: %i, Mean: %i" % (sd_timestamp,
                    "Unscaled" if not acc_scale else "Scaled by %i" % ((meta['n_accs'] if meta.has_key('n_accs') else 1)), np.max(ig[name]),np.mean(ig[name]))
                ig_sd['sd_data'] = ig[name] if not acc_scale else (ig[name] / float(meta['n_accs'] if meta.has_key('n_accs') else 1)).astype(np.float32)
                ig_sd['sd_timestamp'] = int(sd_timestamp * 100)
                tx_sd.send_heap(ig_sd.get_heap())
            f[name][datasets_index[name]] = ig[name]
            datasets_index[name] += 1
            item._changed = False
              # we have dealt with this item so continue...
        idx+=1
    for (name,idx) in datasets_index.iteritems():
        if idx == 1:
            print "Repacking dataset",name,"as an attribute as it is singular."
            f['/'].attrs[name] = f[name].value[0]
            f.__delitem__(name)
    f.flush()
    f.close()
receive()
