#!/usr/bin/python

####!/usr/bin/env python
import optparse
import katsdpservices
from multiprocessing import Process, Queue, Pipe, Manager, current_process
import tornado.ioloop
import tornado.httpserver
import tornado.web
import tornado.websocket
import tornado.template
from pkg_resources import resource_filename
import os
import traceback
import commands
import time
import SocketServer
import socket
import thread,threading
import struct
import sys
import logging
import numpy as np
import copy
import katsdpdisp
import katsdpdisp.data as sdispdata
import re
import json
import resource
import gc
import manhole
import signal
import numbers
from guppy import hpy

SERVE_PATH=resource_filename('katsdpdisp', 'html')

np.set_printoptions(threshold=4096)
np.seterr(all='ignore')

#To run RTS ingestor simulator (in git/katsdpingest/scripts/):
#python ingest.py --sdisp-ips=192.168.1.235;python cbf_simulator.py --standalone;python cam2spead.py --fake-cam;python sim_observe.py;python ~/git/katsdpdisp/time_plot.py

#To run simulator:
#first ./time_plot.py k7simulator
#then run ./k7_simulator.py --test-addr :7149 --standalone
#
#if there is a crash that blocks port - use lsof (ls open files) to determine if there is a  process still running that should be killed
#
#####################################################################################
##Important before running this script:
##If running on a MAC and when streaming over the network (ie not read from local file,
## ie datafile='stream') then you may need to increase your buffer size using the command:
#
#sudo sysctl -w net.inet.udp.recvspace=5000000
#
##Note you need to be plugged into the network with a ethernet cable as the wireless is too slow.
##
##Additionally, previously you needed to issue the following commands to add your ip to the data streamer
#ssh ffuser@kat-dp
#ipython
#import katuilib
#k7w = katuilib.build_client("k7w","kat-dp",2040)
#k7w.req.add_sdisp_ip("192.168.1.156")
#to add center frequency info call
# import katuilib
# k7w = katuilib.build_client('k7w','192.168.193.4',4014,controlled=True)
# k7w.req.k7w_add_sdisp_ip("192.168.9.124")
# k7w.req.k7w_set_center_freq(1822000000)
# k7w.req.k7w_sd_metadata_issue()
#import socket
#localIPaddress=socket.gethostbyname(socket.gethostname())
#if not going through proxy
#import katuilib
#k7w = katuilib.build_client('k7w','192.168.193.5',2040,controlled=True)
#k7w.req.add_sdisp_ip(localIPaddress)
#k7w.req.set_center_freq(1822000000)
#k7w.req.sd_metadata_issue()
#configure()
#kat.dbe7.print_sensors('chan')
######################
# import katcp
#
# logger_katcp=logging.getLogger("katcp")
# logger_katcp.setLevel(logging.CRITICAL)
# client = katcp.BlockingClient('192.168.193.5',2040)#note this is kat-dc1.karoo.kat.ac.za
# client.start()
# client.wait_connected(timeout=5)
# client.is_connected()
# ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.193.7'), timeout=5)
# ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.6.110'), timeout=5)
# ret = client.blocking_request(katcp.Message.request('drop-sdisp-ip','192.168.6.110'), timeout=5)
# ret = client.blocking_request(katcp.Message.request('sd-metadata-issue'), timeout=5)
# client.stop()
######################
#file will be in kat@kat-dc1:/var/kat/data/
#and synced to eg kat@kat-archive:/var/kat/archive/data/comm/2012/10
#note may need to reaugment file if sensor data missing:
#on kat-dc1.karoo.kat.ac.za execute ps aux | grep aug
#see something like /usr/bin/python /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -v -b -d /var/kat/data/staging --dbe=dbe7
#must then run /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -o -f filename.h5 to augment file in place
#####################################################################################
##to debug somewhere in code, run this command: from IPython.Shell import IPShellEmbed; IPShellEmbed()()
##or if crashed then just type debug
#####################################################################################

#note timeseries ringbuffer should also store flaglist(as fn of channel) per time instant, or atleast whereever a change occurs

colour_dict={}
colour_dict_ant={}

#this colour list is exclusively used by ring buffer process for cross correlation product colours
def registeredcolour(signalname):
    if (signalname not in colour_dict):
        colour_dict[signalname]=np.random.random(3)*255
    return colour_dict[signalname]

#this colour list is exclusively used by main process, for bandpass and gain (per antenna) colours
def registeredcolourant(signalname):
    if (signalname not in colour_dict_ant):
        colour_dict_ant[signalname]=np.random.random(3)*255
    return colour_dict_ant[signalname]

