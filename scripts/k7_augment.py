#!/usr/bin/python

# This script is for augmenting Kat-7 HDF5v2 files
#
# The output file should conform to the specification as described in the hdf5 v2 design record.
#
# Briefly this means it will contain Data and MetaData main groups.
# MetaData is further split into:
#  Configuration (static config values at the start of obs)
#  Markup (flags and other markup produced during processing)
#  History (log of changes to the file and observer observations)
#  Sensor (mandatory sensors as required by the minor version and optional sensors as supplied by the observer)
#

import sys
import re
import time
import os
import signal
import shutil
import logging
from optparse import OptionParser

import numpy as np
from h5py import File

import katuilib
import katpoint
import katcore.targets
from k7augment import ms_extra

major_version = 2
 # only augment files of this major version
augment_version = 0
 # the minor version number created by this version of augment
 # will override any existing version

errors = 0
section_reports = {}

def get_input_info(array_cfg):
    """Get correlator input mapping and delays from config system.

    Parameters
    ----------
    array_cfg : :class:`katcore.targets.ArrayConfig` object
        ArrayConfig object from which to extract correlator info

    Returns
    -------
    config_antennas : set of ints
        The numbers of antennas that are connected to the correlator
    dbe_delay : dict
        Mapping from DBE input string to delay in seconds (also a string)
    real_to_dbe : dict
        Mapping from antenna+pol string to DBE input string

    """
    config_antennas, dbe_delay, real_to_dbe = set(), {}, {}
    for k, v in array_cfg.correlator.inputs.iteritems():
        # Connection on DBE side is labelled '0x', '1y', etc.
        dbe = '%d%s' % k
        # Connection on antenna side is labelled '1H', '2V', etc.
        # This assumes the antenna name is 'antX', where X is the antenna number
        ant_num, pol, delay = int(v[0][3:]), v[1].capitalize(), v[2]
        real = '%d%s' % (ant_num, pol)
        config_antennas.add(ant_num)
        dbe_delay[dbe] = '%.16e' % delay
        real_to_dbe[real] = dbe
    return config_antennas, dbe_delay, real_to_dbe

def get_antenna_info(array_cfg):
    """Get antenna objects, positions and diameter from config system.

    Parameters
    ----------
    array_cfg : :class:`katcore.targets.ArrayConfig` object
        ArrayConfig object from which to extract antenna info

    Returns
    -------
    antennas : dict
        Mapping from antenna name to :class:`katpoint.Antenna` object
    antenna_positions : array, shape (N, 3)
        Antenna positions in ECEF coordinates, in metres
    antenna_diameter : float
        Antenna dish diameter (taken from first dish in array)
    noise_diode_models : dict
        Mapping from '%(antenna)_%(diode)_%(pol)' to noise diode model CSV file

    """
    antenna_positions, antennas, noise_diode_models = [], {}, {}
    for ant_name, ant_cfg in array_cfg.antennas.iteritems():
        antenna_positions.append(ant_cfg.observer.position_ecef)
        antennas[ant_name] = ant_cfg.observer
        for nd_name, nd_file in ant_cfg.noise_diode_models.iteritems():
            noise_diode_models[ant_name + "_" + nd_name] = nd_file
    antenna_positions = np.array(antenna_positions)
    antenna_diameter = antennas.values()[0].diameter
    return antennas, antenna_positions, antenna_diameter, noise_diode_models

def load_csv_with_header(csv_file):
    """Load CSV file containing commented-out header with key-value pairs.

    This is used to load the noise diode model CSV files, which contain extra
    metadata in its headers.

    Parameters
    ----------
    csv_file : file object or string
        File object of opened CSV file, or string containing the file name

    Returns
    -------
    csv : array, shape (N, M)
        CSV data as a 2-dimensional array with N rows and M columns
    attrs : dict
        Key-value pairs extracted from header

    """
    try:
        csv_file = open(csv_file) if isinstance(csv_file, basestring) else csv_file
    except Exception, e:
        print "Failed to load csv_file (%s). %s\n" % (csv_file, e)
    start = csv_file.tell()
    csv = np.loadtxt(csv_file, comments='#', delimiter=',')
    csv_file.seek(start)
    header = [line[1:].strip() for line in csv_file.readlines() if line[0] == '#']
    keyvalue = re.compile('\A([a-z]\w*)\s*[:=]\s*(.+)')
    attrs = dict([keyvalue.match(line).groups() for line in header if keyvalue.match(line)])
    return csv, attrs


