#!/usr/bin/python

####!/usr/bin/env python
import optparse
import katsdptelstate
from multiprocessing import Process, Queue, Pipe, Manager, current_process
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from pkg_resources import resource_filename
import mplh5canvas.simple_server as simple_server
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
colour_dict_bandpass={}

#this colour list is exclusively used by ring buffer process
def registeredcolour(signalname):
    if (signalname not in colour_dict):
        colour_dict[signalname]=np.random.random(3)*255
    return colour_dict[signalname];

#this colour list is exclusively used by main process
def registeredcolourbandpass(signalname):
    if (signalname not in colour_dict_bandpass):
        colour_dict_bandpass[signalname]=np.random.random(3)*255
    return colour_dict_bandpass[signalname];

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
def RingBufferProcess(spead_port, memusage, datafilename, ringbufferrequestqueue, ringbufferresultqueue, ringbuffernotifyqueue):
    thefileoffset=0
    typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
    fig={'title':'','xdata':np.arange(100),'ydata':[[np.nan*np.zeros(100)]],'color':np.array([[0,255,0,0]]),'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':'s','yunit':['dB'],'span':[],'spancolor':[]}
    hp = hpy()
    hpbefore = hp.heap()
    dh=katsdpdisp.KATData()
    if (datafilename=='stream'):
        dh.start_spead_receiver(port=spead_port,capacity=memusage/100.0,notifyqueue=ringbuffernotifyqueue,store2=True)
        datasd=dh.sd
    elif (datafilename=='k7simulator'):
        dh.start_direct_spead_receiver(capacity=memusage/100.0,store2=True)
        datasd=dh.sd
    else:
        try:
            dh.load_ar1_data(datafilename, rows=300, startrow=thefileoffset, capacity=memusage/100.0, store2=True)
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
            if (thelayoutsettings=='get_bls_ordering'):
                ringbufferresultqueue.put(datasd.cpref.bls_ordering)
                continue
            if (thelayoutsettings=='info'):
                fig={'logconsole':'katsdpdisp version: '+katsdpdisp.__version__+'\nreceiver alive: '+str(datasd.receiver.isAlive())+'\nheap count: '+str(datasd.receiver.heap_count)+'\ntimeseries slots: %d\nspectrum slots: %d\nwmx slots: %d'%(datasd.storage.timeseriesslots,datasd.storage.slots,datasd.storage.blmxslots)+'\nnbaselines: '+str(len(datasd.cpref.bls_ordering))+'\nnchannels: '+str(datasd.receiver.channels)+'\nblmx nchannels: '+str(datasd.storage.blmxn_chans)+'\ncenter freq: '+str(datasd.receiver.center_freq)+'\nchannel bandwidth: '+str(datasd.receiver.channel_bandwidth)}
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
                    dh.load_ar1_data(datafilename, rows=300, startrow=thefileoffset, capacity=memusage/100.0, store2=True, timeseriesmaskstr=datasd.storage.timeseriesmaskstr)
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
                
                ts = datasd.select_timeseriesdata(product=0, start_time=0, end_time=1e100, include_ts=True)[0]#gets all timestamps only
                ch=datasd.receiver.center_freqs_mhz[:]
                if (len(ts)>1):
                    samplingtime=ts[-1]-ts[-2]
                else:
                    samplingtime=np.nan
                if (theviewsettings['figtype']=='timeseries'):
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
                            signal = datasd.select_timeseriesdata(dtype=thetype, product=tuple(product), start_time=ts[0], end_time=ts[-1], include_ts=False)
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
                        signal = datasd.select_timeseriesdata(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False)
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
                    fig['title']='Timeseries'
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
                            signal = datasd.select_timeseriesdata(dtype=thetype, product=tuple(product), start_time=0, end_time=-datalength, include_ts=False)
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
                        signal = datasd.select_timeseriesdata(dtype=thetype, product=product, start_time=0, end_time=-datalength, include_ts=False)
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
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
                        ydata=[np.nan*thech]
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
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
                elif (theviewsettings['figtype'][:4]=='blmx'):
                    polstr = theviewsettings['figtype'][4:]
                    mxdata,phdata = datasd.select_blxvalue(pol=polstr)
                    if (theviewsettings['type']=='pow'):
                        mxdata=10.0*np.log10(mxdata)
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
                    fig['mxdata']=mxdata
                    fig['phdata']=phdata*180.0/np.pi
                    fig['ydata']=[]
                    fig['xdata']=np.array([0,1])
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['title']='Baseline matrix '+polstr
                    legendx=[]
                    legendy=[]
                    for inp in datasd.cpref.inputs:
                        if (inp[-1]==polstr[0]):
                            legendx.append(str(int(inp[1:-1]))+inp[-1])
                        if (inp[-1]==polstr[-1]):
                            legendy.append(str(int(inp[1:-1]))+inp[-1])
                    fig['legendx']=legendx
                    fig['legendy']=legendy
                    fig['lastts']=ts[-1]
                    fig['lastdt']=samplingtime
                    fig['version']=theviewsettings['version']
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
websockrequest_handlers = {}
websockrequest_type = {}
websockrequest_time = {}
websockrequest_lasttime = {}
websockrequest_username = {}
new_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[]}