#returns minimum and maximum channel numbers, and channel increment, and channels
def getstartstopchannels(ch_mhz,thetype,themin,themax,view_nchannels):
    if (thetype=='mhz'):
        if (themin==None or type(themin)==list or not np.isfinite(themin)):
            start_channel=0
        else:
            start_channel=int(((themax-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))
        if (themax==None or type(themax)==list or not np.isfinite(themax)):
            stop_channel=len(ch_mhz)
        else:
            stop_channel=int(((themin-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))+1
    elif (thetype=='ghz'):
        if (themin==None or type(themin)==list or not np.isfinite(themin)):
            start_channel=0
        else:
            start_channel=int(((themax*1e3-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))
        if (themax==None or type(themax)==list or not np.isfinite(themax)):
            stop_channel=len(ch_mhz)
        else:
            stop_channel=int(((themin*1e3-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))+1
    else:#channel
        if (themin==None or type(themin)==list or not np.isfinite(themin)):
            start_channel=0
        else:
            start_channel=int(themin)
        if (themax==None or type(themax)==list or not np.isfinite(themax)):
            stop_channel=len(ch_mhz)
        else:
            stop_channel=int(themax+1)

    if (start_channel>stop_channel):#ensures at least 2 channels even if clipped
        tmp=start_channel
        start_channel=stop_channel
        stop_channel=tmp
    if (start_channel<0):
        start_channel=0
    elif (start_channel>=len(ch_mhz)-1):
        start_channel=len(ch_mhz)-2
    if (stop_channel>len(ch_mhz)):
        stop_channel=len(ch_mhz)
    elif (stop_channel<=0):
        stop_channel=1

    if (view_nchannels==None or view_nchannels<1):
        channelincr=1
    else:
        channelincr=int(abs(stop_channel-start_channel)/view_nchannels)
        if (channelincr<1):
            channelincr=1
    return start_channel,stop_channel,channelincr,ch_mhz[start_channel:stop_channel:channelincr]

#assumes ts is timestamps although themin, themax is seconds after current timestamp (i.e. typically negative numbers)
def getstartstoptime(ts,themin,themax):
    if (themin==None or type(themin)==list or not np.isfinite(themin)):
        tstart=ts[0]
    else:
        tstart=ts[-1]+themin
    if (themax==None or type(themax)==list or not np.isfinite(themax)):
        tstop=ts[-1]
    else:
        tstop=ts[-1]+themax
    if (tstart>tstop):
        tmp=tstart
        tstart=tstop
        tstop=tmp
    return tstart,tstop

#idea is to store the averaged time series profile in channel 0
def RingBufferProcess(multicast_group, spead_port, spead_interface, memusage, max_custom_signals, datafilename, cbf_channels, ringbufferrequestqueue, ringbufferresultqueue, ringbuffernotifyqueue):
    thefileoffset=0
    typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
    fig={'title':'','xdata':np.arange(100),'ydata':[[np.nan*np.zeros(100)]],'color':np.array([[0,255,0,0]]),'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':'s','yunit':['dB'],'span':[],'spancolor':[]}
    hp = hpy()
    hpbefore = hp.heap()
    dh=katsdpdisp.KATData()
    if (datafilename=='stream'):
        interface_address = katsdpservices.get_interface_address(spead_interface)
        dh.start_spead_receiver(multicast_group=multicast_group,port=spead_port,interface_address=interface_address,capacity=memusage/100.0,max_custom_signals=max_custom_signals,cbf_channels=cbf_channels,notifyqueue=ringbuffernotifyqueue,store2=True)
        datasd=dh.sd
    elif (datafilename=='k7simulator'):
        dh.start_direct_spead_receiver(capacity=memusage/100.0,max_custom_signals=max_custom_signals,store2=True)
        datasd=dh.sd
    else:
        try:
            dh.load_ar1_data(datafilename, rows=300, startrow=thefileoffset, capacity=memusage/100.0, max_custom_signals=max_custom_signals, store2=True)
        except Exception,e:
            logger.warning(" Failed to load file using ar1 loader (%s)" % e, exc_info=True)
            try:
                dh.load_k7_data(datafilename,rows=300,startrow=thefileoffset)
            except Exception,e:
                logger.warning(" Failed to load file using k7 loader (%s)" % e, exc_info=True)
                try:
                    dh.load_ff_data(datafilename)
                except Exception,e:
                    logger.warning(" Failed to load file using ff loader (%s)" % e, exc_info=True)
                    pass
                pass
            pass
        datasd=dh.sd_hist
    logger.info('Started ring buffer process')
    warnOnce=True
    try:
        while(True):
            #ts = datasd.select_data(product=0, start_time=0, end_time=-1, start_channel=0, stop_channel=0, include_ts=True)[0]#gets last timestamp only
            #ts[0] contains times
            #antbase=np.unique([0 if len(c)!=5 else int(c[3:-1])-1 for c in datasd.cpref.inputs])
            #datasd.cpref.inputs=['ant1h','ant1v','ant2h','ant2v','ant3h','ant3v','ant4h','ant4v','ant5h','ant5v','ant6h','ant6v']
            #ts[0] # [  1.37959922e+09   1.37959922e+09]
            [thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels]=ringbufferrequestqueue.get()
            startproctime=time.time()
            if (thelayoutsettings=='setflags'):
                datasd.storage.timeseriesmaskstr=str(','.join(theviewsettings))
                datasd.storage.timeseriesmaskind,weightedmask,datasd.storage.spectrum_flag0,datasd.storage.spectrum_flag1=sdispdata.parse_timeseries_mask(datasd.storage.timeseriesmaskstr,datasd.storage.n_chans)
                ringbufferresultqueue.put(weightedmask)
                continue
            if (thelayoutsettings=='setoutliertime'):
                datasd.storage.outliertime=theviewsettings
                continue
            if (thelayoutsettings=='getflags'):
                fig={'logconsole':'flags='+(datasd.storage.timeseriesmaskstr)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='getoutliertime'):
                fig={'logconsole':'outliertime=%g'%(datasd.storage.outliertime)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='inputs'):
                fig={'logconsole':','.join(datasd.cpref.inputs)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='override'):
                try:
                    if (theviewsettings.startswith('bandwidthMHz=')):
                        if (len(theviewsettings[13:])==0):
                            fig={'logconsole':'clear override bandwidthMHz'}
                            datasd.receiver.set_override_bandwidth(None)
                        else:
                            newval=float(theviewsettings[13:])
                            fig={'logconsole':'override set bandwidthMHz=%f'%(newval)}
                            datasd.receiver.set_override_bandwidth(newval*1e6)
                        datasd.receiver.update_center_freqs()
                    elif (theviewsettings.startswith('centerfreqMHz=')):
                        if (len(theviewsettings[14:])==0):
                            fig={'logconsole':'clear override centerfreqMHz'}
                            datasd.receiver.set_override_center_freq(None)
                        else:
                            newval=float(theviewsettings[14:])
                            fig={'logconsole':'override set centerfreqMHz=%f'%(newval)}
                            datasd.receiver.set_override_center_freq(newval*1e6)
                        datasd.receiver.update_center_freqs()
                    else:
                        fig={}
                except:
                        fig={}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='get_bls_ordering'):
                ringbufferresultqueue.put(datasd.cpref.bls_ordering)
                continue
            if (thelayoutsettings=='info'):
                try:
                    fig={'logconsole':'katsdpdisp version: '+katsdpdisp.__version__+'\nreceiver alive: '+str(datasd.receiver.isAlive())+'\nheap count: '+str(datasd.receiver.heap_count) \
                         +'\ntimeseries slots: %d\nspectrum slots: %d\nwmx slots: %d'%(datasd.storage.timeseriesslots,datasd.storage.slots,datasd.storage.blmxslots)\
                         +'\nnbaselines: '+str(len(datasd.cpref.bls_ordering))+'\ncbf_channels: '+str(datasd.receiver.cbf_channels)+'\nnchannels: '+str(datasd.receiver.channels)\
                         +'\nblmx nchannels: '+str(datasd.storage.blmxn_chans)+'\ncenter freq: '+str(datasd.receiver.center_freq)+'\nchannel bandwidth: '+str(datasd.receiver.channel_bandwidth)}
                except Exception,e:
                    logger.warning('Exception in sendfiguredata: '+str(e), exc_info=True)
                    fig={}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='memoryleak'):
                gc.collect()
                hpafter = hp.heap()
                hpleftover=hpafter-hpbefore
                logger.info('Memory usage %s (kb)'%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
                logger.info(hpleftover)
                fig={'logconsole':'Memory usage %s (kb)\n'%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)+' leftover objects= '+str(hpleftover)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='fileoffset'):
                if (datafilename is 'stream'):
                    fig={'logconsole':'This is a stream'}
                elif (theviewsettings is None):
                    fig={'logconsole':'The fileoffset for %s is %d [total %d dumps]'%(datafilename,thefileoffset,datasd.storage.h5_ndumps)}
                else:
                    thefileoffset=theviewsettings
                    dh.load_ar1_data(datafilename, rows=300, startrow=thefileoffset, capacity=memusage/100.0, max_custom_signals=max_custom_signals, store2=True, timeseriesmaskstr=datasd.storage.timeseriesmaskstr)
                    datasd=dh.sd_hist
                    fig={'logconsole':'Restarted %s at %d [total %d dumps]'%(datafilename,thefileoffset,datasd.storage.h5_ndumps)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='RESTART'):
                fig={'logconsole':'Exiting ring buffer process'}
                ringbufferresultqueue.put(fig)
                return
            if (thelayoutsettings=='sendfiguredata'):
                theindex=-1
                try:
                    if (datasd.receiver.ig['sd_data_index'].value is None):
                        data_index=[]
                    else:
                        data_index=datasd.receiver.ig['sd_data_index'].value.astype(np.uint32)
                    if (list(thesignals[0]) in [datasd.cpref.bls_ordering[ind] for ind in data_index]):
                        signal = datasd.select_data(dtype=theviewsettings, product=tuple(thesignals[0]), end_time=lastts, include_ts=False,include_flags=False)
                        signal=np.array(signal).reshape(-1)
                        theindex=datasd.cpref.bls_ordering.index(list(thesignals[0]))
                    elif (list(thesignals[0]) in datasd.cpref.bls_ordering):
                        signal='wait for signal'
                        theindex=datasd.cpref.bls_ordering.index(list(thesignals[0]))
                    else:
                        signal='signal not in bls_ordering'
                except Exception, e:
                    logger.warning('Exception in sendfiguredata: '+str(e), exc_info=True)
                    signal='error'
                    pass
                ringbufferresultqueue.put([signal, theindex])
                continue
            if (datasd.storage.frame_count==0):
                if (warnOnce):
                    fig={'logconsole':'empty signal buffer'}
                else:
                    fig={'logignore':'empty signal buffer'}
                ringbufferresultqueue.put(fig)
                warnOnce=False
                continue
            else:
                warnOnce=True

            fig={}
            try:
                thetype=typelookup[theviewsettings['type']]
                #hfeeds=datasd.cpref.inputs
                collectionsignals=thesignals[0]
                customsignals=thesignals[1]

                ts = datasd.select_timeseriesdata(products=[0], start_time=0, end_time=1e100, include_ts=True)[0]#gets all timestamps only
                ch=datasd.receiver.center_freqs_mhz[:]
                if (len(ts)>1):
                    samplingtime=ts[-1]-ts[-2]
                else:
                    samplingtime=np.nan
                if (theviewsettings['figtype']=='timeseries' or theviewsettings['figtype']=='timeseriessnr'):
                    ydata=[]
                    color=[]
                    legend=[]
                    collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                    outlierproducts=[]
                    customproducts=[]
                    for colprod in collectionsignals:
                        if (colprod[:8]=='envelope'):
                            if (colprod[8:] in collections):
                                icolprod=collections.index(colprod[8:])
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                                if (theviewsettings['figtype']=='timeseries'):
                                    cbase=registeredcolour(colprod[8:])
                                    c=np.array(np.r_[cbase,1],dtype='int')
                                    for iprod in range(2):#only min and max
                                        product=icolprod*5+iprod
                                        signal = datasd.select_timeseriesdata_collection(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False)
                                        signal=signal.reshape(-1)
                                        if (len(signal)<len(ts)):
                                            signal=np.r_[signal,np.tile(np.nan,len(ts)-len(signal))]
                                        ydata.append(signal)
                                        legend.append(colprod[8:])
                                        if (iprod==1):#note this is kindof a hack to get legend and drawing of envelopes to work
                                            c=np.array(np.r_[cbase,0],dtype='int')
                                        color.append(c)
                        else:
                            if (colprod in collections):
                                icolprod=collections.index(colprod)
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                                if (theviewsettings['figtype']=='timeseries'):
                                    cbase=registeredcolour(colprod)
                                    c=np.array(np.r_[cbase,1],dtype='int')
                                    for iprod in range(5):
                                        product=icolprod*5+iprod
                                        signal = datasd.select_timeseriesdata_collection(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False)
                                        signal=signal.reshape(-1)
                                        if (len(signal)<len(ts)):
                                            signal=np.r_[signal,np.tile(np.nan,len(ts)-len(signal))]
                                        ydata.append(signal)
                                        legend.append(colprod)
                                        if (iprod==4):
                                            c=np.array(np.r_[cbase,0],dtype='int')
                                        color.append(c)

                    for product in customsignals:
                        if (list(product) in datasd.cpref.bls_ordering):
                            customproducts.append(product)
                            if (theviewsettings['figtype']=='timeseriessnr'):
                                signal = datasd.select_timeseriesdata(dtype=thetype, products=[tuple(product)], start_time=ts[0], end_time=ts[-1], include_ts=False, source='timeseriessnrdata')
                            else:
                                signal = datasd.select_timeseriesdata(dtype=thetype, products=[tuple(product)], start_time=ts[0], end_time=ts[-1], include_ts=False)
                            signal=np.array(signal).reshape(-1)
                            if (len(signal)<len(ts)):
                                signal=np.r_[signal,np.tile(np.nan,len(ts)-len(signal))]
                        else:
                            signal=np.tile(np.nan,len(ts))
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(printablesignal(product))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    outlierhash=0
                    for ipr,product in enumerate(outlierproducts):
                        outlierhash=(outlierhash+product<<3)%(2147483647+ipr)
                        if (theviewsettings['figtype']=='timeseriessnr'):
                            signal = datasd.select_timeseriesdata(dtype=thetype, products=[product], start_time=ts[0], end_time=ts[-1], include_ts=False, source='timeseriessnrdata')
                        else:
                            signal = datasd.select_timeseriesdata(dtype=thetype, products=[product], start_time=ts[0], end_time=ts[-1], include_ts=False)
                        signal=np.array(signal).reshape(-1)
                        if (len(signal)<len(ts)):
                            signal=np.r_[signal,np.tile(np.nan,len(ts)-len(signal))]
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(datasd.cpref.id_to_real_str(id=product,short=True).replace('m00','').replace('m0','').replace('m','').replace('ant','').replace(' * ',''))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    if (len(ydata)==0):
                        ydata=[np.nan*ts]
                        color=[np.array([255,255,255,0])]
                    if (theviewsettings['type']=='pow'):
                        ydata=10.0*np.log10(ydata)
                        fig['ylabel']=['Power']
                        fig['yunit']=['dB']
                    elif (thetype=='mag'):
                        fig['ylabel']=['Amplitude']
                        fig['yunit']=['counts']
                    else:
                        fig['ylabel']=['Phase']
                        fig['yunit']=['rad']
                    fig['xunit']='s'
                    fig['xdata']=ts
                    fig['ydata']=[ydata]
                    fig['color']=np.array(color)
                    fig['legend']=legend
                    fig['outlierhash']=outlierhash
                    fig['title']='Timeseries SNR' if (theviewsettings['figtype']=='timeseriessnr') else 'Timeseries'
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xlabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['outlierproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in outlierproducts]
                    fig['customproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in customproducts]
                elif (theviewsettings['figtype'][:11]=='periodogram'):
                    if (theviewsettings['figtype'][11:].isdigit()):
                        datalength=int(theviewsettings['figtype'][11:])
                    else:
                        datalength=60
                    ydata=[]
                    color=[]
                    legend=[]
                    collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                    outlierproducts=[]
                    customproducts=[]
                    for colprod in collectionsignals:
                        if (colprod[:8]=='envelope'):
                            if (colprod[8:] in collections):
                                icolprod=collections.index(colprod[8:])
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                        else:
                            if (colprod in collections):
                                icolprod=collections.index(colprod)
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                    for product in customsignals:
                        if (list(product) in datasd.cpref.bls_ordering):
                            customproducts.append(product)
                            signal = datasd.select_timeseriesdata(dtype=thetype, products=[tuple(product)], start_time=0, end_time=-datalength, include_ts=False)
                            signal=np.array(signal).reshape(-1)
                            if (len(signal)<datalength):
                                signal=np.r_[signal,np.tile(0.0,datalength-len(signal))]
                        else:
                            signal=np.tile(np.nan,datalength)
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(printablesignal(product))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    outlierhash=0
                    for ipr,product in enumerate(outlierproducts):
                        outlierhash=(outlierhash+product<<3)%(2147483647+ipr)
                        signal = datasd.select_timeseriesdata(dtype=thetype, products=[product], start_time=0, end_time=-datalength, include_ts=False)
                        signal=np.array(signal).reshape(-1)
                        if (len(signal)<datalength):
                            signal=np.r_[signal,np.tile(0.0,datalength-len(signal))]
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(datasd.cpref.id_to_real_str(id=product,short=True).replace('m00','').replace('m0','').replace('m','').replace('ant','').replace(' * ',''))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    if (len(ydata)==0):
                        ydata=[np.tile(np.nan,datalength)]
                        color=[np.array([255,255,255,0])]
                    if (theviewsettings['type']=='pow'):
                        ydata=[10.0*np.log10(np.abs(np.fft.fft(yd))) for yd in ydata]
                        fig['ylabel']=['Power']
                        fig['yunit']=['dB']
                    elif (thetype=='mag'):
                        ydata=[np.abs(np.fft.fft(yd)) for yd in ydata]
                        fig['ylabel']=['Amplitude']
                        fig['yunit']=['counts']
                    else:
                        fig['ylabel']=['Phase']
                        fig['yunit']=['rad']
                    fig['xunit']=''
                    fig['xdata']=np.arange(datalength)
                    fig['ydata']=[ydata]
                    fig['color']=np.array(color)
                    fig['legend']=legend
                    fig['outlierhash']=outlierhash
                    fig['title']='Periodogram at '+time.asctime(time.localtime(ts[-1]))
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xlabel']='Cycles'
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['outlierproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in outlierproducts]
                    fig['customproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in customproducts]
                elif (theviewsettings['figtype'][:8]=='spectrum'):
                    #nchannels=datasd.receiver.channels
                    if (theviewsettings['figtype'][8:].isdigit()):
                        navgsamples=int(theviewsettings['figtype'][8:])
                    else:
                        navgsamples=1
                    ydata=[]
                    color=[]
                    legend=[]
                    start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                    thech_=np.arange(start_chan,stop_chan,chanincr)
                    collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                    outlierproducts=[]
                    customproducts=[]
                    flags=np.zeros(len(thech))
                    for colprod in collectionsignals:
                        if (colprod[:8]=='envelope'):
                            if (colprod[8:] in collections):
                                icolprod=collections.index(colprod[8:])
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                                cbase=registeredcolour(colprod[8:])
                                c=np.array(np.r_[cbase,1],dtype='int')
                                for iprod in range(2):
                                    product=icolprod*5+iprod
                                    signal,theflags = datasd.select_data_collection(dtype=thetype, product=product, end_time=-navgsamples, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr,avg_axis=(0 if (navgsamples>1) else None))
                                    flags=np.logical_or(flags,theflags.reshape(-1))
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod[8:])
                                    if (iprod==1):#note this is kindof a hack to get legend and drawing of envelopes to work
                                        c=np.array(np.r_[cbase,0],dtype='int')
                                    color.append(c)
                        else:
                            if (colprod in collections):
                                icolprod=collections.index(colprod)
                                moreoutlierproducts=datasd.get_data_outlier_products(icollection=icolprod, threshold=thelayoutsettings['outlierthreshold'])
                                for ip in moreoutlierproducts:
                                    if (ip not in outlierproducts and ip not in customsignals):
                                        outlierproducts.append(ip)
                                cbase=registeredcolour(colprod)
                                c=np.array(np.r_[cbase,1],dtype='int')
                                for iprod in range(5):
                                    product=icolprod*5+iprod
                                    signal,theflags = datasd.select_data_collection(dtype=thetype, product=product, end_time=-navgsamples, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr,avg_axis=(0 if (navgsamples>1) else None))
                                    flags=np.logical_or(flags,theflags.reshape(-1))
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod)
                                    if (iprod==4):
                                        c=np.array(np.r_[cbase,0],dtype='int')
                                    color.append(c)

                    for product in customsignals:
                        if (list(product) in datasd.cpref.bls_ordering):
                            customproducts.append(product)
                            signal,theflags = datasd.select_data(dtype=thetype, product=tuple(product), end_time=-navgsamples, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr,avg_axis=(0 if (navgsamples>1) else None))
                            flags=np.logical_or(flags,theflags.reshape(-1))
                            signal=np.array(signal).reshape(-1)
                        else:
                            signal=np.nan*np.ones(len(thech))
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(printablesignal(product))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    for product in outlierproducts:
                        signal,theflags = datasd.select_data(dtype=thetype, product=product, end_time=-navgsamples, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr,avg_axis=(0 if (navgsamples>1) else None))
                        flags=np.logical_or(flags,theflags.reshape(-1))
                        signal=np.array(signal).reshape(-1)
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(datasd.cpref.id_to_real_str(id=product,short=True).replace('m00','').replace('m0','').replace('m','').replace('ant','').replace(' * ',''))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    span=[]
                    spancolor=[]
                    if (thelayoutsettings['showonlineflags']=='on'):
                        onlineflags=[]
                        chanwidth=len(thech)-1
                        flagstart=0
                        flagstop=0
                        halfchanwidthmhz=abs(ch[0]-ch[1])/2.0
                        while (flagstop<chanwidth):
                            flagstart=flagstop
                            while (flagstart<chanwidth and flags[flagstart]==0):
                                flagstart+=1
                            flagstop=flagstart
                            while (flagstop<chanwidth and flags[flagstop]!=0):
                                flagstop+=1
                            if (theviewsettings['xtype']=='mhz'):
                                onlineflags.append([thech[flagstart]-halfchanwidthmhz,thech[flagstop]-halfchanwidthmhz])
                            elif (theviewsettings['xtype']=='ghz'):
                                onlineflags.append([(thech[flagstart]-halfchanwidthmhz)/1e3,(thech[flagstop]-halfchanwidthmhz)/1e3])
                            else:
                                onlineflags.append([thech_[flagstart]-0.5,thech_[flagstop]-0.5])
                        span.append(onlineflags)
                        spancolor.append([200,200,0,128])

                    if (len(ydata)==0):
                        ydata=[np.tile(np.nan,len(thech))]
                        color=[np.array([255,255,255,0])]
                    if (theviewsettings['type']=='pow'):
                        ydata=10.0*np.log10(ydata)
                        fig['ylabel']=['Power']
                        fig['yunit']=['dB']
                    elif (thetype=='mag'):
                        fig['ylabel']=['Amplitude']
                        fig['yunit']=['counts']
                    else:
                        fig['ylabel']=['Phase']
                        fig['yunit']=['rad']
                    fig['ydata']=[ydata]
                    fig['color']=np.array(color)
                    fig['legend']=legend
                    fig['outlierhash']=0
                    if (navgsamples>1):
                        fig['title']='Spectrum (avg %d) at '%(navgsamples)+time.asctime(time.localtime(ts[-1]))
                    else:
                        fig['title']='Spectrum at '+time.asctime(time.localtime(ts[-1]))
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    if (theviewsettings['xtype']=='mhz'):
                        fig['xdata']=thech
                        fig['xlabel']='Frequency'
                        fig['xunit']='MHz'
                        if (thelayoutsettings['showflags']=='on' and len(datasd.storage.spectrum_flag0)):
                            spancolor.append([255,0,0,128])
                            span.append([[ch[datasd.storage.spectrum_flag0[a]],ch[datasd.storage.spectrum_flag1[a]]] for a in range(len(datasd.storage.spectrum_flag0))])
                    elif (theviewsettings['xtype']=='ghz'):
                        fig['xdata']=np.array(thech)/1e3
                        fig['xlabel']='Frequency'
                        fig['xunit']='GHz'
                        if (thelayoutsettings['showflags']=='on' and len(datasd.storage.spectrum_flag0)):
                            spancolor.append([255,0,0,128])
                            span.append([[ch[datasd.storage.spectrum_flag0[a]]/1e3,ch[datasd.storage.spectrum_flag1[a]]/1e3] for a in range(len(datasd.storage.spectrum_flag0))])
                    else:
                        fig['xdata']=thech_
                        fig['xlabel']='Channel number'
                        fig['xunit']=''
                        if (thelayoutsettings['showflags']=='on' and len(datasd.storage.spectrum_flag0)):
                            spancolor.append([255,0,0,128])
                            span.append([[datasd.storage.spectrum_flag0[a],datasd.storage.spectrum_flag1[a]] for a in range(len(datasd.storage.spectrum_flag0))])

                    fig['spancolor']=np.array(spancolor)
                    fig['span']=span
                    fig['outlierproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in outlierproducts]
                    fig['customproducts']=[sig if isinstance(sig,int) else datasd.cpref.bls_ordering.index(list(sig)) for sig in customproducts]
                elif (theviewsettings['figtype'][:9]=='waterfall'):
                    start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                    collections=['auto0','auto100','auto25','auto75','auto50','autohh0','autohh100','autohh25','autohh75','autohh50','autovv0','autovv100','autovv25','autovv75','autovv50','autohv0','autohv100','autohv25','autohv75','autohv50','cross0','cross100','cross25','cross75','cross50','crosshh0','crosshh100','crosshh25','crosshh75','crosshh50','crossvv0','crossvv100','crossvv25','crossvv75','crossvv50','crosshv0','crosshv100','crosshv25','crosshv75','crosshv50']
                    collectionsalt=['automin','automax','auto25','auto75','auto','autohhmin','autohhmax','autohh25','autohh75','autohh','autovvmin','autovvmax','autovv25','autovv75','autovv','autohvmin','autohvmax','autohv25','autohv75','autohv','crossmin','crossmax','cross25','cross75','cross','crosshhmin','crosshhmax','crosshh25','crosshh75','crosshh','crossvvmin','crossvvmax','crossvv25','crossvv75','crossvv','crosshvmin','crosshvmax','crosshv25','crosshv75','crosshv']
                    typestr=theviewsettings['figtype'][9:].split('delay')
                    productstr=typestr[0]
                    usingblmxdata=False
                    if (lastrecalc<theviewsettings['version']):
                        start_time=0
                        end_time=-120
                    else:
                        start_time=lastts+0.01
                        end_time=ts[-1]+0.01
                    if (thelayoutsettings['showonlineflags']=='on'):#more efficient to separate these out
                        flags=0
                        if (productstr in collections):
                            product=collections.index(productstr)
                            productstr=collectionsalt[product]
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                            flags=np.logical_or(flags,rvcdata[2])
                        elif (productstr in collectionsalt):
                            product=collectionsalt.index(productstr)
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                            flags=np.logical_or(flags,rvcdata[2])
                        else:
                            product=decodecustomsignal(productstr)
                            if (chanincr>15 and list(product) in datasd.cpref.bls_ordering):#test
                                usingblmxdata=True
                                reduction=datasd.storage.n_chans/datasd.storage.blmxn_chans
                                thech=ch[start_chan:stop_chan:reduction]
                                newchanincr=chanincr/reduction
                                if (newchanincr<1):
                                    newchanincr=1
                                rvcdata = datasd.select_blmxdata(dtype=thetype, product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=True,start_channel=start_chan/reduction,stop_channel=stop_chan/reduction,incr_channel=newchanincr)
                                limitedts=datasd.select_blmxdata(dtype=thetype, product=tuple(product), end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                flags=np.logical_or(flags,rvcdata[2])
                            elif (list(product) in datasd.cpref.bls_ordering):
                                rvcdata = datasd.select_data(dtype=thetype, product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                                limitedts=datasd.select_data(dtype=thetype, product=tuple(product), end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                flags=np.logical_or(flags,rvcdata[2])
                            else:
                                thets=datasd.select_data(product=0, start_time=start_time, end_time=end_time, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                limitedts=thets
                                rvcdata=[thets,np.nan*np.ones([len(thets),len(thech)])]

                        if (len(rvcdata[0])==1):#reshapes in case one time dump of data (select data changes shape)
                            rvcdata[1]=np.array([rvcdata[1]])
                            flags=np.array([flags])

                        cdata=np.array(rvcdata[1])
                        if (len(np.shape(flags))>0):
                            shp=np.shape(cdata)
                            tmp=cdata.reshape(-1)
                            tmp[np.nonzero(flags.reshape(-1))[0]]=np.nan;
                            cdata=tmp.reshape(shp)
                    else:
                        if (productstr in collections):
                            product=collections.index(productstr)
                            productstr=collectionsalt[product]
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                        elif (productstr in collectionsalt):
                            product=collectionsalt.index(productstr)
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                        else:
                            product=decodecustomsignal(productstr)
                            if (chanincr>15 and list(product) in datasd.cpref.bls_ordering):#test
                                usingblmxdata=True
                                reduction=datasd.storage.n_chans/datasd.storage.blmxn_chans
                                thech=ch[start_chan:stop_chan:reduction]
                                newchanincr=chanincr/reduction
                                if (newchanincr<1):
                                    newchanincr=1
                                rvcdata = datasd.select_blmxdata(dtype=thetype, product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan/reduction,stop_channel=stop_chan/reduction,incr_channel=newchanincr)
                                limitedts=datasd.select_blmxdata(dtype=thetype, product=tuple(product), end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                            elif (list(product) in datasd.cpref.bls_ordering):
                                rvcdata = datasd.select_data(dtype=thetype, product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                                limitedts=datasd.select_data(dtype=thetype, product=tuple(product), end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                            else:
                                thets=datasd.select_data(product=0, start_time=start_time, end_time=end_time, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                limitedts=thets
                                rvcdata=[thets,np.nan*np.ones([len(thets),len(thech)])]

                        if (len(rvcdata[0])==1):#reshapes in case one time dump of data (select data changes shape)
                            rvcdata[1]=np.array([rvcdata[1]])
                        cdata=np.array(rvcdata[1])

                    if (theviewsettings['type']=='pow'):
                        cdata=10.0*np.log10(cdata)
                        fig['clabel']='Power'
                        fig['cunit']='dB'
                    elif (thetype=='mag'):
                        fig['clabel']='Amplitude'
                        fig['cunit']='counts'
                    else:
                        fig['clabel']='Phase'
                        fig['cunit']='rad'
                        if (cdata.shape[0]>0 and len(typestr)>1):
                            cdata=np.angle(np.exp(1j*(cdata+2.0*np.pi*float(typestr[1])*1e-9*np.array(ch[start_chan:stop_chan:chanincr])*1e6)))
                    fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['yunit']='s'
                    fig['cdata']=cdata
                    fig['ydata']=np.array(limitedts)
                    fig['legend']=[]
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['title']='Waterfall '+productstr+(' with %sns delay'%(typestr[1]) if (len(typestr)>1) else '')
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    if (theviewsettings['xtype']=='mhz'):
                        fig['xdata']=thech
                        fig['xlabel']='Frequency'
                        fig['xunit']='MHz'
                    elif (theviewsettings['xtype']=='ghz'):
                        fig['xdata']=np.array(thech)/1e3
                        fig['xlabel']='Frequency'
                        fig['xunit']='GHz'
                    else:
                        fig['xdata']=np.arange(start_chan,stop_chan,chanincr)
                        fig['xlabel']='Channel number'
                        fig['xunit']=''
                    fig['outlierproducts']=[]
                    if (usingblmxdata):
                        fig['customproducts']=[]
                    elif (isinstance(product,int)):
                        fig['customproducts']=[product]
                    elif (list(product) in datasd.cpref.bls_ordering):
                        fig['customproducts']=[datasd.cpref.bls_ordering.index(list(product))]
                    else:
                        fig['customproducts']=[]
                elif (theviewsettings['figtype'][:3]=='lag'):
                    start_chan=0;stop_chan=len(ch);chanincr=1
                    collections=['auto0','auto100','auto25','auto75','auto50','autohh0','autohh100','autohh25','autohh75','autohh50','autovv0','autovv100','autovv25','autovv75','autovv50','autohv0','autohv100','autohv25','autohv75','autohv50','cross0','cross100','cross25','cross75','cross50','crosshh0','crosshh100','crosshh25','crosshh75','crosshh50','crossvv0','crossvv100','crossvv25','crossvv75','crossvv50','crosshv0','crosshv100','crosshv25','crosshv75','crosshv50']
                    collectionsalt=['automin','automax','auto25','auto75','auto','autohhmin','autohhmax','autohh25','autohh75','autohh','autovvmin','autovvmax','autovv25','autovv75','autovv','autohvmin','autohvmax','autohv25','autohv75','autohv','crossmin','crossmax','cross25','cross75','cross','crosshhmin','crosshhmax','crosshh25','crosshh75','crosshh','crossvvmin','crossvvmax','crossvv25','crossvv75','crossvv','crosshvmin','crosshvmax','crosshv25','crosshv75','crosshv']
                    typestr=theviewsettings['figtype'][3:].split('delay')
                    productstr=typestr[0]
                    usingblmxdata=False
                    if (lastrecalc<theviewsettings['version']):
                        start_time=0
                        end_time=-120
                    else:
                        start_time=lastts+0.01
                        end_time=ts[-1]+0.01
                    if (productstr in collections):
                        product=collections.index(productstr)
                        productstr=collectionsalt[product]
                        rvcdata = datasd.select_data_collection(dtype='phase', product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                        limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                    elif (productstr in collectionsalt):
                        product=collectionsalt.index(productstr)
                        rvcdata = datasd.select_data_collection(dtype='phase', product=product, start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                        limitedts=datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                    else:
                        product=decodecustomsignal(productstr)
                        if (chanincr>15 and list(product) in datasd.cpref.bls_ordering):#test
                            usingblmxdata=True
                            reduction=datasd.storage.n_chans/datasd.storage.blmxn_chans
                            thech=ch[start_chan:stop_chan:reduction]
                            newchanincr=chanincr/reduction
                            if (newchanincr<1):
                                newchanincr=1
                            rvcdata = datasd.select_blmxdata(dtype='phase', product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan/reduction,stop_channel=stop_chan/reduction,incr_channel=newchanincr)
                            limitedts=datasd.select_data_blmxdata(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                        elif (list(product) in datasd.cpref.bls_ordering):
                            rvcdata = datasd.select_data(dtype='phase', product=tuple(product), start_time=start_time, end_time=end_time, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            limitedts=datasd.select_data(dtype=thetype, product=product, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                        else:
                            thets=datasd.select_data(product=0, start_time=start_time, end_time=end_time, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                            limitedts=thets
                            rvcdata=[thets,np.nan*np.ones([len(thets),len(thech)])]

                    if (len(rvcdata[0])==1):#reshapes in case one time dump of data (select data changes shape)
                        rvcdata[1]=np.array([rvcdata[1]])
                    cdata=np.array(rvcdata[1])
                    bw=datasd.storage.n_chans*datasd.receiver.channel_bandwidth
                    if (cdata.shape[0]>0):
                        if (len(typestr)>1):
                            cdata=np.exp(1j*(cdata+2.0*np.pi*float(typestr[1])*1e-9*np.array(ch[start_chan:stop_chan:chanincr])*1e6))
                        else:
                            cdata=np.exp(1j*cdata)
                        cdata=np.fft.fftshift(np.fft.fft2(cdata,axes=[1]),axes=1)
                        start_lag,stop_lag,lagincr,thelag=getstartstopchannels((np.arange(len(ch))-len(ch)/2)/bw,'mhz',theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                        cdata=cdata[:,start_lag:stop_lag:lagincr]
                    if (theviewsettings['type']=='pow'):
                        cdata=10.0*np.log10(np.abs(cdata))
                        fig['clabel']='Power'
                        fig['cunit']='dB'
                    elif (thetype=='mag'):
                        cdata=np.abs(cdata)
                        fig['clabel']='Amplitude'
                        fig['cunit']='counts'
                    else:
                        cdata=np.angle(cdata)
                        fig['clabel']='Phase'
                        fig['cunit']='rad'
                    fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['yunit']='s'
                    fig['cdata']=cdata
                    fig['ydata']=np.array(limitedts)
                    fig['legend']=[]
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['title']='Lag '+productstr+(' with %sns delay'%(typestr[1]) if (len(typestr)>1) else '')
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xdata']=thelag
                    fig['xlabel']='Delay (%.3fns samples, bandwidth %.1fMHz)'%(1.0/bw*1e9,bw/1e6)
                    fig['xunit']='s'
                    fig['outlierproducts']=[]
                    if (usingblmxdata):
                        fig['customproducts']=[]
                    elif (isinstance(product,int)):
                        fig['customproducts']=[product]
                    elif (list(product) in datasd.cpref.bls_ordering):
                        fig['customproducts']=[datasd.cpref.bls_ordering.index(list(product))]
                    else:
                        fig['customproducts']=[]
                elif (theviewsettings['figtype']=='flagcount'):
                    antennas=np.unique([inputname[:-1] for inputname in datasd.cpref.inputs]).tolist()
                    products=[]
                    for ant in antennas:
                        products.append((ant+'h',ant+'h'))
                        products.append((ant+'v',ant+'v'))
                    theflags = datasd.select_timeseriesdata(products=products, dtype=None, end_time=-1, include_ts=False, source='timeseriesflagfractiondata')
                    flagdata=0.5*(theflags[::2]+theflags[1::2])

                    fig['title']='Flag count at '+time.asctime(time.localtime(ts[-1]))
                    fig['clabel']='Amplitude'
                    fig['cunit']='counts'
                    fig['ylabel']='Autocorrelation channels'
                    fig['yunit']='%'
                    fig['flagdata']=flagdata
                    fig['ydata']=[]
                    fig['xdata']=np.array([0,1])
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    legend=[]
                    for inp in datasd.cpref.inputs:
                        if (inp[-1]=='h'):
                            legend.append(str(int(inp[1:-1])))
                    fig['legendx']=legend
                    fig['legendy']=['res0','static','cam','lost','ingest','predict','cal','res7']
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xdata']=[]
                    fig['xlabel']=''
                    fig['xunit']=''
                    fig['outlierproducts']=[]
                    fig['customproducts']=[]
                elif (theviewsettings['figtype']=='flagmx'):
                    antennas=np.unique([inputname[:-1] for inputname in datasd.cpref.inputs]).tolist()
                    products=[]
                    for iant in antennas:
                        products.append((iant+'h',iant+'h'))
                        products.append((iant+'v',iant+'v'))
                    for ii,iant in enumerate(antennas):
                        for jant in antennas[ii+1:]:
                            products.append((iant+'h',jant+'h'))
                            products.append((iant+'v',jant+'v'))
                    fig['title']='Ingest flags baseline matrix H\\V'
                    mxdata=datasd.select_timeseriesdata(products=products, dtype='mag', end_time=-1, include_ts=False, source='timeseriesflagfractiondata')
                    mxdatahh=mxdata[::2,4]*100
                    mxdatavv=mxdata[1::2,4]*100
                    fig['clabel']='flagged channels'
                    fig['cunit']='%'
                    fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['yunit']='s'
                    fig['mxdatavv']=mxdatavv
                    fig['mxdatahh']=mxdatahh
                    fig['ydata']=[]
                    fig['xdata']=np.array([0,1])
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    legend=[]
                    for inp in datasd.cpref.inputs:
                        if (inp[-1]=='h'):
                            legend.append(str(int(inp[1:-1])))
                    fig['legendx']=legend
                    fig['legendy']=legend
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xdata']=[]
                    fig['xlabel']=''
                    fig['xunit']=''
                    fig['outlierproducts']=[]
                    fig['customproducts']=[]
                elif (theviewsettings['figtype'][:4]=='blmx'):
                    antennas=np.unique([inputname[:-1] for inputname in datasd.cpref.inputs]).tolist()
                    products=[]
                    for iant in antennas:
                        products.append((iant+'h',iant+'h'))
                        products.append((iant+'v',iant+'v'))
                    for ii,iant in enumerate(antennas):
                        for jant in antennas[ii+1:]:
                            products.append((iant+'h',jant+'h'))
                            products.append((iant+'v',jant+'v'))
                    if (theviewsettings['figtype'][4:]=='snr'):
                        fig['title']='Baseline matrix SNR H\\V'
                        mxdata=datasd.select_timeseriesdata(products=products, dtype='mag', end_time=-1, include_ts=False, source='timeseriessnrdata')
                    else:
                        fig['title']='Baseline matrix mean H\\V'
                        mxdata=datasd.select_timeseriesdata(products=products, dtype='mag', end_time=-1, include_ts=False, source='timeseriesdata')
                    mxdatahh=mxdata[::2]
                    mxdatavv=mxdata[1::2]
                    if (theviewsettings['type']=='pow'):
                        mxdatahh=10.0*np.log10(mxdatahh)
                        mxdatavv=10.0*np.log10(mxdatavv)
                        fig['clabel']='Power'
                        fig['cunit']='dB'
                    elif (thetype=='mag'):
                        fig['clabel']='Amplitude'
                        fig['cunit']='counts'
                    else:
                        fig['clabel']='Phase'
                        fig['cunit']='deg'
                    fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['yunit']='s'
                    fig['mxdatavv']=mxdatavv
                    fig['mxdatahh']=mxdatahh
                    fig['ydata']=[]
                    fig['xdata']=np.array([0,1])
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    legend=[]
                    for inp in datasd.cpref.inputs:
                        if (inp[-1]=='h'):
                            legend.append(str(int(inp[1:-1])))
                    fig['legendx']=legend
                    fig['legendy']=legend
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['xdata']=[]
                    fig['xlabel']=''
                    fig['xunit']=''
                    fig['outlierproducts']=[]
                    fig['customproducts']=[]
                else:
                    fig={}
            except Exception, e:
                logger.warning('Exception in RingBufferProcess: '+str(e), exc_info=True)
                fig={}
                pass
            if (fig!={}):
                fig['processtime']=time.time()-startproctime

            ringbufferresultqueue.put(fig)

    except KeyboardInterrupt:
        logger.warning('^C received, shutting down the ringbuffer process')


html_customsignals= {'default': [],
                    'inspectauto': [],
                    'inspectcross': [],
                    'envelopeauto': [],
                    'envelopes': [],
                    }
html_collectionsignals= {'default': ['auto'],
                        'inspectauto': ['auto'],
                        'inspectcross': ['cross'],
                        'envelopeauto': ['envelopeautohh','envelopeautovv'],
                        'envelopes': ['envelopeauto','envelopeautohv','envelopecross','envelopecrosshv'],
                        }
html_layoutsettings= {'default': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'inspectauto': {'ncols':3,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'inspectcross': {'ncols':3,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'envelopeauto': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                      'envelopes': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                        }
html_viewsettings={'default':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0}
                             ],
                    'inspectauto':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                     {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                     {'figtype':'waterfallauto' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0}
                                  ],
                    'inspectcross':[ {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                     {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                     {'figtype':'waterfallcross' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0}
                                  ],
                    'envelopeauto':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                      {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0}
                                   ],
                    'envelopes':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0},
                                   {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0}
                                ]
                  }

help_dict={}
websockrequest_time = {}
websockrequest_username = {}
new_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[]}


ingest_signals={}
failed_update_ingest_signals_lastts=0

#adds or removes custom signals requested from ingest
#if an outlier signal is detected the intention is that it keeps being transmitted for at least a minute
def UpdateCustomSignals(handlerkey,customproducts,outlierproducts,lastts):
    global failed_update_ingest_signals_lastts
    global ingest_signals
    if (opts.datafilename is not 'stream'):
        return
    if (failed_update_ingest_signals_lastts==lastts):
        return
    #remove stale items
    timenow=time.time()
    changed=False
    revert_ingest_signals=copy.deepcopy(ingest_signals)
    for sig in ingest_signals.keys():
        if (timenow-ingest_signals[sig])>60.0 and (sig not in customproducts) and (sig not in outlierproducts):
            del ingest_signals[sig]
            changed=True
    for sig in customproducts:
        if sig not in ingest_signals.keys():
            changed=True
        ingest_signals[sig]=time.time()
    for sig in outlierproducts:
        if sig not in ingest_signals.keys():
            changed=True
        ingest_signals[sig]=time.time()
    if (len(ingest_signals)>opts.max_custom_signals):
        logger.debug('Number of customsignals %d exceeds %d:'%(len(ingest_signals),opts.max_custom_signals))
        sigs=ingest_signals.keys()
        times=[ingest_signals[sig] for sig in sigs]
        sind=np.argsort(times)
        for ind in sind[opts.max_custom_signals:]:
            del ingest_signals[sigs[ind]]
    if (changed):
        ####set custom signals on ingest
        thecustomsignals = np.array(sorted(ingest_signals.keys()), dtype=np.uint32)
        logger.debug('Trying to set customsignals to:'+repr(thecustomsignals))
        try:
            result=telstate_l0.add('sdisp_custom_signals',thecustomsignals)
            logger.debug('telstate set custom signals result: '+repr(result))
            if (handlerkey is not None):
                send_websock_cmd('logconsole("Set custom signals to '+','.join([str(sig) for sig in thecustomsignals])+'",true,false,true)',handlerkey)
        except Exception, e:
            logger.warning("Exception while telstate set custom signals: (" + str(e) + ")", exc_info=True)
            if (handlerkey is not None):
                send_websock_cmd('logconsole("Server exception occurred evaluating set custom signals",true,false,true)',handlerkey)
            ingest_signals=revert_ingest_signals
            failed_update_ingest_signals_lastts=lastts

def logusers(handlerkey):
    try:
        startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
        startupdictstr=startupfile.read()
        startupfile.close()
    except:
        startupdictstr=''
        pass
    if (len(startupdictstr)>0):
        startupdict=convertunicode(json.loads(startupdictstr))
        send_websock_cmd('logconsole("'+str(len(startupdict['html_viewsettings']))+' saved: '+','.join(startupdict['html_viewsettings'].keys())+'",true,false,false)',handlerkey)
    else:
        startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
        send_websock_cmd('logconsole("0 saved",true,false,false)',handlerkey)
    inactive=[]
    zombie=[]
    zombiecount=[]
    active=[]
    activeproctime=[]
    activetime=[]
    nactive=0
    totalactiveproctime=0.0
    for usrname in html_viewsettings.keys():
        if (usrname not in websockrequest_username.values()):
            inactive.append(usrname)
    for thishandler in websockrequest_username.keys():
        usrname=websockrequest_username[thishandler]
        timedelay=(time.time()-websockrequest_time[thishandler])
        proctime=0
        for fig in html_viewsettings[usrname]:
            proctime+=fig['processtime']
        if (timedelay<60):
            totalactiveproctime+=proctime
            nactive+=1
            if (usrname in active):
                activeproctime[active.index(usrname)]+=proctime
                activetime[active.index(usrname)].append(timedelay)
            else:
                active.append(usrname)
                activeproctime.append(proctime)
                activetime.append([timedelay])
        else:
            if (usrname in zombie):
                zombiecount[zombie.index(usrname)]+=1
            else:
                zombie.append(usrname)
                zombiecount.append(1)
    send_websock_cmd('logconsole("'+str(len(inactive))+' inactive: '+','.join(inactive)+'",true,true,true)',handlerkey)
    if (len(zombie)>0):
        send_websock_cmd('logconsole("'+str(np.sum(zombiecount))+' zombie (use memoryleak to remove): '+','.join([zombie[iz]+':%d'%zombiecount[iz] for iz in range(len(zombie))])+'",true,true,true)',handlerkey)
    else:
        send_websock_cmd('logconsole("0 zombie",true,true,true)',handlerkey)
    send_websock_cmd('logconsole("'+str(nactive)+' active using %.1fms proc time (use kick to deactivate or send message): ",true,true,true)'%(totalactiveproctime*1000.0),handlerkey)
    for iz in np.argsort(activeproctime)[::-1]:
        send_websock_cmd('logconsole("[proc %.1fms] %s: '%(activeproctime[iz]*1000.0,active[iz])+','.join(['%.1fs'%(tm) for tm in activetime[iz]])+' ago",true,true,true)',handlerkey)

#parse e.g. 3..5,7..,8,..3
#keeps order of selection
def parse_antennarange(selectstr):
    ants=[]
    for elem in selectstr.replace(' ','').split(','):
        vals=elem.split('..')
        if (len(vals)==1):#7
            if (vals[0].isdigit() and 'm%03d'%(int(vals[0])) in telstate_antenna_mask):
                if (int(vals[0]) not in ants):
                    ants.append(int(vals[0]))
        elif(len(vals)==2):
            if (vals[0]=='' and (vals[1].isdigit())):#..3
                for ant in range(int(vals[1])+1):#include specified end too
                    if ((ant not in ants) and ('m%03d'%(ant) in telstate_antenna_mask)):
                        ants.append(ant)
            elif (vals[1]=='' and (vals[0].isdigit())):#7..
                for ant in range(int(vals[0]),64):
                    if ((ant not in ants) and ('m%03d'%(ant) in telstate_antenna_mask)):
                        ants.append(ant)
            elif (vals[0].isdigit() and vals[1].isdigit()):#3..5
                for ant in range(int(vals[0]),int(vals[1])+1):
                    if ((ant not in ants) and ('m%03d'%(ant) in telstate_antenna_mask)):
                        ants.append(ant)
    return ants

def handle_websock_event(handlerkey,*args):
    global poll_telstate_lasttime
    global telstate_cal_product_G
    global telstate_cal_product_K
    global telstate_cal_product_B
    global telstate_cal_antlist
    global telstate_cbf_target
    global telstate_antenna_mask
    global telstate_activity
    global telstate_script_name
    global scriptnametext
    try:
        username=websockrequest_username[handlerkey]
        if (args[0]=='setusername' and username!=args[1]):
            websockrequest_username[handlerkey]=args[1]
            logger.info(repr(args))
            if (args[1] not in html_viewsettings):
                html_viewsettings[args[1]]=copy.deepcopy(html_viewsettings['default'])
            if (args[1] not in html_customsignals):
                html_customsignals[args[1]]=copy.deepcopy(html_customsignals['default'])
            if (args[1] not in html_collectionsignals):
                html_collectionsignals[args[1]]=copy.deepcopy(html_collectionsignals['default'])
            if (args[1] not in html_layoutsettings):
                html_layoutsettings[args[1]]=copy.deepcopy(html_layoutsettings['default'])
            send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[args[1]]])+'"]'+','+str(html_layoutsettings[args[1]]['ncols'])+')',handlerkey)
            send_websock_cmd('document.getElementById("scriptnametext").innerHTML="'+scriptnametext+'";',handlerkey)
        elif (username not in html_viewsettings):
            logger.info('Warning: unrecognised username:'+username)
        elif (args[0]=='sendfiguredata'):
            logger.info(repr(args))
            reqts=float(args[1])#eg -1
            chan0=int(args[2])
            chan1=int(args[3])
            thetype=str(args[4]) #'re','im','mag','phase'
            product=decodecustomsignal(str(args[5])) #e.g. args[5]='1h1h' product=('ant1h','ant1h')
            logger.info('decoded product: '+repr(product))
            thesignals=[product]
            if (product not in html_customsignals[username]):
                html_customsignals[username].append(product)
            for itry in range(5): #note this may fail perpetually if datacapture has stopped
                with RingBufferLock:
                    ringbufferrequestqueue.put(['sendfiguredata',thetype,thesignals,reqts,0,0])
                    spectrum,dataindex=ringbufferresultqueue.get()
                if (type(spectrum)==str and spectrum == 'wait for signal' and dataindex>=0):
                    UpdateCustomSignals(None,[dataindex],[],reqts)
                    time.sleep(1)
                else:
                    break
            if (type(spectrum)!=str and chan1>0 and chan0>0):
                send_websock_data(repr(spectrum[chan0:chan1]),handlerkey);
            else:
                send_websock_data(repr(spectrum),handlerkey);
        elif (args[0]=='sendfigure'):
            ifigure=int(args[1])
            reqts=float(args[2])# timestamp on browser side when sendfigure request was issued
            lastts=float(args[3])# np.round(float(args[3])*1000.0)/1000.0
            lastrecalc=float(args[4])
            view_npixels=int(args[5])
            outlierhash=int(args[6])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                logger.warning('Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure))
                return
            if (view_npixels<64):
                view_npixels=64
            theviewsettings=html_viewsettings[username][ifigure]
            thesignals=(html_collectionsignals[username],html_customsignals[username])
            thelayoutsettings=html_layoutsettings[username]
            if (theviewsettings['figtype']=='timeseries' or theviewsettings['figtype']=='timeseriessnr'):
                customproducts,outlierproducts,processtime=send_timeseries(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('periodogram')):
                customproducts,outlierproducts,processtime=send_periodogram(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('spectrum')):
                customproducts,outlierproducts,processtime=send_spectrum(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('waterfall')):
                customproducts,outlierproducts,processtime=send_waterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('lag')):
                customproducts,outlierproducts,processtime=send_lag(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('flagcount')):
                customproducts,outlierproducts,processtime=send_flagcount(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('flagmx')):
                customproducts,outlierproducts,processtime=send_blmx(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('blmx')):
                customproducts,outlierproducts,processtime=send_blmx(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('bandpass')):
                customproducts,outlierproducts,processtime=send_bandpass(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('gainwaterfall')):
                customproducts,outlierproducts,processtime=send_gainwaterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('gain')):
                customproducts,outlierproducts,processtime=send_gain(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'].startswith('delay')):
                customproducts,outlierproducts,processtime=send_gain(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure,dodelay=True)
            html_viewsettings[username][ifigure]['processtime']=processtime
            UpdateCustomSignals(handlerkey,customproducts,outlierproducts,lastts)
        elif (args[0]=='setzoom'):
            logger.info(repr(args))
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                logger.warning('Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure))
                return
            theviewsettings=html_viewsettings[username][ifigure]

            theviewsettings['xmin']=float(args[2])
            theviewsettings['xmax']=float(args[3])
            theviewsettings['ymin']=float(args[4])
            theviewsettings['ymax']=float(args[5])
            theviewsettings['cmin']=float(args[6])
            theviewsettings['cmax']=float(args[7])
            theviewsettings['version']+=1
        elif (args[0]=='setfigparam'):
            logger.info(repr(args))
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                logger.warning('Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure))
                return
            theviewsettings=html_viewsettings[username][ifigure]
            theviewsettings[args[2]]=str(args[3])
            if (args[2]=='type'):
                theviewsettings['ymin']=np.nan
                theviewsettings['ymax']=np.nan
            elif (args[2]=='xtype'):
                theviewsettings['xmin']=np.nan
                theviewsettings['xmax']=np.nan
            theviewsettings['version']+=1

        elif (args[0]=='deletefigure'):
            logger.info(repr(args))
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                logger.warning('Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure))
                return
            html_viewsettings[username].pop(ifigure)
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='setncols'):
            logger.info(repr(args))
            html_layoutsettings[username]['ncols']=int(args[1])
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='getoutlierthreshold'):
            logger.info(repr(args))
            send_websock_cmd('logconsole("outlierthreshold=%g'%(html_layoutsettings[username]['outlierthreshold'])+'",true,true,true)',handlerkey)
        elif (args[0]=='getoutliertime'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['getoutliertime',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating getoutliertime",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)
        elif (args[0]=='getflags'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['getflags',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating getflags",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)
            try:
                flagfile=open(SETTINGS_PATH+'/userflags.json','r')
                flagdictstr=flagfile.read()
                flagfile.close()
            except:
                flagdictstr=''
                pass
            if (len(flagdictstr)>0):
                flagdict=convertunicode(json.loads(flagdictstr))
                send_websock_cmd('logconsole("'+str(len(flagdict))+' flags saved:",true,true,true)',handlerkey)
                for key in flagdict.keys():
                    send_websock_cmd('logconsole("'+key+'='+flagdict[key]+'",true,true,true)',handlerkey)
            else:
                send_websock_cmd('logconsole("0 flags saved",true,true,true)',handlerkey)
        elif (args[0]=='setoutlierthreshold'):
            logger.info(repr(args))
            html_layoutsettings[username]['outlierthreshold']=float(args[1])
        elif (args[0]=='setoutliertime'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['setoutliertime',float(args[1]),0,0,0,0])
        elif (args[0]=='flagcount'):
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'flagcount' ,'type':'mag','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='flagmx'):
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'flagmx' ,'type':'mag','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='blmx'):
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'blmx'+str(args[1]) ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='gainwaterfall'):
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'gainwaterfall' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('wmx') and (args[0].startswith('wmxhh') or args[0].startswith('wmxhv') or args[0].startswith('wmxvh') or args[0].startswith('wmxvv'))):
            logger.info(repr(args))
            antnumbers=[]
            if (len(args)==1 or args[1]==''):#determine all available inputs
                for antnumberstr in telstate_antenna_mask:
                    antnumbers.append(int(antnumberstr[1:]))
            else:#use supplied inputs
                antnumbers=parse_antennarange(','.join(args[1:]))
            if (len(antnumbers)==0):
                send_websock_cmd('logconsole("No antenna inputs found or specified",true,true,true)',handlerkey)
            else:
                maxnant=16
                if (len(antnumbers)>maxnant):
                    send_websock_cmd('logconsole("Too many ('+str(len(antnumbers))+') antenna inputs specified. Specify antenna ranges explicitly. Warning, omitting: '+','.join(['m%03d'%antnum for antnum in antnumbers[maxnant:]])+'",true,true,true)',handlerkey)
                    antnumbers=antnumbers[:maxnant]
                send_websock_cmd('logconsole("Building waterfall matrix for: '+','.join(['m%03d'%antnum for antnum in antnumbers])+'",true,false,true)',handlerkey)
                html_customsignals[username]=[]
                html_collectionsignals[username]=[]
                html_viewsettings[username]=[]
                html_layoutsettings[username]={'ncols':len(antnumbers),'showonlineflags':'off','showflags':'on','outlierthreshold':100.0}
                for jj,jant in enumerate(antnumbers):
                    for ii,iant in enumerate(antnumbers):
                        ijstr=str(jant)+str(args[0][-2])+str(iant)+str(args[0][-1]) if (iant>=jant) else str(iant)+str(args[0][-2])+str(jant)+str(args[0][-1])
                        if (ii>=jj):
                            html_viewsettings[username].append({'figtype':'waterfall'+ijstr,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'in','processtime':0,'version':0})
                        else:
                            html_viewsettings[username].append({'figtype':'waterfall'+ijstr,'type':'phase','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'in','processtime':0,'version':0})
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==username):
                        send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('wtabhh') or args[0].startswith('wtabhv') or args[0].startswith('wtabvh') or args[0].startswith('wtabvv')):
            logger.info(repr(args))
            antnumbers=[int(antnumberstr[1:]) for antnumberstr in telstate_antenna_mask]#determine all available inputs
            if (len(antnumbers)==0):
                send_websock_cmd('logconsole("No antenna inputs found or specified",true,true,true)',handlerkey)
            else:
                if (len(args)==1 or args[1]==''):
                    refantnumber=antnumbers[0]
                else:#use supplied inputs
                    refantnumberlist=parse_antennarange(','.join(args[1:]))
                    if (len(refantnumberlist)==1):
                        refantnumber=refantnumberlist[0]
                    else:
                        send_websock_cmd('logconsole("Invalid reference antenna specified, using default instead",true,true,true)',handlerkey)
                        refantnumber=antnumbers[0]
                send_websock_cmd('logconsole("Building waterfall table for: '+','.join(['m%03d'%antnum for antnum in antnumbers])+'",true,false,true)',handlerkey)
                html_customsignals[username]=[]
                html_collectionsignals[username]=[]
                html_viewsettings[username]=[]
                html_layoutsettings[username]={'ncols':10,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0}
                for iant in range(64): # keep blank placeholder if antenna not present
                    if (iant<refantnumber):
                        ijstr=str(iant)+str(args[0][-1])+str(refantnumber)+str(args[0][-2])
                    else:
                        ijstr=str(refantnumber)+str(args[0][-2])+str(iant)+str(args[0][-1])
                    html_viewsettings[username].append({'figtype':'waterfall'+ijstr,'type':'phase','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'in','processtime':0,'version':0})
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==username):
                        send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('waterfall')):#creates new waterfall plot
            logger.info(repr(args))
            if (args[0].startswith('waterfallphase')):
                html_viewsettings[username].append({'figtype':'waterfall'+str(args[0][14:]),'type':'phase','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            else:
                html_viewsettings[username].append({'figtype':str(args[0]),'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('lag')):#creates new lag plot
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':str(args[0]),'type':'mag','xtype':'sample','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='timeseries'):#creates new timeseries plot
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'timeseries','type':'pow','xtype':'s','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='timeseriessnr'):#creates new timeseriessnr plot
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'timeseriessnr','type':'pow','xtype':'s','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('periodogram')):#creates new periodogram plot
            logger.info(repr(args))
            if (args[0][11:].replace(' ','').isdigit()):
                figtype='periodogram%d'%(int(args[0][11:].replace(' ','')))
            else:
                figtype='periodogram'
            html_viewsettings[username].append({'figtype':figtype,'type':'pow','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('bandpass')):#creates new bandpass plot
            logger.info(repr(args))
            if (args[0][8:].replace(' ','').isdigit()):
                figtype='bandpass%d'%(int(args[0][8:].replace(' ','')))
            else:
                figtype='bandpass'
            html_viewsettings[username].append({'figtype':figtype,'type':'pow','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('gain')):#creates new gain plot
            logger.info(repr(args))
            if (args[0][4:].replace(' ','').isdigit()):
                figtype='gain%d'%(int(args[0][4:].replace(' ','')))
            else:
                figtype='gain'
            html_viewsettings[username].append({'figtype':figtype,'type':'mag','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('delay')):#creates new delay plot
            logger.info(repr(args))
            if (args[0][5:].replace(' ','').isdigit()):
                figtype='delay%d'%(int(args[0][5:].replace(' ','')))
            else:
                figtype='delay'
            html_viewsettings[username].append({'figtype':figtype,'type':'mag','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0].startswith('spectrum')):#creates new spectrum plot
            logger.info(repr(args))
            if (args[0][8:].replace(' ','').isdigit()):
                figtype='spectrum%d'%(int(args[0][8:].replace(' ','')))
            else:
                figtype='spectrum'
            html_viewsettings[username].append({'figtype':figtype,'type':'pow','xtype':'ch','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='setsignals'):
            logger.info(repr(args))
            standardcollections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv','envelopeauto','envelopeautohh','envelopeautovv','envelopeautohv','envelopecross','envelopecrosshh','envelopecrossvv','envelopecrosshv']
            for theviewsettings in html_viewsettings[username]:
                theviewsettings['version']+=1
            for sig in args[1:]:
                sig=str(sig)
                if (re.match(r'^[^*]*[hv]\*[hv]$',sig)):#wildcard signal eg 32h*h, or h*h for auto products if (sig.count('*') == 1 and len(sig)>=3 and '*'==sig[-2] and (sig[-1]=='h' or sig[-1]=='v') and (sig[-3]=='h' or sig[-3]=='v') ):#wildcard signal eg 32h*h, or h*h for auto products
                    decodedsignal=decodecustomsignal(sig.replace('*','99999'))
                    if (len(decodedsignal) != 2):
                        send_websock_cmd('logconsole("Custom signal instruction not recognised",true,true,true)',handlerkey)
                    else:
                        with RingBufferLock:
                            ringbufferrequestqueue.put(['inputs',0,0,0,0,0])
                            fig=ringbufferresultqueue.get()
                        if (fig=={}):#an exception occurred
                            send_websock_cmd('logconsole("Server exception occurred evaluating inputs",true,true,true)',handlerkey)
                        elif ('logconsole' in fig):
                            inputs=fig['logconsole'].split(',')
                            antennas=np.unique([inputname[:-1] for inputname in inputs]).tolist()
                            send_websock_cmd('logconsole("%d antennas: '%(len(antennas))+','.join(antennas)+'",true,true,true)',handlerkey)
                            for ant in antennas:
                                if (len(sig)==3):
                                    ndecodedsignal=(ant+decodedsignal[0][-1],ant+decodedsignal[1][-1])
                                elif (ant<decodedsignal[0][:-1]):
                                    ndecodedsignal=(ant+decodedsignal[1][-1],decodedsignal[0])
                                elif (ant==decodedsignal[0][:-1]):#don't include auto corr using eg 32h*h command
                                    continue
                                else:
                                    ndecodedsignal=(decodedsignal[0],ant+decodedsignal[1][-1])
                                if (ndecodedsignal not in html_customsignals[username]):
                                    html_customsignals[username].append(ndecodedsignal)
                else:
                    decodedsignal=decodecustomsignal(sig)
                    logger.info('signal'+sig+' ==> decodedsignal '+repr(decodedsignal))
                    if (sig in standardcollections and sig not in html_collectionsignals[username]):
                        html_collectionsignals[username].append(sig)
                    elif (sig=='clear'):
                        html_customsignals[username]=[]
                        html_collectionsignals[username]=[]
                    elif (len(decodedsignal)):
                        if (decodedsignal not in html_customsignals[username]):
                            html_customsignals[username].append(decodedsignal)
        elif (args[0]=='saveflags'):
            logger.info(repr(args))
            if (len(args)==1):
                send_websock_cmd('logconsole("Please specify flagname",true,true,true)',handlerkey)
            else:
                with RingBufferLock:
                    ringbufferrequestqueue.put(['getflags',0,0,0,0,0])
                    fig=ringbufferresultqueue.get()
                if (fig=={}):#an exception occurred
                    send_websock_cmd('logconsole("Server exception occurred evaluating getflags",true,true,true)',handlerkey)
                elif ('logconsole' in fig):
                    theflagstr=fig['logconsole'][6:]
                    flagname=str(args[1])
                    try:
                        flagfile=open(SETTINGS_PATH+'/userflags.json','r+')
                        flagdictstr=flagfile.read()
                    except:
                        flagfile=open(SETTINGS_PATH+'/userflags.json','w+')
                        flagdictstr=''
                        pass
                    if (len(flagdictstr)>0):
                        flagdict=convertunicode(json.loads(flagdictstr))
                    else:
                        flagdict={}
                    flagdict[flagname]=theflagstr
                    flagdictstr=json.dumps(flagdict)
                    flagfile.seek(0)
                    flagfile.truncate(0)
                    flagfile.write(flagdictstr)
                    flagfile.close()
                try:
                    flagfile=open(SETTINGS_PATH+'/userflags.json','r')
                    flagdictstr=flagfile.read()
                    flagfile.close()
                except:
                    flagdictstr=''
                    pass
                if (len(flagdictstr)>0):
                    flagdict=convertunicode(json.loads(flagdictstr))
                    send_websock_cmd('logconsole("'+str(len(flagdict))+' flags saved: '+','.join(flagdict.keys())+'",true,true,true)',handlerkey)
                else:
                    send_websock_cmd('logconsole("0 flags saved",true,true,true)',handlerkey)
        elif (args[0]=='deleteflags'):
            logger.info(repr(args))
            if (len(args)==1):
                send_websock_cmd('logconsole("Please specify flagname",true,true,true)',handlerkey)
            else:
                flagname=str(args[1])
                try:
                    flagfile=open(SETTINGS_PATH+'/userflags.json','r+')
                    flagdictstr=flagfile.read()
                except:
                    flagfile=open(SETTINGS_PATH+'/userflags.json','w+')
                    flagdictstr=''
                    pass
                if (len(flagdictstr)>0):
                    flagdict=convertunicode(json.loads(flagdictstr))
                else:
                    flagdict={}
                if (flagname in flagdict):
                    flagdict.pop(flagname)
                flagdictstr=json.dumps(flagdict)
                flagfile.seek(0)
                flagfile.truncate(0)
                flagfile.write(flagdictstr)
                flagfile.close()
                try:
                    flagfile=open(SETTINGS_PATH+'/userflags.json','r')
                    flagdictstr=flagfile.read()
                    flagfile.close()
                except:
                    flagdictstr=''
                    pass
                if (len(flagdictstr)>0):
                    flagdict=convertunicode(json.loads(flagdictstr))
                    send_websock_cmd('logconsole("'+str(len(flagdict))+' flags saved: '+','.join(flagdict.keys())+'",true,true,true)',handlerkey)
                else:
                    send_websock_cmd('logconsole("0 flags saved",true,true,true)',handlerkey)
        elif (args[0]=='setflags'):
            logger.info(repr(args))
            try:
                flagfile=open(SETTINGS_PATH+'/userflags.json','r+')
                flagdictstr=flagfile.read()
            except:
                flagfile=open(SETTINGS_PATH+'/userflags.json','w+')
                flagdictstr=''
                pass
            if (len(flagdictstr)>0):
                flagdict=convertunicode(json.loads(flagdictstr))
            else:
                flagdict={}
            for theviewsettings in html_viewsettings[username]:
                if (theviewsettings['figtype'][:8]=='spectrum'):
                    theviewsettings['version']+=1
            weightedmask={}
            newflagstrlist=flagdict[args[1]].split(',') if (len(args)>1 and args[1] in flagdict) else args[1:]
            with RingBufferLock:
                ringbufferrequestqueue.put(['setflags',newflagstrlist,0,0,0,0])
                weightedmask=ringbufferresultqueue.get()
            if (isinstance(weightedmask,dict) and weightedmask == {}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating setflags'+','.join(newflagstrlist)+'",true,true,true)',handlerkey)
                if (len(flagdictstr)>0):
                    flagdict=convertunicode(json.loads(flagdictstr))
                    send_websock_cmd('logconsole("'+str(len(flagdict))+' flags saved: '+','.join(flagdict.keys())+'",true,true,true)',handlerkey)
                else:
                    send_websock_cmd('logconsole("0 flags saved",true,true,true)',handlerkey)
            elif (opts.datafilename is 'stream'):
                ####set timeseries mask on ingest
                try:
                    result=telstate_l0.add('sdisp_timeseries_mask',weightedmask)
                    logger.info('telstate setflags result: '+repr(result))
                    send_websock_cmd('logconsole("Set timeseries mask to '+','.join(newflagstrlist)+'",true,false,true)',handlerkey)
                except Exception, e:
                    logger.warning("Exception while telstate setflags: (" + str(e) + ")", exc_info=True)
                    send_websock_cmd('logconsole("Failed to set timeseries mask to '+','.join(newflagstrlist)+'",true,false,true)',handlerkey)
                    weightedmask={}
                    with RingBufferLock:
                        ringbufferrequestqueue.put(['setflags','',0,0,0,0])
                        weightedmask=ringbufferresultqueue.get()
                    if (isinstance(weightedmask,dict) and weightedmask == {}):#an exception occurred
                        send_websock_cmd('logconsole("Server exception occurred evaluating setflags while clearing flags",true,true,true)',handlerkey)
                    if (len(flagdictstr)>0):
                        flagdict=convertunicode(json.loads(flagdictstr))
                        send_websock_cmd('logconsole("'+str(len(flagdict))+' flags saved: '+','.join(flagdict.keys())+'",true,true,true)',handlerkey)
                    else:
                        send_websock_cmd('logconsole("0 flags saved",true,true,true)',handlerkey)
        elif (args[0]=='fileoffset'):
            logger.info(repr(args))
            if (opts.datafilename is 'stream'):
                send_websock_cmd('logconsole("Ignoring fileoffset command because data source is a stream and not a file",true,true,true)',handlerkey)
            else:
                with RingBufferLock:
                    ringbufferrequestqueue.put(['fileoffset',int(args[1]) if (args[1].isdigit()) else None,0,0,0,0])
                    fig=ringbufferresultqueue.get()
                    if (fig=={}):#an exception occurred
                        send_websock_cmd('logconsole("Server exception occurred evaluating fileoffset",true,true,true)',handlerkey)
                    elif ('logconsole' in fig):
                        send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)
        elif (args[0]=='showonlineflags' or args[0]=='showflags'):#onlineflags on, onlineflags off; flags on, flags off
            logger.info(repr(args))
            html_layoutsettings[username][args[0]]=args[1]
            for theviewsettings in html_viewsettings[username]:
                if (theviewsettings['figtype'][:8]=='spectrum' or theviewsettings['figtype'][:9]=='waterfall'):
                    theviewsettings['version']+=1
        elif (args[0]=='getusers'):
            logger.info(repr(args))
            logusers(handlerkey)
        elif (args[0]=='override'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['override',args[1],0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating override",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                overridestr=fig['logconsole']
                send_websock_cmd('logconsole("'+overridestr+'",true,true,true)',handlerkey)
        elif (args[0]=='inputs'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['inputs',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating inputs",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                inputsstr=fig['logconsole']
                inputs=inputsstr.split(',')
                send_websock_cmd('logconsole("%d inputs: '%(len(inputs))+inputsstr+'",true,true,true)',handlerkey)
        elif (args[0]=='antennas'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['inputs',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating inputs",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                inputs=fig['logconsole'].split(',')
                antennas=np.unique([inputname[:-1] for inputname in inputs]).tolist()
                send_websock_cmd('logconsole("%d antennas: '%(len(antennas))+','.join(antennas)+'",true,true,true)',handlerkey)
        elif (args[0]=='info'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['info',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating info",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                for printline in ((fig['logconsole']).split('\n')):
                    send_websock_cmd('logconsole("'+printline+'",true,true,true)',handlerkey)
        elif (args[0]=='kick'):
            logger.info(repr(args))
            if (len(args)==1):
                send_websock_cmd('logconsole("No username specified to kick",true,true,true)',handlerkey)
            elif (len(args)==2):
                splitarg=str(args[1]).split(' ')
                theusername=splitarg[0]
                message=' '.join(splitarg[1:])
                nusers=0
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==theusername):
                        nusers+=1
                        send_websock_cmd('document.write("You have been kicked off by '+username+' at '+time.strftime("%Y-%m-%d %H:%M")+'. Reload the page to re-connect. Message: '+message+'");',thishandler)
                send_websock_cmd('logconsole("Kicked off '+str(nusers)+' users with username '+theusername+'",true,true,true)',handlerkey)
        elif (args[0]=='telstate'):
            logger.info(repr(args))
            if (telstate is not None):
                if (len(args)>1):
                    thekey=str(args[1])
                    if (thekey=='obs_params'):
                        cbid=str(telstate['sdp_capture_block_id'])
                        obs_params_key=telstate.SEPARATOR.join((cbid, 'obs_params'))
                        obs_params=telstate.get(obs_params_key, {})
                        for obskey,obsvalue in obs_params.iteritems():
                            send_websock_cmd('logconsole("'+obskey+': '+repr(obsvalue)+'",true,true,true)',handlerkey)
                    elif (thekey in telstate):
                        if telstate.is_immutable(thekey):
                            send_websock_cmd('logconsole("'+thekey+': '+repr(telstate[thekey])+' (immutable, not plottable)",true,true,true)',handlerkey)
                        elif(not isinstance(telstate[thekey],numbers.Real)):
                            send_websock_cmd('logconsole("'+thekey+': '+repr(telstate[thekey])+' (not real valued, not plottable)",true,true,true)',handlerkey)
                        else:
                            html_viewsettings[username].append({'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0,'sensor':thekey})
                            for thishandler in websockrequest_username.keys():
                                if (websockrequest_username[thishandler]==username):
                                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
                            send_websock_cmd('logconsole("'+thekey+': '+repr(telstate[thekey])+'",true,true,true)',handlerkey)
                    else:
                        splitkeys=thekey.split(' ')
                        foundkeys=[]
                        for telkey in telstate.keys():
                            match=True
                            for splitkey in splitkeys:
                                if splitkey not in telkey:
                                    match=False
                                    break
                            if (match):
                                foundkeys.append(telkey)
                        if (len(foundkeys)==1):
                            send_websock_cmd('var txtinput=document.getElementById("signaltext");txtinput.value="telstate '+str(foundkeys[0])+'";txtinput.setSelectionRange(9,'+str(9+len(foundkeys[0]))+');txtinput.focus();',handlerkey)
                        else:
                            send_websock_cmd('logconsole("'+thekey+' not in telstate. Suggestions: '+repr(foundkeys)+'",true,true,true)',handlerkey)
                else:
                    immut=[]
                    unreal=[]
                    sens=[]
                    for thekey in telstate.keys():
                        if telstate.is_immutable(thekey):
                            immut.append(thekey)
                        elif(isinstance(telstate[thekey],numbers.Real)):
                            sens.append(thekey)
                        else:
                            unreal.append(thekey)
                    send_websock_cmd('logconsole("Immutable keys in telstate: '+repr(immut)+'",true,true,true)',handlerkey)
                    send_websock_cmd('logconsole("Non-real valued keys in telstate: '+repr(unreal)+'",true,true,true)',handlerkey)
                    send_websock_cmd('logconsole("Sensor keys in telstate: '+repr(sens)+'",true,true,true)',handlerkey)
            else:
                send_websock_cmd('logconsole("No telstate object",true,true,true)',handlerkey)
        elif (args[0]=='memoryleak'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['memoryleak',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating memoryleak",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                for printline in ((fig['logconsole']).split('\n')):
                    send_websock_cmd('logconsole("'+printline+'",true,true,true)',handlerkey)
                send_websock_cmd('logconsole("'+'nthreads:'+str(len(websockrequest_time))+'",true,true,true)',handlerkey)
                deregisterhandlers=[]
                for thishandler in websockrequest_username.keys():
                    timedelay=(time.time()-websockrequest_time[thishandler])
                    printline=websockrequest_username[thishandler]+': %.1fs'%(timedelay)
                    send_websock_cmd('logconsole("'+printline+'",true,true,true)',handlerkey)
                    if (timedelay>60):# connection been inactive for 1 minute
                        deregisterhandlers.append(thishandler)
                for thishandler in deregisterhandlers:
                    deregister_websockrequest_handler(thishandler)
                #extramsg='\n'.join([websockrequest_username[key]+': %.1fs'%(time.time()-websockrequest_time[key]) for key in websockrequest_username.keys()])
                #extramsg=str(repr(websockrequest_username))+str(repr(websockrequest_username.keys()))
        elif (args[0]=='RESTART'):
            logger.info(repr(args))
            with RingBufferLock:
                ringbufferrequestqueue.put(['RESTART',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating RESTART",true,true,true)',handlerkey)
            else:
                send_websock_cmd('logconsole("Exit ring buffer process",true,true,true)',handlerkey)
                time.sleep(2)
                Process(target=RingBufferProcess,args=(opts.spead, opts.spead_port, opts.spead_interface, opts.memusage, opts.max_custom_signals, opts.datafilename, opts.cbf_channels, ringbufferrequestqueue, ringbufferresultqueue)).start()
                logger.info('RESTART performed, using port=%d memusage=%f datafilename=%s'%(opts.spead_port,opts.memusage,opts.datafilename))
                send_websock_cmd('logconsole("RESTART performed.",true,true,true)',handlerkey)
        elif (args[0]=='server'):
            cmd=','.join(args[1:])
            logger.info(args[0]+':'+cmd)
            ret=commands.getoutput(cmd).split('\n')
            for thisret in ret:
                send_websock_cmd('logconsole("'+thisret+'",true,true,true)',handlerkey)
        elif (args[0]=='help'):
            logger.info(repr(args))
            if (len(args)!=1 or args[1] not in helpdict):
                for line in helpdict[args[1]]:
                    send_websock_cmd('logconsole("'+line+'",false,true,true)',handlerkey)
        elif (args[0]=='delete' and len(args)==2):#deletes specified user's settings from startup settings file as well as from server memory
            logger.info(repr(args))
            theusername=str(args[1])#load another user's settings
            try:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','r+')
                startupdictstr=startupfile.read()
            except:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','w+')
                startupdictstr=''
                pass
            if (len(startupdictstr)>0):
                startupdict=convertunicode(json.loads(startupdictstr))
            else:
                startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
            if (theusername in startupdict['html_viewsettings']):
                startupdict['html_viewsettings'].pop(theusername)
                startupdict['html_customsignals'].pop(theusername)
                startupdict['html_collectionsignals'].pop(theusername)
                startupdict['html_layoutsettings'].pop(theusername)
                startupdictstr=json.dumps(startupdict)
                startupfile.seek(0)
                startupfile.truncate(0)
                startupfile.write(startupdictstr)
                startupfile.close()
                send_websock_cmd('logconsole("Deleted '+theusername+' from '+SETTINGS_PATH+'/usersettings.json'+'",true,true,true)',handlerkey)
            else:
                startupfile.close()
                send_websock_cmd('logconsole("'+theusername+' not found in '+SETTINGS_PATH+'/usersettings.json'+'",true,true,true)',handlerkey)
            if (theusername in html_viewsettings):
                html_viewsettings.pop(theusername)
                html_customsignals.pop(theusername)
                html_collectionsignals.pop(theusername)
                html_layoutsettings.pop(theusername)
                send_websock_cmd('logconsole("Deleted '+theusername+' from active server memory",true,true,true)',handlerkey)
                logusers(handlerkey)
        elif (args[0]=='save'):#saves this user's settings in startup settings file
            logger.info(repr(args))
            if (len(args)==2):
                theusername=str(args[1])#load another user's settings
            else:
                theusername=username
            try:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','r+')
                startupdictstr=startupfile.read()
            except:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','w+')
                startupdictstr=''
                pass
            if (len(startupdictstr)>0):
                startupdict=convertunicode(json.loads(startupdictstr))
            else:
                startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
            startupdict['html_viewsettings'][theusername]=html_viewsettings[username]
            startupdict['html_customsignals'][theusername]=html_customsignals[username]
            startupdict['html_collectionsignals'][theusername]=html_collectionsignals[username]
            startupdict['html_layoutsettings'][theusername]=html_layoutsettings[username]
            startupdictstr=json.dumps(startupdict)
            startupfile.seek(0)
            startupfile.truncate(0)
            startupfile.write(startupdictstr)
            startupfile.close()
            try:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
                startupdictstr=startupfile.read()
                startupfile.close()
            except:
                startupdictstr=''
                pass
            if (len(startupdictstr)>0):
                startupdict=convertunicode(json.loads(startupdictstr))
                send_websock_cmd('logconsole("'+str(len(startupdict['html_viewsettings']))+' saved: '+','.join(startupdict['html_viewsettings'].keys())+'",true,false,true)',handlerkey)
            else:
                startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
                send_websock_cmd('logconsole("0 saved",true,false,true)',handlerkey)
        elif (args[0]=='load'):#loads this user's settings from startup settings file
            logger.info(repr(args))
            if (len(args)==2):
                theusername=str(args[1])#load another user's settings
            else:
                theusername=username
            try:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
                startupdictstr=startupfile.read()
                startupfile.close()
            except:
                startupdictstr=''
                pass
            if (len(startupdictstr)>0):
                startupdict=convertunicode(json.loads(startupdictstr))
            else:
                startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
            if (theusername in startupdict['html_viewsettings']):
                html_viewsettings[username]=copy.deepcopy(startupdict['html_viewsettings'][theusername])
                html_customsignals[username]=copy.deepcopy(startupdict['html_customsignals'][theusername])
                html_collectionsignals[username]=copy.deepcopy(startupdict['html_collectionsignals'][theusername])
                html_layoutsettings[username]=copy.deepcopy(startupdict['html_layoutsettings'][theusername])
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==username):
                        send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
            elif (theusername in html_viewsettings):
                html_viewsettings[username]=copy.deepcopy(html_viewsettings[theusername])
                html_customsignals[username]=copy.deepcopy(html_customsignals[theusername])
                html_collectionsignals[username]=copy.deepcopy(html_collectionsignals[theusername])
                html_layoutsettings[username]=copy.deepcopy(html_layoutsettings[theusername])
                send_websock_cmd('logconsole("'+theusername+' not found in startup settings file, but copied from active process instead",true,false,true)',handlerkey)
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==username):
                        send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
            else:
                send_websock_cmd('logconsole("'+theusername+' not found in '+SETTINGS_PATH+'/usersettings.json'+'",true,true,true)',handlerkey)
                logusers(handlerkey)
        if ((handlerkey in websockrequest_time) and (websockrequest_time[handlerkey]>poll_telstate_lasttime+1.0)):#don't check more than once a second
            poll_telstate_lasttime=websockrequest_time[handlerkey]
            try:
                if ('cbf_target' in telstate):
                    cbf_target=telstate.get_range('cbf_target',st=0 if (len(telstate_cbf_target)==0) else telstate_cbf_target[-1][1]+0.01)
                    for thiscbf_target in cbf_target:
                        telstate_cbf_target.append((thiscbf_target[0].split(',')[0].split(' |')[0].split('|')[0],thiscbf_target[1]))
                if (len(telstate_cal_antlist)==0 and 'cal_antlist' in telstate):
                    telstate_cal_antlist=telstate.get('cal_antlist')
                if ('cal_product_B' in telstate):
                    newproducts=telstate.get_range('cal_product_B',st=0 if (len(telstate_cal_product_B)==0) else telstate_cal_product_B[-1][1]+0.01)
                    if (len(newproducts)):
                        telstate_cal_product_B=[newproducts[-1]]#overwrite with latest values, do not make history available
                if ('cal_product_G' in telstate):
                    newproducts=telstate.get_range('cal_product_G',st=0 if (len(telstate_cal_product_G)==0) else telstate_cal_product_G[-1][1]+0.01)
                    telstate_cal_product_G.extend(newproducts)
                if ('cal_product_K' in telstate):
                    newproducts=telstate.get_range('cal_product_K',st=0 if (len(telstate_cal_product_K)==0) else telstate_cal_product_K[-1][1]+0.01)
                    telstate_cal_product_K.extend(newproducts)
                if (len(telstate_antenna_mask)>0 and telstate_antenna_mask[0]+'_activity' in telstate):
                    data_activity=telstate.get_range(telstate_antenna_mask[0]+'_activity',st=0 if (len(telstate_activity)==0) else telstate_activity[-1][1]+0.01)
                    for thisdata_activity in data_activity:
                        telstate_activity.append((thisdata_activity[0],thisdata_activity[1]))
                notification=ringbuffernotifyqueue.get(False)
                if (notification=='end of stream'):
                    scriptnametext='completed '+telstate_script_name
                    for thishandler in websockrequest_username.keys():
                        send_websock_cmd('document.getElementById("scriptnametext").innerHTML="'+scriptnametext+'";',thishandler)
                elif (notification=='start of stream'):
                    try:
                        cbid=str(telstate['sdp_capture_block_id'])
                        obs_params_key=telstate.SEPARATOR.join((cbid, 'obs_params'))
                        obs_params=telstate.get(obs_params_key, {})
                        telstate_script_name=os.path.basename(obs_params['script_name'])
                    except Exception, e:
                        logger.warning("User event exception when determining script name %s" % str(e), exc_info=True)
                        telstate_script_name='undisclosed script'
                    scriptnametext=telstate_script_name
                    for thishandler in websockrequest_username.keys():
                        send_websock_cmd('document.getElementById("scriptnametext").innerHTML="'+scriptnametext+'";',thishandler)
                else:
                    logger.warning("Unexpected notification received from ringbufferprocess: %s" % str(notification))
            except: #ringbuffernotifyqueue.get(False) raise Empty if queue is empty
                pass

    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)

def convertunicode(input):
    if isinstance(input, dict):
        return dict((convertunicode(key), convertunicode(value)) for key, value in input.iteritems())
    # elif isinstance(input,tuple):#JSON HAS NO TUPLES!!!
    #     return tuple(convertunicode(element) for element in input)
    elif isinstance(input, list):
        return list(convertunicode(element) for element in input)
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input

#decodes abreviated signals of form 1h3h to ('ant1h','ant3h')
#else decodes, eg d0001hd0003v into ('d0001h','d0003v')
#returns () if otherwise invalid
#note this is not foolproof
def decodecustomsignal(signalstr):
    sreg=re.compile('[h|v|H|V|x|y]').split(signalstr)
    if (len(sreg)!=3 or len(sreg[2])!=0):
        return ();
    if ((not sreg[0].isdigit()) or (not sreg[1].isdigit())):
        return (sreg[0]+signalstr[len(sreg[0])],sreg[1]+signalstr[len(sreg[0])+1+len(sreg[1])])
    return (ANTNAMEPREFIX%(int(sreg[0]))+signalstr[len(sreg[0])].lower(),ANTNAMEPREFIX%(int(sreg[1]))+signalstr[len(sreg[0])+1+len(sreg[1])].lower())

#converts eg ('ant1h','ant2h') into '1h2h'
#            ('m000h','m001h') into '0h1h'
def printablesignal(product):
    return str(int(''.join(re.findall('[0-9]',product[0]))))+product[0][-1]+str(int(''.join(re.findall('[0-9]',product[1]))))+product[1][-1]

def getsensordata(sensorname, start_time=0, end_time=-120):
    if telstate is None or sensorname not in telstate:
        return [np.array([]),np.array([])]
    if (end_time>=0):
        values=telstate.get_range(sensorname,st=start_time,et=end_time,include_previous=True)
    else:
        values=telstate.get_range(sensorname,st=end_time,include_previous=True)# typical values=[(25.0, 1458820419.843372)]
    if (not isinstance(values,list) or len(values)<1 or not isinstance(values[0][0], (numbers.Real, str))):
        return [np.array([]),np.array([])]
    if (len(values)==1):
        sensorvalues=np.array([values[0][0],values[0][0]])
        timestamps=np.array([start_time,end_time])
    else:
        sensorvalues=np.array([val[0] for val in values])
        timestamps=np.array([val[1] for val in values])
    return [timestamps,sensorvalues]

def send_timeseries(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            timeseries_fig=ringbufferresultqueue.get()

        count=0
        processtime=0
        if (timeseries_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],processtime
        elif ('logconsole' in timeseries_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+timeseries_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],processtime
        elif ('logignore' in timeseries_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],processtime
        if ('processtime' in timeseries_fig):
            processtime=timeseries_fig['processtime']

        sensorsignal=[]
        sensorts=[]
        sensorname=''
        textsensor=[]
        textsensorts=[]
        if ('sensor' in theviewsettings):
            try:
                sensorts,sensorsignal = getsensordata(sensorname=theviewsettings['sensor'], start_time=timeseries_fig['xdata'][0], end_time=timeseries_fig['xdata'][-1])
                sensorname=' '#currently requires length>0
                timeseries_fig['title']=theviewsettings['sensor'].replace('_',' ')
            except Exception, e:
                sensorsignal=[]
                sensorts=[]
                sensorname=''
                #logger.warning("Exception evaluating sensor %s: %s" % (theviewsettings['sensor'],str(e)), exc_info=True)

        textsensor=[]
        textsensorts=[]
        if (len(telstate_activity)>0):
            span=[[]]
            spancolor=[[192,192,192,64]]
            startslew=None
            currenttargetname=''
            itarget=0
            mergedtextsensor=[]
            mergedtextsensorts=[]
            tstart,tstop=getstartstoptime(timeseries_fig['xdata'],theviewsettings['xmin'],theviewsettings['xmax'])
            is_small_view=(tstop-tstart<=200)
            for idata in range(len(telstate_activity)):
                newtarget=False
                if (telstate_activity[idata][0]=='slew'):
                    startslew=telstate_activity[idata][1]
                else:
                    if (startslew is not None):
                        if ((timeseries_fig['xdata'][0]<=startslew and startslew<=timeseries_fig['xdata'][-1]) or (timeseries_fig['xdata'][0]<=telstate_activity[idata][1] and telstate_activity[idata][1]<=timeseries_fig['xdata'][-1])):
                            span[0].append([startslew,telstate_activity[idata][1]])
                        while (itarget<len(telstate_cbf_target)):
                            if (telstate_cbf_target[itarget][1]<telstate_activity[idata][1]):
                                currenttargetname=telstate_cbf_target[itarget][0]
                                itarget+=1
                            else:
                                break
                        newtarget=(len(mergedtextsensor)==0 or mergedtextsensor[-1]!=currenttargetname)
                    startslew=None
                if (newtarget):
                    if (is_small_view):
                        mergedtextsensor.append(currenttargetname+' '+telstate_activity[idata][0])
                    else:
                        mergedtextsensor.append(currenttargetname)
                    mergedtextsensorts.append(telstate_activity[idata][1])
                elif (is_small_view):
                    mergedtextsensor.append(telstate_activity[idata][0])
                    mergedtextsensorts.append(telstate_activity[idata][1])
            if (startslew is not None and telstate_activity[idata][0]=='slew' and startslew<timeseries_fig['xdata'][-1]):
                span[0].append([startslew,timeseries_fig['xdata'][-1]])
            if (len(mergedtextsensor)>0):#only include text that is in view
                for idata in range(len(mergedtextsensor))[::-1]:#skip ahead
                    if (timeseries_fig['xdata'][-1]>=mergedtextsensorts[idata]):
                        break
                for idata in range((idata+1 if (len(mergedtextsensor)>idata) else idata))[::-1]:#includes preceding target too
                    textsensor.insert(0,mergedtextsensor[idata])
                    textsensorts.insert(0,mergedtextsensorts[idata])
                    if (timeseries_fig['xdata'][0]>mergedtextsensorts[idata]):
                        break
            if (len(span[0])>0):
                timeseries_fig['span']=span
                timeseries_fig['spancolor']=np.array(spancolor)
        if (lastrecalc<timeseries_fig['version'] or outlierhash!=timeseries_fig['outlierhash']):
            local_yseries=(timeseries_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),timeseries_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),timeseries_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),timeseries_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),timeseries_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),timeseries_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),timeseries_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),timeseries_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),timeseries_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),timeseries_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),timeseries_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),timeseries_fig['xdata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),timeseries_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].sensorname'%(ifigure),sensorname,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xsensor'%(ifigure),sensorts,'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ysensor'%(ifigure),sensorsignal,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].textsensor'%(ifigure),textsensor,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtextsensor'%(ifigure),textsensorts,'I'),handlerkey);count+=1;
            for ispan in range(len(timeseries_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(timeseries_fig['span'][ispan]),'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),timeseries_fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            where=np.where(timeseries_fig['xdata']>lastts+0.01)[0]#next time stamp index
            if (len(where)>0):
                its=np.min(where)
                local_yseries=np.array(timeseries_fig['ydata'])[:,:,its:]
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),timeseries_fig['lastts'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),timeseries_fig['lastdt'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),timeseries_fig['title'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),timeseries_fig['xlabel'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),timeseries_fig['xdata'],'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].sensorname'%(ifigure),sensorname,'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xsensor'%(ifigure),sensorts,'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ysensor'%(ifigure),sensorsignal,'H'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].textsensor'%(ifigure),textsensor,'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xtextsensor'%(ifigure),textsensorts,'I'),handlerkey);count+=1;
                for ispan in range(len(timeseries_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                    send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(timeseries_fig['span'][ispan]),'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),timeseries_fig['spancolor'],'b'),handlerkey);count+=1;
                for itwin,twinplotyseries in enumerate(local_yseries):
                    for iline,linedata in enumerate(twinplotyseries):
                        send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentydata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return timeseries_fig['customproducts'],timeseries_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime


def send_periodogram(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            periodogram_fig=ringbufferresultqueue.get()
        count=0
        processtime=0
        if (periodogram_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in periodogram_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+periodogram_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in periodogram_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in periodogram_fig):
            processtime=periodogram_fig['processtime']
        if (lastrecalc<periodogram_fig['version'] or periodogram_fig['lastts']>lastts+0.01):
            local_yseries=(periodogram_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),periodogram_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),periodogram_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),periodogram_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),periodogram_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),periodogram_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),periodogram_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),periodogram_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),periodogram_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),periodogram_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),periodogram_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),periodogram_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),periodogram_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(periodogram_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(periodogram_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),periodogram_fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return periodogram_fig['customproducts'],periodogram_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime

def send_bandpass(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    startproctime=time.time()
    fig={}
    try:
        if (telstate is not None):
            if (len(telstate_cal_product_B)):
                [(cal_B,cal_B_timestamp)]=telstate_cal_product_B
                ydata=[]
                color=[]
                legend=[]
                cfreq=telstate_l0.get('center_freq')*1e-6
                bwidth=telstate_l0.get('bandwidth')*1e-6
                nchan=telstate_l0.get('n_chans')
                ch=cfreq - bwidth/2.0 + np.arange(nchan) * (bwidth/nchan)
                start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                thech_=np.arange(start_chan,stop_chan,chanincr)
                typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
                thetype=typelookup[theviewsettings['type']]
                for ipol in range(cal_B.shape[1]):
                    for iant in range(cal_B.shape[2]):
                        signal=cal_B[start_chan:stop_chan:chanincr,ipol,iant].reshape(-1)
                        ydata.append(signal)
                        legend.append(telstate_cal_antlist[iant]+['h','v'][ipol])
                        color.append(np.r_[registeredcolourant(legend[-1]),0])
                if (len(ydata)==0):
                    ydata=[np.nan*thech]
                    color=[np.array([255,255,255,0])]
                if (theviewsettings['type']=='pow'):
                    ydata=20.0*np.log10(np.abs(ydata))#ydata is voltage quantity in this case
                    fig['ylabel']=['Power']
                    fig['yunit']=['dB']
                elif (thetype=='mag'):
                    ydata=np.abs(ydata)
                    fig['ylabel']=['Amplitude']
                    fig['yunit']=['counts']
                else:
                    ydata=np.angle(ydata)
                    fig['ylabel']=['Phase']
                    fig['yunit']=['rad']
                fig['ydata']=[ydata]
                fig['color']=np.array(color)
                fig['legend']=legend
                fig['outlierhash']=0
                fig['title']='Bandpass at '+time.asctime(time.localtime(cal_B_timestamp))
                fig['lastts']=cal_B_timestamp
                fig['lastdt']=0
                fig['version']=theviewsettings['version']
                if (theviewsettings['xtype']=='mhz'):
                    fig['xdata']=thech
                    fig['xlabel']='Frequency'
                    fig['xunit']='MHz'
                elif (theviewsettings['xtype']=='ghz'):
                    fig['xdata']=np.array(thech)/1e3
                    fig['xlabel']='Frequency'
                    fig['xunit']='GHz'
                else:
                    fig['xdata']=thech_
                    fig['xlabel']='Channel number'
                    fig['xunit']=''
                fig['spancolor']=np.array([])
                fig['span']=[]
                fig['outlierproducts']=[]
                fig['customproducts']=[]
        bandpass_fig=fig
        count=0
        if (bandpass_fig!={} and (lastrecalc<bandpass_fig['version'] or bandpass_fig['lastts']>lastts+0.01)):
            local_yseries=(bandpass_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),bandpass_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),bandpass_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),bandpass_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),bandpass_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),bandpass_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),bandpass_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),bandpass_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),bandpass_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),bandpass_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),bandpass_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),bandpass_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),bandpass_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(bandpass_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(bandpass_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),bandpass_fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],time.time()-startproctime#customproducts,outlierproducts,processtime

def send_gain(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure,dodelay=False):
    startproctime=time.time()
    fig={}
    sensorsignal=[]
    sensorts=[]
    sensorname=''
    textsensor=[]
    textsensorts=[]
    try:
        if (telstate is not None):
            gainlist=telstate_cal_product_K if dodelay else telstate_cal_product_G
            if (len(gainlist)):
                ts=[]
                ydata=[]
                color=[]
                legend=[]
                outlierproducts=[]
                customproducts=[]
                typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
                thetype=typelookup[theviewsettings['type']]
                ts=[v[1] for v in gainlist]
                if (len(gainlist)>0):
                    for ipol in range(gainlist[0][0].shape[0]):
                        for iant in range(gainlist[0][0].shape[1]):
                            signal=np.array([v[0][ipol,iant] for v in gainlist]).reshape(-1)
                            ydata.append(signal)
                            legend.append(telstate_cal_antlist[iant]+['h','v'][ipol])
                            color.append(np.r_[registeredcolourant(legend[-1]),0])
                outlierhash=0
                if (len(ydata)==0):
                    ydata=[]
                    color=[np.array([255,255,255,0])]
                if (theviewsettings['type']=='pow'):
                    ydata=20.0*np.log10(np.abs(ydata))#ydata is voltage quantity in this case
                    fig['ylabel']=['Power']
                    fig['yunit']= ['dB'] if (not dodelay) else ['dBs']
                elif (thetype=='mag'):
                    if (dodelay):
                        ydata=np.real(ydata)
                        fig['ylabel']=['Delay']
                    else:
                        ydata=np.abs(ydata)
                        fig['ylabel']=['Amplitude']
                    fig['yunit']=[' '] if (not dodelay) else ['s']
                else:
                    ydata=np.angle(ydata)
                    fig['ylabel']=['Phase']
                    fig['yunit']=['rad']
                fig['xunit']='s'
                fig['xdata']=ts
                fig['ydata']=[ydata]
                fig['color']=np.array(color)
                fig['legend']=legend
                fig['outlierhash']=outlierhash
                fig['title']='Gain' if (not dodelay) else 'Delay'
                fig['lastts']=ts[-1]
                fig['lastdt']=0
                fig['version']=theviewsettings['version']
                fig['xlabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                fig['span']=[]
                fig['spancolor']=[]
                fig['outlierproducts']=[]
                fig['customproducts']=[]
        count=0
        if (fig!={} and (lastrecalc<fig['version'] or outlierhash!=fig['outlierhash'])):
            local_yseries=(fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),fig['xdata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].sensorname'%(ifigure),sensorname,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xsensor'%(ifigure),sensorts,'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ysensor'%(ifigure),sensorsignal,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].textsensor'%(ifigure),textsensor,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtextsensor'%(ifigure),textsensorts,'I'),handlerkey);count+=1;
            for ispan in range(len(fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(fig['span'][ispan]),'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            if fig=={}:
                where=[]
            else:
                where=np.where(fig['xdata']>lastts+0.01)[0]#next time stamp index
            if (len(where)>0):
                its=np.min(where)
                local_yseries=np.array(fig['ydata'])[:,:,its:]
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),fig['lastts'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),fig['lastdt'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),fig['title'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),fig['xlabel'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),fig['xdata'],'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].sensorname'%(ifigure),sensorname,'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xsensor'%(ifigure),sensorts,'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ysensor'%(ifigure),sensorsignal,'H'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].textsensor'%(ifigure),textsensor,'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xtextsensor'%(ifigure),textsensorts,'I'),handlerkey);count+=1;
                for ispan in range(len(fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                    send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(fig['span'][ispan]),'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),fig['spancolor'],'b'),handlerkey);count+=1;
                for itwin,twinplotyseries in enumerate(local_yseries):
                    for iline,linedata in enumerate(twinplotyseries):
                        send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentydata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],time.time()-startproctime#customproducts,outlierproducts,processtime


def send_gainwaterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure,dodelay=False):
    startproctime=time.time()
    fig={}
    try:
        if (telstate is not None):
            gainlist=telstate_cal_product_K if dodelay else telstate_cal_product_G
            if (len(gainlist)):
                ts=[]
                cdata=[]
                legend=[]
                outlierproducts=[]
                customproducts=[]
                typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
                thetype=typelookup[theviewsettings['type']]
                ts=[v[1] for v in gainlist]
                if (len(gainlist)>0):
                    for iant in range(gainlist[0][0].shape[1]):
                        for ipol in range(gainlist[0][0].shape[0]):
                            signal=np.array([v[0][ipol,iant] for v in gainlist]).reshape(-1)
                            cdata.append(signal)
                            legend.append(telstate_cal_antlist[iant]+['h','v'][ipol])
                outlierhash=0
                cdata=np.array(cdata).transpose()
                if (theviewsettings['type']=='pow'):
                    cdata=20.0*np.log10(np.abs(cdata))
                    fig['clabel']='Power'
                    fig['cunit']='dB' if (not dodelay) else 'dBs'
                elif (thetype=='mag'):
                    if (dodelay):
                        cdata=np.real(cdata)
                        fig['clabel']='Delay'
                    else:
                        cdata=np.abs(cdata)
                        fig['clabel']='Amplitude'
                    fig['cunit']=[' '] if (not dodelay) else ['s']
                else:
                    fig['clabel']='Phase'
                    fig['cunit']='rad'
                    cdata=np.angle(cdata)
                fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                fig['yunit']='s'
                fig['cdata']=cdata
                fig['ydata']=np.array(ts)
                fig['legend']=legend
                fig['outlierhash']=0
                fig['color']=[]
                fig['span']=[]
                fig['spancolor']=[]
                fig['title']='Gain waterfall' if (not dodelay) else 'Delay waterfall'
                fig['lastts']=ts[-1]
                fig['lastdt']=0
                fig['version']=theviewsettings['version']
                fig['xdata']=range(gainlist[0][0].shape[1]*2+1)
                fig['xlabel']='Input'
                fig['xunit']=' '
                fig['outlierproducts']=[]
                fig['customproducts']=[]
        waterfall_fig=fig
        count=0
        if (waterfall_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+waterfall_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in waterfall_fig):
            processtime=waterfall_fig['processtime']
        if (lastrecalc<waterfall_fig['version']):
            local_cseries=(waterfall_fig['cdata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),waterfall_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),waterfall_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),waterfall_fig['clabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),waterfall_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),waterfall_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),waterfall_fig['cunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),waterfall_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),waterfall_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),waterfall_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),waterfall_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(waterfall_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(waterfall_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),waterfall_fig['spancolor'],'b'),handlerkey);count+=1;
            for iline,linedata in enumerate(local_cseries):
                send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            if (waterfall_fig['cdata'].shape[0]>0):
                local_cseries=waterfall_fig['cdata'][:]
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),waterfall_fig['xdata'],'m'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
                for iline,linedata in enumerate(local_cseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentcdata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],time.time()-startproctime#customproducts,outlierproducts,processtime

def send_spectrum(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            spectrum_fig=ringbufferresultqueue.get()
        count=0
        processtime=0
        if (spectrum_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in spectrum_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+spectrum_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in spectrum_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in spectrum_fig):
            processtime=spectrum_fig['processtime']
        if (lastrecalc<spectrum_fig['version'] or spectrum_fig['lastts']>lastts+0.01):
            local_yseries=(spectrum_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),spectrum_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),spectrum_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),spectrum_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),spectrum_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),spectrum_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),spectrum_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),spectrum_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),spectrum_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),spectrum_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),spectrum_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),spectrum_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),spectrum_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(spectrum_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(spectrum_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),spectrum_fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return spectrum_fig['customproducts'],spectrum_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime


def send_waterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            waterfall_fig=ringbufferresultqueue.get()

        count=0
        processtime=0
        if (waterfall_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+waterfall_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in waterfall_fig):
            processtime=waterfall_fig['processtime']
        if (lastrecalc<waterfall_fig['version']):
            local_cseries=(waterfall_fig['cdata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),waterfall_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),waterfall_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),waterfall_fig['clabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),waterfall_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),waterfall_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),waterfall_fig['cunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),waterfall_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),waterfall_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),waterfall_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),waterfall_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(waterfall_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(waterfall_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),waterfall_fig['spancolor'],'b'),handlerkey);count+=1;
            for iline,linedata in enumerate(local_cseries):
                send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            if (waterfall_fig['cdata'].shape[0]>0):
                local_cseries=waterfall_fig['cdata'][:]
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),waterfall_fig['xdata'],'m'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
                for iline,linedata in enumerate(local_cseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentcdata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return waterfall_fig['customproducts'],waterfall_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime

def send_lag(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            lag_fig=ringbufferresultqueue.get()

        count=0
        processtime=0
        if (lag_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in lag_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+lag_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in lag_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in lag_fig):
            processtime=lag_fig['processtime']
        if (lastrecalc<lag_fig['version']):
            local_cseries=(lag_fig['cdata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),lag_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),lag_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),lag_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),lag_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),lag_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),lag_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),lag_fig['clabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),lag_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),lag_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),lag_fig['cunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),lag_fig['legend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),lag_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),lag_fig['xdata'],'m'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),lag_fig['ydata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),lag_fig['color'],'b'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            for ispan in range(len(lag_fig['span'])):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(lag_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),lag_fig['spancolor'],'b'),handlerkey);count+=1;
            for iline,linedata in enumerate(local_cseries):
                send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            if (lag_fig['cdata'].shape[0]>0):
                local_cseries=lag_fig['cdata'][:]
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),lag_fig['lastts'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),lag_fig['lastdt'],'d'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),lag_fig['title'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),lag_fig['ylabel'],'s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),lag_fig['ydata'],'I'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),lag_fig['xdata'],'m'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey);count+=1;
                for iline,linedata in enumerate(local_cseries):
                    send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentcdata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return lag_fig['customproducts'],lag_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime

def send_flagcount(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            flagcount_fig=ringbufferresultqueue.get()
        count=0
        processtime=0
        if (flagcount_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in flagcount_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+flagcount_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in flagcount_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in flagcount_fig):
            processtime=flagcount_fig['processtime']
        if (lastrecalc<flagcount_fig['version'] or flagcount_fig['lastts']>lastts+0.01):
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),flagcount_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),flagcount_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),flagcount_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),flagcount_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),flagcount_fig['clabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),flagcount_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),flagcount_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),flagcount_fig['cunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),flagcount_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),flagcount_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legendx'%(ifigure),flagcount_fig['legendx'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legendy'%(ifigure),flagcount_fig['legendy'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),flagcount_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),flagcount_fig['xdata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].flagdata'%(ifigure),(flagcount_fig['flagdata'])[:],'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return flagcount_fig['customproducts'],flagcount_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime

def send_blmx(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        with RingBufferLock:
            ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
            blmx_fig=ringbufferresultqueue.get()
        count=0
        processtime=0
        if (blmx_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logconsole' in blmx_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+blmx_fig['logconsole']+'",true,false,true)',handlerkey)
            return [],[],0
        elif ('logignore' in blmx_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return [],[],0
        if ('processtime' in blmx_fig):
            processtime=blmx_fig['processtime']
        if (lastrecalc<blmx_fig['version'] or blmx_fig['lastts']>lastts+0.01):
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),blmx_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),blmx_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),blmx_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),blmx_fig['title'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),blmx_fig['clabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),blmx_fig['xlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),blmx_fig['ylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),blmx_fig['cunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),blmx_fig['xunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),blmx_fig['yunit'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legendx'%(ifigure),blmx_fig['legendx'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].legendy'%(ifigure),blmx_fig['legendy'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].outlierhash'%(ifigure),blmx_fig['outlierhash'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),blmx_fig['xdata'],'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),theviewsettings['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),theviewsettings['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),theviewsettings['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),theviewsettings['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),theviewsettings['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),theviewsettings['showyticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].mxdatahh'%(ifigure),(blmx_fig['mxdatahh'])[:],'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].mxdatavv'%(ifigure),(blmx_fig['mxdatavv'])[:],'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return blmx_fig['customproducts'],blmx_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime#customproducts,outlierproducts,processtime

#client sends request to server; server may respond with numerous assignments of data into a datastructure on client side to address request
#datastructure transmitted in binary to client
#keep an indexible list of elements rather than individual arrays
#var data=new Object()
#data["key"]="value"
#transmission is performed per variable
#data could be list of strings
#idea is to send several short messages rather than one long message with many variables
#variablename [null terminated]: eg could be x or x[10] or x[10][10]
#type[8bits]: s:string; f:float32; d:float64; b:byte; h:int16; i:int32; B:tobyte; H:toint16
#number of dimensions [8bits]
#dim0: [32 bits]
#dim1: [32 bits]
#dim2: [32 bits]
#...
#data follows []...
#and at end if appropriate
#convertminval [float32] if (doconvert) outdata=convertminval+(data)*(convertmaxval-convertminval)
#convertmaxval [float32] if (doconvert) outdata=convertminval+(data)*(convertmaxval-convertminval)

#if val is a list in cannot contain sublists - must be only one dimensional
#val can be multidimensional if it is a np.dnarray
#dtype:
# B: original array is double precision, but min, max determined and array it is transmitted as bytes, and rescaled on other side.
# m: only first, last and count is sent over, it is assumed to be monotonic, and array is rebuilt on other side
def pack_binarydata_msg(varname,val,dtype):
    bytesize  ={'s':1, 'f':4,   'd':8,   'b':1,   'h':2,   'i':4,   'B':1,   'H':2,   'I':4, 'm':4, 'M':8}
    structconv={'s':1, 'f':'f', 'd':'d', 'b':'B', 'h':'H', 'i':'I', 'B':'B', 'H':'H', 'I':'I', 'm':'f', 'M':'d'}
    npconv={'s':1, 'f':'float32', 'd':'float64', 'b':'uint8', 'h':'uint16', 'i':'uint32', 'B':'uint8', 'H':'uint16', 'I':'uint32', 'm':'float32', 'M':'float64'}
    lenvarname=len(varname)
    if (type(val)==np.ndarray):
        shp=val.shape
        ndim=len(shp)
        val=val.reshape(-1)
    elif(type(val)==list):
        shp=[len(val)]
        ndim=1
    else:
        val=[val]
        shp=[]
        ndim=0
    buff=varname+'\x00'+dtype+struct.pack('<B',ndim)
    for idim in shp:
        buff+=struct.pack('<H',idim)
    if (dtype=='s'):#encodes a list of strings
        for sval in val:
            buff+=sval+'\x00';
    elif (dtype=='B' or dtype=='H' or dtype=='I'):
        origval=val;
        val=np.array(val,dtype='float')
        wval=np.zeros(np.shape(val),dtype=npconv[dtype])
        finiteind=np.nonzero(np.isfinite(val)==True)[0]
        minval=np.nan
        maxval=np.nan
        if (len(finiteind)):
            finitevals=val[finiteind]
            minval=np.min(finitevals)
            maxval=np.max(finitevals)
            if (maxval==minval):
                maxval=minval+1

            maxrange=2**(8*bytesize[dtype])-4;#also reserve -inf,inf,nan
            wval[finiteind]=np.array(((val[finiteind]-minval)/(maxval-minval)*(maxrange)),dtype=npconv[dtype])+3

        #note- improvement could be done. It seems lines are sent as channels individually spanning time, should possibly rather send a spectrum for waterfall plot updates
        # if (dtype=='B' and ((not np.isfinite(minval)) or np.isnan(minval)) ):
        #     print 'WARNING: sent nan scale, len(finiteind)',len(finiteind),'len(val)',len(val),'varname',varname

        if (len(finiteind) != len(wval)):
            wval[np.nonzero(val==-np.inf)[0]]=0
            wval[np.nonzero(val==np.inf)[0]]=1
            wval[np.nonzero(np.isnan(val)==True)[0]]=2

        buff+=struct.pack('<%d'%(len(val))+structconv[dtype],*wval.tolist())
        if (dtype=='I'):
            buff+=struct.pack('<d',minval)#use double precision limits here
            buff+=struct.pack('<d',maxval)
        else:
            buff+=struct.pack('<f',minval)
            buff+=struct.pack('<f',maxval)
    elif (dtype=='f' or dtype=='d' or dtype =='b' or dtype =='h' or dtype =='i'):#encodes list or ndarray of floats
        wval=np.array(val,dtype=npconv[dtype])
        buff+=struct.pack('<%d'%(len(wval))+structconv[dtype],*wval.tolist())
    elif (dtype=='m' or dtype=='M'):
        wval=np.array([val[0],val[-1]],dtype=npconv[dtype])
        buff+=struct.pack('<%d'%(len(wval))+structconv[dtype],*wval.tolist())

    return buff

#Caught exception (local variable 'action' referenced before assignment). Removing registered handler
def parse_websock_cmd(s, request):
    try:
        args = s.split(",")
        if (request not in websockrequest_username):
            if (args[0]=='setusername'):
                websockrequest_username[request]='no-name'
            else:
                raise ValueError('Closing data connection. Unregistered request handler not allowed: '+str(request))
        websockrequest_time[request]=time.time()
        handle_websock_event(request,*args)

    except AttributeError:
        logger.warning("Cannot find request method %s", s)

def send_websock_data(binarydata, handlerkey):
    try:
        handlerkey.write_message(binarydata,binary=True)
    except WebSocketClosedError: # connection has gone
        logger.warning("Connection to %s@%s has gone. Closing..." % websockrequest_username[handlerkey], handlerkey.request.remote_ip)
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)", str(e), exc_info=True)
        logger.warning("Connection to %s@%s has gone. Closing..." % websockrequest_username[handlerkey], handlerkey.request.remote_ip)
        deregister_websockrequest_handler(handlerkey)