def get_sensor_data(sensor, start_time, end_time, dither=1, initial_value=False):
    """Returns a recarray containing timestamp and value columns for the specified sensor.

    Parameters
    ----------
    sensor : KATSensor
        The sensor from which to retrieve the data
    start_time : integer
        The start time of the period for which to retrieve data
    end_time : integer
        The end time of the period for which to retrieve data
    dither : integer
        The number of seconds either side of the specified start and end to retrieve data for
        default: 1
    initial_value : boolean
        If true then an initial value for the sensor (i.e. the last known good value before the requested range)
        is retrieve and inserted as the first entry in the returned array. Note this is an expensive
        operation and should be reserved for those cases known to require it.
        default: False
    Returns
    -------
    array : dtype=[('timestamp','float'),('value', '<f4')]
    """
    print "Pulling data for sensor %s from %i to %i\n" % (sensor.name, start_time, end_time)
    start_time = start_time - dither
    end_time = end_time + dither
    initial_data = [[], [], []]
    if initial_value:
        initial_data = sensor.get_stored_history(select=False,start_time=start_time,end_time=start_time, last_known=True)
        print "Initial value fetch:",initial_data
    stime = time.time()
    data = sensor.get_stored_history(select=False,start_time=start_time,end_time=end_time)
    print "Retrieved data of length",len(data[1]),"in",time.time()-stime,"s"
    return np.rec.fromarrays([initial_data[0] + data[0], initial_data[1] + data[1], initial_data[2] + data[2]], names='timestamp, value, status')

def insert_sensor(name, dataset, obs_start, obs_end, int_time, iv=False):
    global errors
    pstime = time.time()
    try:
        sensor_i = kat.sensors.__dict__[name]
        data = get_sensor_data(sensor_i, obs_start, obs_end, int_time, initial_value=iv)
        if np.multiply.reduce(data.shape) == 0:
            section_reports[name] = "Warning: Sensor %s has no data for the specified time period. Inserting empty dataset."
            s_dset = dataset.create_dataset(sensor_i.name, [], maxshape=None)
        else:
            s_dset = dataset.create_dataset(sensor_i.name, data=data)
            section_reports[name] = "Success"
        s_dset.attrs['name'] = sensor_i.name
        s_dset.attrs['description'] = sensor_i.description
        s_dset.attrs['units'] = sensor_i.units
        s_dset.attrs['type'] = sensor_i.type
    except KeyError:
         # sensor does not exist
        section_reports[name] = "Error: Cannot find sensor",name,".This is most likely a configuration issue."
        errors += 1
    except Exception, err:
        if not str(err).startswith('Name already exists'):
            section_reports[name] = "Error: Failed to create dataset for "+ name + " (" + str(err) + ")"
            errors += 1
        else:
            section_reports[name] = "Success (Note: Existing data for this sensor was not changed.)"
    if options.verbose: print "Creation of dataset for sensor " + name + " took " + str(time.time() - pstime) + "s"

def create_group(f, name):
    try:
        ng = f.create_group(name)
    except:
        ng = f[name]
    return ng

def get_lo1_frequency(start_time):
    try:
        return kat.sensors.rfe7_rfe7_lo1_frequency.get_stored_history(select=False, include_central=True, start_time=start_time, end_time=start_time, last_known=True)[1][0]
    except Exception, err:
        section_reports['lo1_frequency'] = "Warning: Failed to get a stored value for lo1 frequency. Defaulting to 6022000000.0"
        return 6022000000.0

def terminate(_signum, _frame):
    print "augment - User requested terminate..."
    print "augment stopped"
    sys.exit(0)


def get_files_in_dir(directory):
    files = []
    p = os.listdir(directory+"/")
    p.sort()
    while p:
        x = p.pop()
        if x.endswith("unaugmented.h5"):
            files.append(directory+"/" + x)
    return files

