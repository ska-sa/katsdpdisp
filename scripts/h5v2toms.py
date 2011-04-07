#!/usr/bin/python

# Produces a CASA compatible Measurement Set from a KAT-7 HDF5 file.
#
# Uses the pyrap python CASA bindings from the ATNF.

import os
import sys
import numpy as np
import katpoint
import katcore.targets
import shutil
import tarfile
from k7augment import ms_extra
from optparse import OptionParser
from h5py import File

def get_single_value(group, name):
    """Return a single value from an attribute or dataset of the given name.

       If data is retrieved from a dataset, this functions raises an error
       if the values in the dataset are not all the same. Otherwise it
       returns the first value."""
    value = group.attrs.get(name, None)
    if value is not None:
        return value
    dataset = group.get(name, None)
    if dataset is None:
        raise ValueError("Could not find attribute or dataset named %r/%r" % (group.name, name))
    if not dataset.len():
        raise ValueError("Found dataset named %r/%r but it was empty" % (group.name, name))
    if not all(dataset.value == dataset.value[0]):
        raise ValueError("Not all values in %r/%r are equal. Values found: %r" % (group.name, name, dataset.value))
    return dataset.value[0]

parser = OptionParser()
parser.add_option("-w", "--stop_w", dest="stop_w", action="store_true", default=False, help="Use the W term to stop the fringes for each baseline.")
parser.add_option("-t", "--tar", action="store_true", default=False, help="Tar ball the ms")
(options, args) = parser.parse_args()

 # NOTE: This should be checked before running (only for w stopping) to see how up to date the cable delays are !!!
delays = [478.041e-9, 545.235e-9, 669.900e-9, 772.868e-9, 600.0e-9, 600.0e-9, 600.0e-9]
 # updated by simonr July 5th 2010

if not sys.argv[-1].endswith(".h5"):
    print "No h5 filename supplied.\n"
    print "Usage: h5toms.py [options] <filename.h5>"
    sys.exit()
file = sys.argv[-1]

if options.stop_w:
    print "W term in UVW coordinates will be used to stop the fringes."

if ms_extra.pyrap_fail == True:
    print "Failed to import pyrap. You need to have both casacore and pyrap installed in order to produce measurement sets."
    sys.exit(0)

ms_name = file[:file.rfind(".")] + ".ms"
 # first step is to copy the blank template MS to our desired output...
#if os.path.isdir(ms_name) or os.path.isdir(
try:
    shutil.copytree("/var/kat/static/blank.ms",ms_name)
except Exception, err:
    print "Failed to copy blank ms to",ms_name,". Cannot write MS output...(",err,")"
    sys.exit(0)

print "Will create MS output in",ms_name

f = File(file, 'r+')

 # build the antenna table
antenna_objs = {}
antenna_positions = []
antenna_diameter = 0
dbe_map = {}
id_map = {}
ant_map = {}
for a in f['/MetaData/Configuration/Antennas'].iterobjects():
    name = a.name[a.name.rfind("/") + 1:]
    print name
    antenna_objs[name] = katpoint.Antenna(a.attrs['description'])
    antenna_diameter = antenna_objs[name].diameter
    antenna_positions.append(antenna_objs[name].position_ecef)
    num_receptors_per_feed = 2

#### Non file specific MS stuff ####
ms_dict = {}
telescope_name = "KAT-7"
observer_name = f['/MetaData/Configuration/Observation'].attrs['script_observer']
project_name = ""
ms_dict['ANTENNA'] = ms_extra.populate_antenna_dict(antenna_positions, antenna_diameter)

sg = f['/MetaData/Configuration/Correlator']
#dump_rate = 1/sg.attrs['int_time']
dump_rate = 1/get_single_value(sg, 'int_time')
channels = sg.attrs['n_chans']
bandwidth = float(sg.attrs['bandwidth']) / channels
center_frequency = sg.attrs['center_freq'] + 1.5e9
center_freqs = [center_frequency + bandwidth*c + 0.5*bandwidth for c in range(-channels/2, channels/2)]
n_bls = sg.attrs['n_bls']
n_pol = sg.attrs['n_stokes']
bls_ordering = sg.attrs['bls_ordering']

pol_type = 'HV'
#for mt in sg['input_map'].value:
#    a1 = dbe_map[mt[1][:2]]
#    a2 = dbe_map[mt[1][2:]]
#    ak = a1[:-1] + ":" + a2[:-1]
#    id_map[mt[0]] = a1 + ":" + a2
#    if mt[0] == 2:
#     # the third product will tell us the pol type...
#        pol_type = a1[-1] + a2[-1]
#    ant_map[ak] = ant_map[ak] + [mt[0]] if ant_map.has_key(ak) else [mt[0]]
#print id_map

field_id = 0
field_counter = -1
fields = {}
obs_start = 0
obs_end = 0