def send_websock_cmd(cmd, handlerkey):
    try:
        frame=u"/*exec_user_cmd*/ function callme(){%s; return;};callme();" % cmd;#ensures that vectors of data is not sent back to server!
        handlerkey.write_message(frame)
    except WebSocketClosedError: # connection has gone
        logger.warning("Connection to %s@%s has gone. Closing...", websockrequest_username[handlerkey], handlerkey.request.remote_ip)
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)", str(e), exc_info=True)
        logger.warning("Connection to %s@%s has gone. Closing...", websockrequest_username[handlerkey], handlerkey.request.remote_ip)
        deregister_websockrequest_handler(handlerkey)

def deregister_websockrequest_handler(request):
    if (request in websockrequest_time):
        del websockrequest_time[request]
    if (request in websockrequest_username):
        del websockrequest_username[request]

class MainHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def get(self):
        self.render(SERVE_PATH+"/index.html",scriptname_text=scriptnametext,arrayname_text=telstate_array_id)

    def options(self):
        self.set_status(204)
        self.finish()

class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        logger.info("Connection opened...")

    def on_message(self, message):
        parse_websock_cmd(message,self)

    def on_close(self):
        logger.info("Connection to %s@%s is closed...", websockrequest_username[self] if (self in websockrequest_username) else '(unknown)', self.request.remote_ip)
        deregister_websockrequest_handler(self)