parser = OptionParser()
parser.add_option("-b", "--batch", action="store_true", default=False, help="If set augment will process all unaugmented files in the directory specified by -d, and then continue to monitor this directory. Any new files that get created will be augmented in sequence.")
parser.add_option("-c", "--config", dest='config', default=None, help='look for configuration files in folder CONF [default is KATCONF environment variable or /var/kat/conf]')
parser.add_option("-u", "--central_monitor_url", default=None, help="Override the central monitor url in the configuration with the one specified.")
parser.add_option("-d", "--dir", default=katuilib.defaults.kat_directories["data"], help="Process all unaugmented files in the specified directory. [default=%default]")
parser.add_option("-f", "--file", default="", help="Fully qualified path to a specific file to augment. [default=%default]")
parser.add_option("-s", "--system", default="systems/local.conf", help="System configuration file to use. [default=%default]")
parser.add_option("-m", "--ms", action="store_true", default=False,help="In addition to augmenting the specified file a measurement set of the data will be produced. Note that in this case a file must be specified and all the baselines associated with this file will be augmented.")
parser.add_option("-o", "--override", dest="force", action="store_true", default=False, help="If set, previously augmented files will be re-augmented. Only useful in conjunction with a single specified file.")
parser.add_option("-v", "--verbose", action="store_true", default=False, help="Verbose output.")
parser.add_option("-n", "--nd_dir", default="/var/kat/conf/noise-diode-models", help="Directory in which csv noise diode models are stored. Naming is expected to follow: ant\w.[pin|coupler].[h|v].csv")


(options, args) = parser.parse_args()
signal.signal(signal.SIGTERM, terminate)
signal.signal(signal.SIGINT, terminate)

#### Setup configuration source
###katconf.set_config(katconf.environ(options.config))

state = ["|","/","-","\\"]
batch_count = 0

pointing_sensors = ["activity","target","observer","pos_actual_scan_azim","pos_actual_scan_elev","pos_actual_refrac_azim","pos_actual_refrac_elev","pos_actual_pointm_azim","pos_actual_pointm_elev","pos_request_scan_azim","pos_request_scan_elev","pos_request_refrac_azim","pos_request_refrac_elev","pos_request_pointm_azim","pos_request_pointm_elev"]
enviro_sensors = ["asc_air_temperature","asc_air_pressure","asc_air_relative_humidity","asc_wind_speed","asc_wind_direction"]
 # a list of pointing sensors to insert
pedestal_sensors = ["rfe3_rfe15_noise_pin_on", "rfe3_rfe15_noise_coupler_on"]
 # a list of pedestal sensors to insert
beam_sensors = ["dbe_target"]
 # a list of sensor for beam 0

sensors = {'ant':pointing_sensors, 'ped':pedestal_sensors, 'ped1':enviro_sensors}
 # mapping from sensors to proxy

sensors_iv = {"rfe3_rfe15_noise_pin_on":True, "rfe3_rfe15_noise_coupler_on":True, "activity":True, "target":True,"observer":True,"lock":True}
 # indicate which sensors will require an initial value fetch

######### Start of augment code #########

files = []
if options.ms:
    if ms_extra.pyrap_fail == True:
        print "Failed to import pyrap. You need to have both casacore and pyrap installed in order to produce measurement sets."
        sys.exit(0)
    options.override = True
 # we need to force an augment so that data will be read from the specified files and inserted into the ms

if options.ms and options.file == "":
    print "You must use the -f specified to choose a specific file when creating measurement set output."
    sys.exit(0)

if options.file == "":
    files = get_files_in_dir(options.dir)
else:
    files.append(options.file)
    if options.ms:
        p = os.listdir(options.dir+"/")
        ms_name = options.file[:options.file.rfind(".")] + ".ms"
            # first step is to copy the blank template MS to our desired output...
        try:
            shutil.copytree("/var/kat/static/blank.ms",ms_name)
        except Exception, err:
            print "Failed to copy blank ms to",ms_name,". Cannot write MS output...(",err,")"
            sys.exit(0)

if len(files) == 0 and not options.batch:
    print "No files matching the specified criteria where found..."
    sys.exit(0)

print "Found",len(files),"files to process"
if options.ms:
    print "Will create MS output in",ms_name

 # build an kat object for history gathering purposes
print "Creating KAT connections..."
kat = katuilib.tbuild(options.system, log_level=logging.ERROR, central_monitor_url=options.central_monitor_url)
 # check that we have basic connectivity (i.e. two antennas and pedestals)