ms_dict['FEED'] = ms_extra.populate_feed_dict(len(antenna_positions), num_receptors_per_feed)
ms_dict['DATA_DESCRIPTION'] = ms_extra.populate_data_description_dict()
ms_dict['POLARIZATION'] = ms_extra.populate_polarization_dict(pol_type=pol_type)
ms_dict['MAIN'] = []
ms_dict['FIELD'] = []


refant = f['MetaData']['Configuration']['Observation'].attrs['script_ants'].split(",")[0]
refant_obj = antenna_objs[refant]

print "\nUsing %s as the reference antenna. All targets and activity detection will be based on this antenna.\n" % refant

data_ref = f['/Data/correlator_data']
data_timestamps = f['/Data/timestamps'].value
print data_timestamps.shape
target_sensor = f['/MetaData/Sensors/Antennas'][refant]['target'].value

dump_endtimes = data_timestamps + (0.5 / dump_rate)
target, target_timestamps = target_sensor['value'], target_sensor['timestamp']
target_changes = [n for n in xrange(len(target)) if target[n] and ((n== 0) or (target[n] != target[n - 1]))]
target, target_timestamps = target[target_changes],target_timestamps[target_changes]
compscan_starts = dump_endtimes.searchsorted(target_timestamps)
compscan_ends = np.r_[compscan_starts[1:] - 1, len(dump_endtimes) - 1]
for i,c_start_id in enumerate(compscan_starts):
    c_end_id = compscan_ends[i] + 1
    print "Cscan runs from id %i to id %i\n" % (c_start_id, c_end_id)
    tstamps = data_timestamps[c_start_id:c_end_id]
    c_start = tstamps[0]
    c_end = tstamps[-1]
    tgt = katpoint.Target(target[i][1:-2]) #[1:-2] strip out " from sensor values
    tgt.antenna = refant_obj
    radec = tgt.radec()
    if fields.has_key(tgt.description):
        field_id = fields[tgt.description]
    else:
        field_counter += 1
        field_id = field_counter
        fields[tgt.description] = field_counter
        ms_dict['FIELD'].append(ms_extra.populate_field_dict(tgt.radec(), katpoint.Timestamp(c_start).to_mjd() * 24 * 60 * 60, field_name=tgt.name))
          # append this new field
        print "Adding new field id",field_id,"with radec",tgt.radec()

    tstamps = tstamps + (0.5/dump_rate)
             # move timestamps to middle of integration
    mjd_tstamps = [katpoint.Timestamp(t).to_mjd() * 24 * 60 * 60 for t in tstamps]
    data = data_ref[c_start_id:c_end_id].astype(np.float32).view(np.complex64)[:,:,:,:,0].swapaxes(1,2).swapaxes(0,1)
     # pick up the data segement for this compound scan, reorder into bls, timestamp, channels, pol, complex
    for bl in range(n_bls):
        (a1, a2) = bls_ordering[bl]
        if a1 > 6 or a2 > 6: continue
        a1_name = 'ant' + str(a1 + 1)
        a2_name = 'ant' + str(a2 + 1)
        uvw_coordinates = np.array(tgt.uvw(antenna_objs[a2_name], tstamps / 1000, antenna_objs[a1_name]))
	vis_data = data[bl]
        if options.stop_w:
            cable_delay_diff = (delays[int(a2)-1] - delays[int(a1)-1])
            w = np.outer(((uvw_coordinates[2] / katpoint.lightspeed) + cable_delay_diff), center_freqs)
             # get w in terms of phase (in radians). This is now frequency dependent so has shape(tstamps, channels)
            vis_data *= np.exp(-2j * np.pi * w)
            # recast the data into (ts, channels, polarisations, complex64)
        ms_dict['MAIN'].append(ms_extra.populate_main_dict(uvw_coordinates, vis_data, mjd_tstamps, int(a1), int(a2), 1.0/dump_rate, field_id))

     # handle the per compound scan specific MS rows. (And those that are common, but only known after at least on CS)
     # the field will in theory change per compound scan. The spectral window should be constant, but is only known
     # after parsing at least one scan.
    if not ms_dict.has_key('SPECTRAL_WINDOW'):
        ms_dict['SPECTRAL_WINDOW'] = ms_extra.populate_spectral_window_dict(center_frequency, bandwidth, channels)
 # end of compound scans
ms_dict['OBSERVATION'] = ms_extra.populate_observation_dict(obs_start, obs_end, telescope_name, observer_name, project_name)

 # finally we write the ms as per our created dicts
ms_extra.write_dict(ms_dict,ms_name)
if options.tar:
    tar = tarfile.open('%s.tar' % ms_name, 'w')
    tar.add(ms_name, arcname=os.path.basename(ms_name))
    tar.close()