parser = katsdpservices.ArgumentParser(usage="%(prog)s [options] <file or 'stream' or 'k7simulator'>",
                               description="Launches the HTML5 signal displays front end server. If no <file> is given then it defaults to 'stream'.")

parser.add_argument("-d", "--debug", dest="debug", type=bool, default=False,
                  help="Display debug messages.")
parser.add_argument("-m", "--memusage", dest="memusage", default=10.0, type=float,
                  help="Percentage memory usage. Percentage of available memory to be allocated for buffer. If negative then number of megabytes. (default=%(default)s)")
parser.add_argument("--html_port", dest="html_port", default=8080, type=int,
                  help="Port number used to serve html pages for signal displays (default=%(default)s)")
parser.add_argument("--data_port", dest="data_port", default=8081, type=int,
                  help="DEPRECATED Port number used to serve data for signal displays (default=%(default)s)")
parser.add_argument('--spead', type=str,
                  help="Multicast group for SPEAD stream (default=unicast)")
parser.add_argument("--spead_port", dest="spead_port", default=7149, type=int,
                  help="Port number used to connect to spead stream (default=%(default)s)")
parser.add_argument('--spead_interface', type=str, metavar="INTERFACE",
                  help="Interface to subscribe to for SPEAD data")
parser.add_argument("--config_base", dest="config_base", default="~/.katsdpdisp", type=str,
                  help="Base configuration directory where persistent user settings are stored (default=%(default)s)")