time.sleep(1)
while not kat.ant1.katcpobj.is_connected() or not kat.ant2.katcpobj.is_connected() or not kat.ped1.katcpobj.is_connected() or not kat.ped2.katcpobj.is_connected():
    status = "\r%s Connections to basic system of two antennas and two pedestals not available. Waiting for these to appear (possibly futile)..." % str(state[batch_count % 4])
    sys.stdout.write(status)
    sys.stdout.flush()
    time.sleep(30)
    batch_count += 1
kat.disconnect()
 # we dont need live connection anymore
section_reports['configuration'] = str(options.system)

array_cfg = katuilib.conf.KatuilibConfig(options.system).get_array()
 # get array info from config system
config_antennas, dbe_delay, real_to_dbe = get_input_info(array_cfg)
 # return dicts showing the current mapping between dbe inputs and real antennas
antennas, antenna_positions, antenna_diameter, noise_diode_models = get_antenna_info(array_cfg)
 # build the description and position (in ecef coords) arrays for the antenna in the selected configuration
diodes = set([name.split('_')[1] for name in noise_diode_models])

#### Non file specific MS stuff ####
ms_dict = {}
telescope_name = "KAT-7"
observer_name = "ffuser"
project_name = ""
ms_dict['ANTENNA'] = ms_extra.populate_antenna_dict(antenna_positions, antenna_diameter)
num_receptors_per_feed = 2
ms_dict['FEED'] = ms_extra.populate_feed_dict(len(antenna_positions), num_receptors_per_feed)
ms_dict['DATA_DESCRIPTION'] = ms_extra.populate_data_description_dict()
ms_dict['POLARIZATION'] = ms_extra.populate_polarization_dict()
ms_dict['MAIN'] = []
ms_dict['FIELD'] = []
 # this is all we can do for now. The remainder requires input from the file itself...

inputs = 16
input_map = [('ant' + str(int(x/2) + 1) + (x % 2 == 0 and 'H' or 'V'), str(int(x / 2)) + (x % 2 == 0 and 'x' or 'y')) for x in range(inputs)]