ingest_signals={}
failed_update_ingest_signals_lastts=0
max_custom_signals=128

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
    if (len(ingest_signals)>max_custom_signals):
        logger.info('Number of customsignals %d exceeds %d:'%(len(ingest_signals),max_custom_signals))
        sigs=ingest_signals.keys()
        times=[ingest_signals[sig] for sig in sigs]
        sind=np.argsort(times)
        for ind in sind[max_custom_signals:]:
            del ingest_signals[sigs[ind]]
    if (changed):
        ####set custom signals on ingest
        thecustomsignals = np.array(sorted(ingest_signals.keys()), dtype=np.uint32)
        logger.info('Trying to set customsignals to:'+repr(thecustomsignals))
        try:
            result=telstate.add('sdp_sdisp_custom_signals',thecustomsignals)
            logger.info('telstate set custom signals result: '+repr(result))
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
    global telstate_data_target
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
            if (theviewsettings['figtype']=='timeseries'):
                customproducts,outlierproducts,processtime=send_timeseries(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:11]=='periodogram'):
                customproducts,outlierproducts,processtime=send_periodogram(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:8]=='spectrum'):
                customproducts,outlierproducts,processtime=send_spectrum(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:9]=='waterfall'):
                customproducts,outlierproducts,processtime=send_waterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:3]=='lag'):
                customproducts,outlierproducts,processtime=send_lag(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:4]=='blmx'):
                customproducts,outlierproducts,processtime=send_blmx(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:8]=='bandpass'):
                customproducts,outlierproducts,processtime=send_bandpass(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
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
        elif (args[0]=='blmx'):
            logger.info(repr(args))
            html_viewsettings[username].append({'figtype':'blmx'+str(args[1]) ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0][:3]=='wmx' and (args[0][:5]=='wmxhh' or args[0][:5]=='wmxhv' or args[0][:5]=='wmxvh' or args[0][:5]=='wmxvv')):
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
        elif (args[0][:9]=='waterfall'):#creates new waterfall plot
            logger.info(repr(args))
            if (args[0][:14]=='waterfallphase'):
                html_viewsettings[username].append({'figtype':'waterfall'+str(args[0][14:]),'type':'phase','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            else:
                html_viewsettings[username].append({'figtype':str(args[0]),'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0][:3]=='lag'):#creates new lag plot
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
        elif (args[0][:11]=='periodogram'):#creates new periodogram plot
            logger.info(repr(args))
            if (args[0][11:].replace(' ','').isdigit()):
                figtype='periodogram%d'%(int(args[0][11:].replace(' ','')))
            else:
                figtype='periodogram'
            html_viewsettings[username].append({'figtype':figtype,'type':'pow','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0][:8]=='bandpass'):#creates new bandpass plot
            logger.info(repr(args))
            if (args[0][11:].replace(' ','').isdigit()):
                figtype='bandpass%d'%(int(args[0][8:].replace(' ','')))
            else:
                figtype='bandpass'
            html_viewsettings[username].append({'figtype':figtype,'type':'pow','xtype':'','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','processtime':0,'version':0})
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+'["'+'","'.join([fig['figtype'] for fig in html_viewsettings[username]])+'"]'+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0][:8]=='spectrum'):#creates new spectrum plot
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
                    result=telstate.add('sdp_sdisp_timeseries_mask',weightedmask)
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
                    if (thekey in telstate):
                        if (thekey=='obs_params'):
                            entries=telstate.get_range('obs_params',0)
                            obs_params=dict(entry[0].split(' ', 1) for entry in entries)
                            for obskey,obsvalue in obs_params.iteritems():
                                send_websock_cmd('logconsole("'+obskey+': '+obsvalue+'",true,true,true)',handlerkey)
                        elif telstate.is_immutable(thekey):
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
                Process(target=RingBufferProcess,args=(opts.spead_port, opts.memusage, opts.datafilename, ringbufferrequestqueue, ringbufferresultqueue)).start()
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
                if ('data_target' in telstate):
                    data_target=telstate.get_range('data_target',st=0 if (len(telstate_data_target)==0) else telstate_data_target[-1][1]+0.01)
                    for thisdata_target in data_target:
                        telstate_data_target.append((thisdata_target[0].split(',')[0].split(' |')[0].split('|')[0],thisdata_target[1]))
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
                        if ('antenna_mask' in telstate):
                            telstate_antenna_mask=telstate['antenna_mask']
                        else:
                            logger.warning("Unexpected antenna_mask not in telstate")
                        entries=telstate.get_range('obs_params',0)
                        obs_params=dict(entry[0].split(' ', 1) for entry in entries)
                        telstate_script_name=obs_params['script_name'][1:-1].split('/')[-1]
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
                        while (itarget<len(telstate_data_target)):
                            if (telstate_data_target[itarget][1]<telstate_activity[idata][1]):
                                currenttargetname=telstate_data_target[itarget][0]
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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),timeseries_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),timeseries_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),timeseries_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),timeseries_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),timeseries_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),timeseries_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            send_websock_data(pack_binarydata_msg('fig[%d].sensorname'%(ifigure),sensorname,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xsensor'%(ifigure),sensorts,'I'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].ysensor'%(ifigure),sensorsignal,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].textsensor'%(ifigure),textsensor,'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].xtextsensor'%(ifigure),textsensorts,'I'),handlerkey);count+=1;
            for ispan,span in enumerate(timeseries_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
                for ispan,span in enumerate(timeseries_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
    return [],[],processtime


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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),periodogram_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),periodogram_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),periodogram_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),periodogram_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),periodogram_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),periodogram_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            for ispan,span in enumerate(periodogram_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
    return [],[],processtime

def send_bandpass(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        startproctime=time.time()
        if (telstate is not None):
            if ('cal_product_B' in telstate):
                [(cal_B,cal_B_timestamp)]=telstate.get_range('cal_product_B')
                if (True):
                    ydata=[]
                    color=[]
                    legend=[]
                    ants=telstate.get('cal_antlist')
                    cfreq=telstate.get('cbf_center_freq')*1e-6
                    bwidth=telstate.get('cbf_bandwidth')*1e-6
                    nchan=telstate.get('sdp_cbf_channels')
                    ch=np.linspace(cfreq-bwidth/2.0,cfreq+bwidth/2.0,nchan)
                    start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                    thech_=np.arange(start_chan,stop_chan,chanincr)
                    for ipol in range(cal_B.shape[1]):
                        for iant in range(cal_B.shape[2]):
                            signal=cal_B[:,ipol,iant].reshape(-1)
                            ydata.append(signal)
                            legend.append(ants[iant]+['h','v'][ipol])
                            color.append(np.r_[registeredcolourbandpass(legend[-1]),0])
                    if (len(ydata)==0):
                        ydata=[np.nan*thech]
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
                    fig['title']='Bandpass at '+time.asctime(time.localtime(cal_B_timestamp))
                    fig['lastts']=cal_B_timestamp
                    fig['lastdt']=0
                    fig['version']=theviewsettings['version']
                    fig['showtitle']=theviewsettings['showtitle']
                    fig['showlegend']=theviewsettings['showlegend']
                    fig['showxlabel']=theviewsettings['showxlabel']
                    fig['showylabel']=theviewsettings['showylabel']
                    fig['showxticklabel']=theviewsettings['showxticklabel']
                    fig['showyticklabel']=theviewsettings['showyticklabel']
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
        processtime=time.time()-startproctime
        count=0
        if (lastrecalc<bandpass_fig['version'] or fig['lastts']>lastts+0.01):
            local_yseries=(bandpass_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),bandpass_fig['version'],'i'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),bandpass_fig['lastts'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),bandpass_fig['lastdt'],'d'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),bandpass_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),bandpass_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),bandpass_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),bandpass_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),bandpass_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),bandpass_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            for ispan,span in enumerate(periodogram_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
        return bandpass_fig['customproducts'],bandpass_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime

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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),spectrum_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),spectrum_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),spectrum_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),spectrum_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),spectrum_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),spectrum_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            for ispan,span in enumerate(spectrum_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
    return [],[],processtime


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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),waterfall_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),waterfall_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),waterfall_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),waterfall_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),waterfall_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),waterfall_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            for ispan,span in enumerate(waterfall_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
    return [],[],processtime

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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),lag_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),lag_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),lag_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),lag_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),lag_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),lag_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            for ispan,span in enumerate(lag_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
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
    return [],[],processtime

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
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),blmx_fig['showtitle'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),blmx_fig['showlegend'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),blmx_fig['showxlabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),blmx_fig['showylabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showxticklabel'%(ifigure),blmx_fig['showxticklabel'],'s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].showyticklabel'%(ifigure),blmx_fig['showyticklabel'],'s'),handlerkey);count+=1;
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
            send_websock_data(pack_binarydata_msg('fig[%d].mxdata'%(ifigure),(blmx_fig['mxdata'])[:],'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].phdata'%(ifigure),(blmx_fig['phdata'])[:],'B'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        return blmx_fig['customproducts'],blmx_fig['outlierproducts'],processtime
    except Exception, e:
        logger.warning("User event exception %s" % str(e), exc_info=True)
    return [],[],processtime

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
        # print 'PARSING s=',s,'thread=',thread.get_ident()
        action = s[1:s.find(" ")]
        args = s[s.find("args='")+6:-2].split(",")
        websockrequest_type[request]=action
        if (request in websockrequest_lasttime):
            websockrequest_lasttime[request]=websockrequest_time[request]
        else:
            websockrequest_lasttime[request]=time.time()
        if (request not in websockrequest_username):
            if (args[0]=='setusername'):
                websockrequest_username[request]='no-name'
            else:
                raise ValueError('Closing data connection. Unregistered request handler not allowed: '+str(request))
        websockrequest_time[request]=time.time()
        if (action=='data_user_event_timeseries'):
            handle_websock_event(request,*args)
        
    except AttributeError:
        logger.warning("Cannot find request method %s" % s)

def send_websock_data(binarydata, handlerkey):
    try:
        handlerkey.ws_stream.send_message(binarydata,binary=True)
    except AttributeError:         # connection has gone
        logger.warning("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)" % str(e), exc_info=True)
        logger.warning("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_websockrequest_handler(handlerkey)

def send_websock_cmd(cmd, handlerkey):
    try:
        frame="/*exec_user_cmd*/ function callme(){%s; return;};callme();" % cmd;#ensures that vectors of data is not sent back to server!
        handlerkey.ws_stream.send_message(frame.decode('utf-8'))
    except AttributeError:
         # connection has gone
        logger.warning("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)" % str(e), exc_info=True)
        logger.warning("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_websockrequest_handler(handlerkey)

def register_websockrequest_handler(request):
    websockrequest_handlers[request] = request.connection.remote_addr[0]
    
def deregister_websockrequest_handler(request):
    if (request in websockrequest_type):
        del websockrequest_type[request]
    if (request in websockrequest_time):
        del websockrequest_time[request]
    if (request in websockrequest_lasttime):
        del websockrequest_lasttime[request]
    if (request in websockrequest_username):
        del websockrequest_username[request]
    if (request in websockrequest_handlers):
        del websockrequest_handlers[request]
    del request

def websock_transfer_data(request):
    register_websockrequest_handler(request)
    while True:
        try:
            line = request.ws_stream.receive_message()
            parse_websock_cmd(line,request)
        except Exception, e:
            logger.warning("Caught exception (%s). Removing registered handler" % str(e))
            deregister_websockrequest_handler(request)
            return
    
class htmlHandler(BaseHTTPRequestHandler):
            
    def handle_command(self,cmd):
        cmdlist=cmd.split(',')
        if (cmdlist[0]=='close websocket'):
            webid=int(cmdlist[1])
            deregister_htmlrequest_handler(webid)
            return 'ok'
        elif (cmdlist[0]=='set username'):
            #set username:viewnumber for this handler, copies settings if numbered view corresponds to existing view
            #could be just username, or username with view specification
            #if just username provided, then appends unique view specification
            #if view specification provided then if this view exists elsewhere, then copy its settings
            webid=int(cmdlist[1])
            username=cmdlist[2]
            spusername=username.split(':')
            if (len(spusername)>1):# eg operator:mainview
                #copies view settings if defined elsewhere already for this view of this user
                settingsdict=dict((val['username'],val['settings']) for val in htmlrequest_handlers.values())
                if (settingsdict.has_key(username)):
                    htmlrequest_handlers[webid]['settings']=settingsdict[username]
                #TODO else possibly copy default views settings
                htmlrequest_handlers[webid]['username']=username
            else:#append unique view number to username-typical behaviour when creating new web page
                usernamelist=[val['username'] for val in htmlrequest_handlers.values()]
                for count in range(len(usernamelist)+1):
                    if (username+':'+str(count) not in usernamelist):
                        htmlrequest_handlers[webid]['username']=username+':'+str(count)
                        break
            return 'ok'
        elif (cmdlist[0]=='set settings'):#set settings for all users of this username with same numbered view
            webid=int(cmdlist[1])
            settings=cmdlist[2]
            for key in htmlrequest_handlers.keys():
                if (htmlrequest_handlers[webid]['username']==htmlrequest_handlers[key]['username']):
                    htmlrequest_handlers[key]['settings']=settings
            return 'ok'
        elif (cmdlist[0]=='get settings'):
            webdid=int(cmdlist[1])
            return htmlrequest_handlers[webid]['settings']
        return 'unknown command: '+cmd
        
    #intercepts commands sent from data collector processes
    def parse_request(self):
        if (self.raw_requestline[:7]=='/*cmd*/'):
            #logger.info('raw request:'+self.raw_requestline)
            response=self.handle_command(self.raw_requestline[7:-1])
            self.wfile.write(response);
            self.command = None  
            self.requestline = ""
            self.request_version = self.default_request_version
            self.close_connection = 1
            return False
        else:
            return BaseHTTPRequestHandler.parse_request(self)
        
        
    #Handler for the GET requests
    def do_GET(self):
        if self.path=="/":
            self.path="/index.html"

        try:
            #Check the file extension required and
            #set the right mime type

            sendReply = False
            if self.path.endswith(".html"):
                mimetype='text/html'
                sendReply = True
            if self.path.endswith(".ico"):
                mimetype='image/x-icon'
                sendReply = True
            if self.path.endswith(".png"):
                mimetype='image/png'
                sendReply = True
            if self.path.endswith(".jpg"):
                mimetype='image/jpg'
                sendReply = True
            if self.path.endswith(".gif"):
                mimetype='image/gif'
                sendReply = True
            if self.path.endswith(".js"):
                mimetype='application/javascript'
                sendReply = True
            if self.path.endswith(".css"):
                mimetype='text/css'
                sendReply = True

            if sendReply == True:
                #Open the static file requested and send it
                f = open(SERVE_PATH + self.path)
                self.send_response(200)
                self.send_header('Content-type',mimetype)
                self.end_headers()
                filetext=f.read()
                if (self.path=="/index.html"):
                    filetext=filetext.replace('<!--data_port-->',str(opts.data_port)).replace('<!--scriptname_text-->',scriptnametext)
                
                self.wfile.write(filetext)
                f.close()
                    
            return

        except IOError:
            self.send_error(404,'File Not Found: %s' % self.path)

#determines unused webid by reusing old webid values
def getFreeWebID():
    webid=htmlrequest_handlers.keys()#list of currently used webid's
    webid.append(0)
    swebid=np.sort(webid)
    igaps=np.nonzero(np.diff(swebid)>1)[0]
    if (len(igaps)>0):
        freeid=swebid[igaps[0]]+1#chooses first free gap
    else:
        freeid=swebid[-1]+1
    return freeid

def register_htmlrequest_handler(requesthandler):
    webid=getFreeWebID()
    htmlrequest_handlers[webid] = {'handler':requesthandler,'username':'','settings':''}
    return webid
    
def deregister_htmlrequest_handler(webid):
    htmlrequest_handlers.pop(webid)#del rv?

parser = katsdptelstate.ArgumentParser(usage="%(prog)s [options] <file or 'stream' or 'k7simulator'>",
                               description="Launches the HTML5 signal displays front end server. If no <file> is given then it defaults to 'stream'.")

parser.add_argument("-d", "--debug", dest="debug", type=bool, default=False,
                  help="Display debug messages.")
parser.add_argument("-m", "--memusage", dest="memusage", default=10.0, type=float,
                  help="Percentage memory usage. Percentage of available memory to be allocated for buffer (default=%(default)s)")
parser.add_argument("--rts", action='store_true', dest="rts_antenna_labels", default=True,
                  help="DEPRECATED Use RTS style antenna labels (eg m001,m002) instead of KAT-7 style (eg ant1,ant2)")
parser.add_argument("--html_port", dest="html_port", default=8080, type=int,
                  help="Port number used to serve html pages for signal displays (default=%(default)s)")
parser.add_argument("--data_port", dest="data_port", default=8081, type=int,
                  help="Port number used to serve data for signal displays (default=%(default)s)")
parser.add_argument("--spead_port", dest="spead_port", default=7149, type=int,
                  help="Port number used to connect to spead stream (default=%(default)s)")
parser.add_argument("--capture_server", dest="capture_server", default="localhost:2040", type=str,
                  help="DEPRECATED Server ip-address:port that runs kat_capture (default=%(default)s)")
parser.add_argument("--config_base", dest="config_base", default="~/.katsdpdisp", type=str,
                  help="Base configuration directory where persistent user settings are stored (default=%(default)s)")

(opts, args) = parser.parse_known_args()

if len(logging.root.handlers) > 0: logging.root.removeHandler(logging.root.handlers[0])
formatter = logging.Formatter("%(asctime)s.%(msecs)dZ - %(filename)s:%(lineno)s - %(levelname)s - %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
sh = logging.StreamHandler()
sh.setFormatter(formatter)
logging.root.addHandler(sh)

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

poll_telstate_lasttime=0
telstate_data_target=[]
telstate_activity=[]
telstate_antenna_mask=[]
telstate_script_name='No script active'
scriptnametext=telstate_script_name

RingBufferLock=threading.Lock()
ringbufferrequestqueue=Queue()
ringbufferresultqueue=Queue()
ringbuffernotifyqueue=Queue()
opts.datafilename=args[0]
rb_process = Process(target=RingBufferProcess,args=(opts.spead_port, opts.memusage, opts.datafilename, ringbufferrequestqueue, ringbufferresultqueue, ringbuffernotifyqueue))
rb_process.start()
htmlrequest_handlers={}

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

try:
    websockserver=simple_server.WebSocketServer(('', opts.data_port), websock_transfer_data, simple_server.WebSocketRequestHandler)
    logger.info('Started data websocket server on port '+str(opts.data_port))
    thread.start_new_thread(websockserver.serve_forever, ())
except Exception, e:
    logger.warning("Failed to create data websocket server. (%s)" % str(e))
    sys.exit(1)

try:
    server = HTTPServer(("", opts.html_port), htmlHandler)
    logger.info('Started httpserver on port '+str(opts.html_port))
    manhole.install(oneshot_on='USR1', locals={'server':server, 'websockserver':websockserver, 'opts':opts})
     # allow remote debug connections and expose server, websockserver and opts
    server.serve_forever()
except KeyboardInterrupt:
    logger.warning('^C received, shutting down the web server')
    server.socket.close()

websockserver.shutdown()