parser.add_argument("--cbf_channels", dest="cbf_channels", default=None, type=int,
                  help="Override total number of cbf_channels (default=%(default)s). There may be fewer channels received per Ingest node.")
parser.add_argument("--l0_name", dest="l0_name", default="sdp_l0", type=str,
                  help="Set stream name for telstate keys (default=%(default)s)")
parser.add_argument("--max_custom_signals", dest="max_custom_signals", default=128, type=int,
                  help="Maximum number of custom signals (default=%(default)s).")

(opts, args) = parser.parse_known_args()

if len(logging.root.handlers) > 0: logging.root.removeHandler(logging.root.handlers[0])
katsdpservices.setup_logging()

logger = logging.getLogger("katsdpdisp.time_plot")
if (opts.debug):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

#configure SPEAD to display warnings about dropped packets etc...
#logging.getLogger('spead2').setLevel(logging.WARNING)

SETTINGS_PATH=os.path.expanduser(opts.config_base)
SERVE_PATH=os.path.expanduser(SERVE_PATH)
np.random.seed(0)

if (len(args)==0):
    args=['stream']

ANTNAMEPREFIX='m%03d' #meerkat; ANTNAMEPREFIX='ant%d' #kat7

# loads usersettings
try:
    if not os.path.exists(SETTINGS_PATH):
        os.makedirs(SETTINGS_PATH)
    startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
    startupdictstr=startupfile.read()
    startupfile.close()
    startupdict=convertunicode(json.loads(startupdictstr))
    usernames=[]
    logger.info('Importing saved user settings from '+SETTINGS_PATH+'/usersettings.json')
    for username in startupdict['html_viewsettings']:
        html_viewsettings[username]=copy.deepcopy(startupdict['html_viewsettings'][username])
        html_customsignals[username]=copy.deepcopy(startupdict['html_customsignals'][username])
        html_collectionsignals[username]=copy.deepcopy(startupdict['html_collectionsignals'][username])
        html_layoutsettings[username]=copy.deepcopy(startupdict['html_layoutsettings'][username])
        usernames.append(username)
    logger.info(', '.join(usernames))