while(len(files) > 0 or options.batch):
    for fname in files:
        errors = 0
        fst = time.time()
        print "\nStarting augment of file",fname
        new_extension = "h5"
        try:
            f = File(fname, 'r+')
            if f['/'].attrs.get('version_number',"0.0") == str(major_version):
                print "This version of augment required HDF5 files of version %i to augment. Your file has major version %s\n" % (major_version, current_version[0])
                sys.exit(0)
            last_run = f['/'].attrs.get('augment_ts',None)
            if last_run:
                print "Warning: This file has already been augmented: " + str(last_run)
                if not options.force:
                    print "To force reprocessing, please use the -o option."
                    sys.exit()
                else:
                    section_reports['reaugment'] = "Augment was previously done in this file on " + str(last_run)
            f['/'].attrs['version_number'] = "%i.%i" % (major_version, augment_version)

            obs_start = f['/Data/timestamps'].value[1]
             # first timestamp is currently suspect
            f['/Data'].attrs['ts_of_first_timeslot'] = obs_start
            obs_end = f['/Data/timestamps'].value[-1]
            print "Observation session runs from %s to %s\n" % (time.ctime(obs_start), time.ctime(obs_end))
            int_time = f['/MetaData/Configuration/Correlator'].attrs['int_time']
            f['/MetaData/Configuration/Correlator'].attrs['input_map'] = input_map
             # TODO: default input mapping for now. Once config system has input_map sensor we pull from there

            hist = create_group(f,"/History")
            sg = create_group(f, "/MetaData/Sensors")
            ag = create_group(sg, "Antennas")
            acg = create_group(f, "/MetaData/Configuration/Antennas")
            pg = create_group(sg, "Pedestals")
            eg = create_group(sg, "Enviro")
            bg = create_group(sg, "Beams")

            for antenna in range(1,8):
                antenna = str(antenna)
                ant_name = 'ant' + antenna
                try:
                    a = ag.create_group(ant_name)
                    ac = acg.create_group(ant_name)
                except:
                    a = ag[ant_name]
                    ac = acg.create_group(ant_name)
                stime = time.time()
                for sensor in pointing_sensors:
                    insert_sensor(ant_name + "_" + sensor, a, obs_start, obs_end, int_time, iv=(sensors_iv.has_key(sensor) and True or False))
                if options.verbose: print "Overall creation of sensor table for antenna " + antenna + " took " + str(time.time()-stime) + "s"
                # noise diode models
                for pol in ['h','v']:
                    for nd in ['coupler','pin']:
                        nd_fname = "%s/%s.%s.%s.csv" % (options.nd_dir, ant_name, nd, pol)
                        model = np.zeros((1,2), dtype=np.float32)
                        attrs = {}
                        try:
                            model, attrs = load_csv_with_header(nd_fname)
                        except Exception, e:
                            print "Failed to open noise diode model file %s. Inserting null noise diode model. (%s)" % (nd_fname, e)
                        nd = ac.create_dataset("%s_%s_noise_diode_model" % (pol, nd), data=model)
                        for key,val in attrs.iteritems(): nd.attrs[key] = val

            for ped in range(1,8):
                ped = str(ped)
                ped_name = 'ped' + ped
                try:
                    p = pg.create_group(ped_name)
                except:
                    p = pg[ped_name]
                stime = time.time()
                for sensor in pedestal_sensors:
                    insert_sensor(ped_name + "_" + sensor, p, obs_start, obs_end, int_time, iv=(sensors_iv.has_key(sensor) and True or False))
                if options.verbose: print "Overall creation of sensor table for pedestal " + ped + " took " + str(time.time()-stime) + "s"

            b0 = bg.create_group("Beam0")
            for sensor in beam_sensors:
                insert_sensor(sensor, b0, obs_start, obs_end, int_time, iv=(sensors_iv.has_key(sensor) and True or False))

            stime = time.time()
            for sensor in enviro_sensors:
                insert_sensor("anc_" + sensor, eg, obs_start, obs_end, int_time)
            if options.verbose: print "Overall creation of enviro sensor table took " + str(time.time()-stime) + "s"
             # end of antenna loop
            f['/'].attrs['augment_ts'] = time.time()

        except Exception, err:
            section_reports["general"] = "Exception: " + str(err)
            errors += 1
            print "Failed to run augment. File will be  marked as 'failed' and ignored:  (" + str(err) + ")"
            new_extension = "failed.h5"
        try:
            log = np.rec.fromarrays([np.array(section_reports.keys()), np.array(section_reports.values())], names='section, message')
            f['/'].attrs['augment_errors'] = errors
            if options.force:
                try:
                    del hist['augment_log']
                except KeyError:
                    pass # no worries if the augment log does not exist, a new one is written...
            try:
                hist.create_dataset("augment_log", data=log)
            except ValueError:
                hist['augment_log'].write_direct(log)
        except Exception, err:
            print "Warning: Unable to create augment_log dataset. (" + str(err) + ")"
        f.close()

        if options.verbose:
            print "\n\nReport"
            print "======"
            keys = section_reports.keys()
            keys.sort()
            for k in keys:
                print k.ljust(50),section_reports[k]
        try:
            #Drop the last two extensions of the file 123456789.xxxxx.h5 becomes 123456789.
            #And then add the new extension in its place thus 123456789.unaugmented.h5 becomes 123456789.h5 or 123456789.failed.h5
            lst = fname.split(".")
            y = ".".join(l for l in lst[:-2]) + "."
            renfile = y + new_extension
            os.rename(fname, renfile)
            print "File has been renamed to " + str(renfile) + "\n"
        except:
            print "Failed to rename " + str(fname) + " to " + str(renfile) + ". This is most likely a permissions issue. Please resolve these and either manually rename the file or rerun augment with the -o option."
            sys.exit()
        print (errors == 0 and "No errors found." or str(errors) + " potential errors found. Please inspect the augment log by running 'h5dump -d /augment_log " + str(renfile) + "'.")

    if options.ms:
        # finally we write the ms as per our created dicts
        ms_extra.write_dict(ms_dict,ms_name)
     # if in batch mode check for more files...
    files = []
    if options.batch:
        time.sleep(2)
        status = "\rChecking for new files in %s: %s" % (options.dir,str(state[batch_count % 4]))
        sys.stdout.write(status)
        sys.stdout.flush()
        files = get_files_in_dir(options.dir)
        batch_count += 1