except:
    logger.warning('Unable to import saved user settings from '+SETTINGS_PATH+'/usersettings.json')
    pass

helpdict={}
try:
    hfile=open(SERVE_PATH+'/help.txt','r')
    hstr=hfile.read()
    hfile.close()
    curkey=''
    for hline in hstr.split('\n'):
        if (len(hline) and hline[0]=='[' and hline[-1]==']'):
            curkey=hline[1:-1]
            helpdict[curkey]=['help '+curkey,'']
        else:
            helpdict[curkey].append(hline)
except:
    logger.warning('Unable to load help file '+SERVE_PATH+'/help.txt')
    pass

telstate=opts.telstate
if (telstate is None):
    logger.warning('Telescope state is None. Proceeding in limited capacity, assuming for testing purposes only.')
    telstate_l0 = None
else:
    telstate_l0 = telstate.view(opts.l0_name)

poll_telstate_lasttime=0
telstate_cal_antlist=[]
telstate_cal_product_G=[]
telstate_cal_product_K=[]
telstate_cal_product_B=[]
telstate_cbf_target=[]
telstate_activity=[]
telstate_antenna_mask=[]
telstate_bls_ordering_string=opts.l0_name+'_bls_ordering'
telstate_script_name='No script active'
telstate_array_id='unknown_array'
scriptnametext=telstate_script_name

RingBufferLock=threading.Lock()
ringbufferrequestqueue=Queue()
ringbufferresultqueue=Queue()
ringbuffernotifyqueue=Queue()
opts.datafilename=args[0]
rb_process = Process(target=RingBufferProcess,args=(opts.spead, opts.spead_port, opts.spead_interface, opts.memusage, opts.max_custom_signals, opts.datafilename, opts.cbf_channels, ringbufferrequestqueue, ringbufferresultqueue, ringbuffernotifyqueue))
rb_process.start()

if (opts.datafilename is not 'stream'):
    telstate_script_name=opts.datafilename
    scriptnametext=opts.datafilename
    with RingBufferLock:
        ringbufferrequestqueue.put(['inputs',0,0,0,0,0])
        fig=ringbufferresultqueue.get()
    if (fig=={}):#an exception occurred
        logger.warning('Server exception evaluating inputs')
    elif ('logconsole' in fig):
        inputs=fig['logconsole'].split(',')
        telstate_antenna_mask=np.unique([inputname[:-1] for inputname in inputs]).tolist()
    else:
        logger.warning('Error evaluating inputs')
else:
    if ('bls_ordering' in telstate_l0):
        telstate_bls_ordering=telstate_l0['bls_ordering']
        inputs=[]
        for bls in telstate_bls_ordering:
            if bls[0] == bls[1]:
                inputs.append(bls[0])
        telstate_antenna_mask=np.unique([inputname[:-1] for inputname in inputs]).tolist()
    else:
        logger.warning("Unexpected " + telstate_bls_ordering_string + " not in telstate")
    if ('subarray_product_id' in telstate):
        telstate_array_id=telstate['subarray_product_id']
    else:
        logger.warning("Unexpected subarray_product_id not in telstate")


def graceful_exit(_signo=None, _stack_frame=None):
    logger.info("Exiting time_plot on SIGTERM")
    rb_process.terminate()
     # SIGINT gets swallowed by the HTTP server
     # so we explicitly terminate the Ring Buffer
    os.kill(os.getpid(), signal.SIGINT)
     # rely on the interrupt handler around the HTTP server
     # to peform graceful shutdown. this preserves the command
     # line Ctrl-C shutdown.

signal.signal(signal.SIGTERM, graceful_exit)
 # mostly needed for Docker use since this process runs as PID 1
 # and does not get passed sigterm unless it has a custom listener

application = tornado.web.Application([
    (r'/ws', WSHandler),
    (r'/', MainHandler),
    (r"/(.*)", tornado.web.StaticFileHandler, {"path": SERVE_PATH}),
])

try:
    httpserver = tornado.httpserver.HTTPServer(application)
    httpserver.listen(opts.html_port)
    logger.info('Started httpserver on port '+str(opts.html_port))
    # allow remote debug connections and expose httpserver, websockserver and opts
    manhole.install(oneshot_on='USR1', locals={'httpserver':httpserver, 'opts':opts})
    tornado.ioloop.IOLoop.current().start()
except KeyboardInterrupt:
    logger.warning('^C received, shutting down the web server')
    tornado.ioloop.IOLoop.current().stop()
