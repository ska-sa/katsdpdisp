#!/usr/bin/python

####!/usr/bin/env python
import optparse
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
import thread
import struct
import sys
import logging
import numpy as np
import copy
import katsdpdisp
import re
import json
import resource
import gc
from guppy import hpy
import katcp

SETTINGS_PATH='~/.katsdpdisp'
SERVE_PATH=resource_filename('katsdpdisp', 'html')

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
# client = katcp.BlockingClient('192.168.193.5',2040)#note this is kat-dc1.karoo.kat.ac.za
# client.is_connected()
# client.start()
# client.is_connected()
# ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.193.7'), timeout=5)
# ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.6.110'), timeout=5)
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

def registeredcolour(signalname):
    if (signalname not in colour_dict):
        colour_dict[signalname]=np.random.random(3)*255
    return colour_dict[signalname];

#returns minimum and maximum channel numbers, and channel increment, and channels
def getstartstopchannels(ch_mhz,thetype,themin,themax,view_nchannels):
    if (thetype=='mhz'):
        if (themin==None or type(themin)==list or not np.isfinite(themin)):
            stop_channel=len(ch_mhz)
        else:
            stop_channel=int(((themin-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))+1
        if (themax==None or type(themax)==list or not np.isfinite(themax)):
            start_channel=0
        else:
            start_channel=int(((themax-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))
    elif (thetype=='ghz'):
        if (themin==None or type(themin)==list or not np.isfinite(themin)):
            stop_channel=len(ch_mhz)
        else:
            stop_channel=int(((themin*1e3-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))+1
        if (themax==None or type(themax)==list or not np.isfinite(themax)):
            start_channel=0
        else:
            start_channel=int(((themax*1e3-ch_mhz[0])/(ch_mhz[-1]-ch_mhz[0]))*len(ch_mhz))
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


#import objgraph

#idea is to store the averaged time series profile in channel 0
def RingBufferProcess(spead_port, memusage, datafilename, ringbufferrequestqueue, ringbufferresultqueue):
    typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
    fig={'title':'','xdata':np.arange(100),'ydata':[[np.nan*np.zeros(100)]],'color':np.array([[0,255,0,0]]),'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':'s','yunit':['dB'],'span':[],'spancolor':[]}
    hp = hpy()
    hpbefore = hp.heap()
    dh=katsdpdisp.KATData()
    if (datafilename=='stream'):
        dh.start_spead_receiver(port=spead_port,capacity=memusage/100.0,store2=True)
        datasd=dh.sd
    elif (datafilename=='k7simulator'):
        dh.start_direct_spead_receiver(capacity=memusage/100.0,store2=True)
        datasd=dh.sd
    else:
        try:
            dh.load_k7_data(datafilename,rows=300,startrow=0)
        except Exception,e:
            print time.asctime()+" Failed to load file using k7 loader (%s)" % e
            dh.load_ff_data(datafilename)
        datasd=dh.sd_hist
    print 'Started ring buffer process'
    warnOnce=True
    try:
        while(True):
            #datasd.storage.set_mask('..170,220..')
            #ts = datasd.select_data(product=0, start_time=0, end_time=-1, start_channel=0, stop_channel=0, include_ts=True)[0]#gets last timestamp only
            #ts[0] contains times
            #antbase=np.unique([0 if len(c)!=5 else int(c[3:-1])-1 for c in datasd.cpref.inputs])
            #datasd.cpref.inputs=['ant1h','ant1v','ant2h','ant2v','ant3h','ant3v','ant4h','ant4v','ant5h','ant5v','ant6h','ant6v']
            #print antbase
            #ts[0] # [  1.37959922e+09   1.37959922e+09]
            [thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels]=ringbufferrequestqueue.get()

            if (thelayoutsettings=='setflags'):
                datasd.storage.set_mask(str(','.join(theviewsettings)))
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
            if (thelayoutsettings=='info'):
                fig={'logconsole':'isAlive(): '+str(datasd.receiver.isAlive())+'\nheap count:'+str(datasd.receiver.heap_count)+'\nnchannels:'+str(datasd.receiver.channels)+'\ncenter freq: '+str(datasd.receiver.center_freq)+'\nchannel bandwidth: '+str(datasd.receiver.channel_bandwidth)}
                ringbufferresultqueue.put(fig)
                continue                
            if (thelayoutsettings=='memoryleak'):
                gc.collect()
                hpafter = hp.heap()
                hpleftover=hpafter-hpbefore
                print 'Memory usage %s (kb)'%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                print hpleftover
                fig={'logconsole':'Memory usage %s (kb)\n'%(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)+' leftover objects= '+str(hpleftover)}
                ringbufferresultqueue.put(fig)
                continue
            if (thelayoutsettings=='RESTART'):
                fig={'logconsole':'Exiting ring buffer process'}
                ringbufferresultqueue.put(fig)
                return
            if (thelayoutsettings=='restartspead'):
                print datasd.ig._new_names.keys()
                fig={'logconsole':'datasd.ig._new_names.keys()= '+str(datasd.ig._new_names.keys())}
                ringbufferresultqueue.put(fig)
                datasd.ig._new_names={}
                
                # objgraph.show_refs([dh],filename='objgraph_refs.png')
                # objgraph.show_backrefs([dh],filename='objgraph_backrefs.png')
                # print 'show_most_common_types()'
                # objgraph.show_most_common_types()
                # print 'objgraph.show_growth(limit=3)'
                # objgraph.show_growth(limit=3)
                # print 'objgraph.get_leaking_objects()'
                # roots = objgraph.get_leaking_objects()
                # print 'objgraph.show_most_common_types(objects=roots)'
                # objgraph.show_most_common_types(objects=roots)
                # objgraph.show_refs(roots[:3], refcounts=True, filename='roots.png')
                # dh.sd.stop()
                # del dh
                # del datasd
                # dh=katsdpdisp.KATData()
                # dh.start_spead_receiver(port=spead_port,capacity=memusage/100.0,store2=True)
                # datasd=dh.sd                
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
                
                ts = datasd.select_data(product=0, start_time=0, end_time=1e100, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
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
                                    signal = datasd.select_data_collection(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
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
                                    signal = datasd.select_data_collection(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod)
                                    if (iprod==4):
                                        c=np.array(np.r_[cbase,0],dtype='int')
                                    color.append(c)
                        
                    for product in customsignals:
                        if (list(product) in datasd.cpref.bls_ordering):
                            signal = datasd.select_data(dtype=thetype, product=tuple(product), start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
                            signal=np.array(signal).reshape(-1)
                        else:
                            signal=np.nan*np.ones(len(ts))
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(printablesignal(product))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    outlierhash=0
                    for ipr,product in enumerate(outlierproducts):
                        outlierhash=(outlierhash+product<<3)%(2147483647+ipr)
                        signal = datasd.select_data(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
                        signal=np.array(signal).reshape(-1)
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(datasd.cpref.id_to_real_str(id=product,short=True).replace('m00','').replace('m0','').replace('m','').replace('ant','').replace(' * ',''))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    if (len(ydata)==0):
                        ydata=[np.nan*ts]
                        color=[np.array([255,255,255,0])]
                    if (theviewsettings['type']=='pow'):
                        ydata=20.0*np.log10(ydata)
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
                elif (theviewsettings['figtype']=='spectrum'):
                    #nchannels=datasd.receiver.channels
                    ydata=[]
                    color=[]
                    legend=[]
                    start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                    thech_=np.arange(start_chan,stop_chan,chanincr)
                    collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                    outlierproducts=[]
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
                                    signal,theflags = datasd.select_data_collection(dtype=thetype, product=product, end_time=-1, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
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
                                    signal,theflags = datasd.select_data_collection(dtype=thetype, product=product, end_time=-1, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                                    flags=np.logical_or(flags,theflags.reshape(-1))
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod)
                                    if (iprod==4):
                                        c=np.array(np.r_[cbase,0],dtype='int')
                                    color.append(c)
                                
                    for product in customsignals:
                        if (list(product) in datasd.cpref.bls_ordering):
                            signal,theflags = datasd.select_data(dtype=thetype, product=tuple(product), end_time=-1, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            flags=np.logical_or(flags,theflags.reshape(-1))
                            signal=np.array(signal).reshape(-1)
                        else:
                            signal=np.nan*np.ones(len(thech))
                        ydata.append(signal)#should check that correct corresponding values are returned
                        legend.append(printablesignal(product))
                        color.append(np.r_[registeredcolour(legend[-1]),0])
                    for product in outlierproducts:
                        signal,theflags = datasd.select_data(dtype=thetype, product=product, end_time=-1, include_ts=False,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
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
                        halfchanwidthmhz=-abs(ch[0]-ch[1])/2.0
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
                        ydata=[np.nan*ts]
                        color=[np.array([255,255,255,0])]
                    if (theviewsettings['type']=='pow'):
                        ydata=20.0*np.log10(ydata)
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
                        
                elif (theviewsettings['figtype'][:9]=='waterfall'):
                    start_chan,stop_chan,chanincr,thech=getstartstopchannels(ch,theviewsettings['xtype'],theviewsettings['xmin'],theviewsettings['xmax'],view_npixels)
                    collections=['auto0','auto100','auto25','auto75','auto50','autohh0','autohh100','autohh25','autohh75','autohh50','autovv0','autovv100','autovv25','autovv75','autovv50','autohv0','autohv100','autohv25','autohv75','autohv50','cross0','cross100','cross25','cross75','cross50','crosshh0','crosshh100','crosshh25','crosshh75','crosshh50','crossvv0','crossvv100','crossvv25','crossvv75','crossvv50','crosshv0','crosshv100','crosshv25','crosshv75','crosshv50']
                    collectionsalt=['automin','automax','auto25','auto75','auto','autohhmin','autohhmax','autohh25','autohh75','autohh','autovvmin','autovvmax','autovv25','autovv75','autovv','autohvmin','autohvmax','autohv25','autohv75','autohv','crossmin','crossmax','cross25','cross75','cross','crosshhmin','crosshhmax','crosshh25','crosshh75','crosshh','crossvvmin','crossvvmax','crossvv25','crossvv75','crossvv','crosshvmin','crosshvmax','crosshv25','crosshv75','crosshv']
                    productstr=theviewsettings['figtype'][9:]
                    if (thelayoutsettings['showonlineflags']=='on'):#more efficient to separate these out
                        flags=0
                        if (productstr in collections):
                            product=collections.index(productstr)
                            productstr=collectionsalt[product]
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            flags=np.logical_or(flags,rvcdata[2])
                        elif (productstr in collectionsalt):
                            product=collectionsalt.index(productstr)
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            flags=np.logical_or(flags,rvcdata[2])
                        else:                        
                            product=decodecustomsignal(productstr)
                            if (list(product) in datasd.cpref.bls_ordering):
                                rvcdata = datasd.select_data(dtype=thetype, product=tuple(product), end_time=-120, include_ts=True,include_flags=True,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                                flags=np.logical_or(flags,rvcdata[2])
                            else:
                                thets=datasd.select_data(product=0, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                rvcdata=[thets,np.nan*np.ones([len(thets),len(thech)])]                            
                        
                        if (len(rvcdata[0])==1):#reshapes in case one time dump of data (select data changes shape)
                            rvcdata[1]=np.array([rvcdata[1]])
                            flags=np.array([flags])
                    
                        cdata=rvcdata[1]
                        if (len(np.shape(flags))>0):
                            shp=np.shape(cdata)
                            tmp=cdata.reshape(-1)
                            tmp[np.nonzero(flags.reshape(-1))[0]]=np.nan;
                            cdata=tmp.reshape(shp)
                    else:
                        if (productstr in collections):
                            product=collections.index(productstr)
                            productstr=collectionsalt[product]
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                        elif (productstr in collectionsalt):
                            product=collectionsalt.index(productstr)
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                        else:                        
                            product=decodecustomsignal(productstr)
                            if (list(product) in datasd.cpref.bls_ordering):
                                rvcdata = datasd.select_data(dtype=thetype, product=tuple(product), end_time=-120, include_ts=True,include_flags=False,start_channel=start_chan,stop_channel=stop_chan,incr_channel=chanincr)
                            else:
                                thets=datasd.select_data(product=0, end_time=-120, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                                rvcdata=[thets,np.nan*np.ones([len(thets),len(thech)])]                            
                        
                        if (len(rvcdata[0])==1):#reshapes in case one time dump of data (select data changes shape)
                            rvcdata[1]=np.array([rvcdata[1]])                    
                        cdata=rvcdata[1]
                    
                    if (theviewsettings['type']=='pow'):
                        cdata=20.0*np.log10(cdata)
                        fig['clabel']='Power'
                        fig['cunit']='dB'
                    elif (thetype=='mag'):
                        fig['clabel']='Amplitude'
                        fig['cunit']='counts'
                    else:
                        fig['clabel']='Phase'
                        fig['cunit']='rad'
                    fig['ylabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    fig['yunit']='s'
                    fig['cdata']=cdata
                    fig['ydata']=np.array(rvcdata[0])
                    fig['legend']=[]
                    fig['outlierhash']=0
                    fig['color']=[]
                    fig['span']=[]
                    fig['spancolor']=[]
                    fig['title']='Waterfall '+productstr
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
                    
                else:                        
                    fig={}
            except Exception, e:
                print '--------------------------------------------------------'
                print 'Exception in RingBufferProcess:',str(e)
                print traceback.format_exc()
                fig={}
                pass
            
            ringbufferresultqueue.put(fig)
            
    except KeyboardInterrupt:
        print '^C received, shutting down the ringbuffer process'
        

html_customsignals= {'default': [],
                    'inspectauto': [],
                    'inspectcross': [],
                    'envelopeauto': [],
                    'envelopes': [],
                     'hh': [],
                     'hv': [],
                     'vv': [],
                     'hhticks': [],
                     'hvticks': [],
                     'vvticks': [],
                     'timeseries': [('ant1h','ant1h'),('ant2h','ant2h'),('ant3h','ant3h'),('ant4h','ant4h'),('ant5h','ant5h'),('ant6h','ant6h'),('ant7h','ant7h'),('ant1v','ant1v'),('ant2v','ant2v'),('ant3v','ant3v'),('ant4v','ant4v'),('ant5v','ant5v'),('ant6v','ant6v'),('ant7v','ant7v')],
                     'spectrum': [('ant1h','ant1h'),('ant2h','ant2h'),('ant3h','ant3h'),('ant4h','ant4h'),('ant5h','ant5h'),('ant6h','ant6h'),('ant7h','ant7h'),('ant1v','ant1v'),('ant2v','ant2v'),('ant3v','ant3v'),('ant4v','ant4v'),('ant5v','ant5v'),('ant6v','ant6v'),('ant7v','ant7v')],
                     'waterfall': []
                    }
html_collectionsignals= {'default': ['auto'],
                        'inspectauto': ['auto'],
                        'inspectcross': ['cross'],
                        'envelopeauto': ['envelopeautohh','envelopeautovv'],
                        'envelopes': ['envelopeauto','envelopeautohv','envelopecross','envelopecrosshv'],
                         'hh': [],
                         'hv': [],
                         'vv': [],
                         'hhticks': [],
                         'hvticks': [],
                         'vvticks': [],
                         'timeseries': ['envelopeautohh','envelopeautovv'],
                         'spectrum': ['envelopeautohh','envelopeautovv'],
                         'waterfall': []
                        }
html_layoutsettings= {'default': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'inspectauto': {'ncols':3,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'inspectcross': {'ncols':3,'showonlineflags':'on','showflags':'on','outlierthreshold':95.0},
                      'envelopeauto': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                      'envelopes': {'ncols':2,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                         'hh':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'hv':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'vv':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'hhticks':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'hvticks':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'vvticks':    {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0},
                         'timeseries': {'ncols':1,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                         'spectrum':   {'ncols':1,'showonlineflags':'on','showflags':'on','outlierthreshold':100.0},
                         'waterfall':  {'ncols':7,'showonlineflags':'off','showflags':'on','outlierthreshold':100.0}
                        }
html_viewsettings={'default':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                             ],
                    'inspectauto':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                     {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                     {'figtype':'waterfallauto' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                  ],
                    'inspectcross':[ {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                     {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                     {'figtype':'waterfallcross' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                  ],
                    'envelopeauto':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                      {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                   ],
                    'envelopes':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                                   {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                ],
                    # 'test':  [  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'spectrum'  ,'type':'arg','xtype':'ghz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall2h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall3h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall4h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall5h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall6h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfall2h2v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfallautomax' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfallautohh' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfallautohv' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0},
                    #             {'figtype':'waterfallcross' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                    #          ],
                    'hh':  [  {'figtype':'waterfall1h1h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h2h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall7h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0}
                             ],
                    'vv':  [  {'figtype':'waterfall1v1v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v2v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall7v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0}
                             ],                   
                    'hv':  [  {'figtype':'waterfall1h1v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h2v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall7h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0}
                             ],
                    
                    'hhticks':  [  {'figtype':'waterfall1h1h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall1h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h2h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall7h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0}
                             ],
                        'hvticks':  [  {'figtype':'waterfall1h1v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h2v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5h5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5h6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6h6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6h7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall7h7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0}
                                 ],
                        'vvticks':  [  {'figtype':'waterfall1v1v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall1v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v2v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v2v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v3v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v3v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v4v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v4v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v5v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5v5v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5v6v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6v6v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                    {'figtype':'waterfall1v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'off','version':0},
                                    {'figtype':'waterfall2v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall3v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall4v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall5v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall6v7v' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0},
                                    {'figtype':'waterfall7v7v' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'off','showtitle':'off','version':0}
                                 ],
                    'timeseries':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                ],
                    'spectrum':[  {'figtype':'spectrum','type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0}
                                ],
                    'waterfall':  [  {'figtype':'waterfall1h1h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall1h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h2h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h3h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h3h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h4h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h4h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h5h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h5h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h6h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h6h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},

                                {'figtype':'waterfall1h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall2h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall3h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall4h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall5h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall6h7h' ,'type':'arg','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0},
                                {'figtype':'waterfall7h7h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'off','showxlabel':'off','showylabel':'off','showxticklabel':'off','showyticklabel':'off','showtitle':'off','version':0}
                             ]
                                 
                  }

help_dict={}
websockrequest_handlers = {}
websockrequest_type = {}
websockrequest_time = {}
websockrequest_lasttime = {}
websockrequest_username = {}
new_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[]}
timeseries_recalced=0

def handle_websock_event(handlerkey,*args):
    try:
        # print(time.asctime()+' DATA '+str(args))
        username=websockrequest_username[handlerkey]
        if (args[0]=='setusername' and username!=args[1]):
            websockrequest_username[handlerkey]=args[1]
            print args
            if (args[1] not in html_viewsettings):
                html_viewsettings[args[1]]=copy.deepcopy(html_viewsettings['default'])
            if (args[1] not in html_customsignals):
                html_customsignals[args[1]]=copy.deepcopy(html_customsignals['default'])
            if (args[1] not in html_collectionsignals):
                html_collectionsignals[args[1]]=copy.deepcopy(html_collectionsignals['default'])
            if (args[1] not in html_layoutsettings):
                html_layoutsettings[args[1]]=copy.deepcopy(html_layoutsettings['default'])
            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[args[1]]))+','+str(html_layoutsettings[args[1]]['ncols'])+')',handlerkey)
        elif (username not in html_viewsettings):
            print 'Warning: unrecognised username:',username
        elif (args[0]=='sendfigure'):
            # print args
            ifigure=int(args[1])
            reqts=float(args[2])# timestamp on browser side when sendfigure request was issued
            lastts=np.round(float(args[3])*1000.0)/1000.0
            lastrecalc=float(args[4])
            view_npixels=int(args[5])
            outlierhash=int(args[6])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                print 'Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure)
                return
            if (view_npixels<64):
                view_npixels=64
            theviewsettings=html_viewsettings[username][ifigure]
            thesignals=(html_collectionsignals[username],html_customsignals[username])
            thelayoutsettings=html_layoutsettings[username]
            if (theviewsettings['figtype']=='timeseries'):
                send_timeseries(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype']=='spectrum'):
                send_spectrum(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
            elif (theviewsettings['figtype'][:9]=='waterfall'):
                send_waterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure)
        elif (args[0]=='setzoom'):
            print args
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                print 'Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure)
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
            print args
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                print 'Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure)
                return
            theviewsettings=html_viewsettings[username][ifigure]
            theviewsettings[args[2]]=str(args[3])
            theviewsettings['version']+=1            
        elif (args[0]=='deletefigure'):
            print args
            ifigure=int(args[1])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                print 'Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure)
                return            
            html_viewsettings[username].pop(ifigure)
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='setncols'):
            print args
            html_layoutsettings[username]['ncols']=int(args[1])
            for thishandler in websockrequest_username.keys():
                if (websockrequest_username[thishandler]==username):
                    send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
        elif (args[0]=='getoutlierthreshold'):
            print args
            send_websock_cmd('logconsole("outlierthreshold=%g'%(html_layoutsettings[username]['outlierthreshold'])+'",true,true,true)',handlerkey)
        elif (args[0]=='getoutliertime'):
            print args
            ringbufferrequestqueue.put(['getoutliertime',0,0,0,0,0])
            fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating getoutliertime",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)            
        elif (args[0]=='getflags'):
            print args
            ringbufferrequestqueue.put(['getflags',0,0,0,0,0])
            fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating getflags",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)            
        elif (args[0]=='setoutlierthreshold'):
            print args
            html_layoutsettings[username]['outlierthreshold']=float(args[1])
        elif (args[0]=='setoutliertime'):
            print args
            ringbufferrequestqueue.put(['setoutliertime',float(args[1]),0,0,0,0])
        elif (args[0]=='setsignals'):
            print args
            #decodes signals of from 1h3h to ('ant1h','ant3h')
            html_customsignals[username]=[]
            standardcollections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv','envelopeauto','envelopeautohh','envelopeautovv','envelopeautohv','envelopecross','envelopecrosshh','envelopecrossvv','envelopecrosshv']
            for theviewsettings in html_viewsettings[username]:
                theviewsettings['version']+=1
            for sig in args[1:]:
                sig=str(sig)
                decodedsignal=decodecustomsignal(sig)
                if (len(decodedsignal)):
                    if (decodedsignal not in html_customsignals[username]):
                        html_customsignals[username].append(decodedsignal)
                elif (sig in standardcollections and sig not in html_collectionsignals[username]):
                    html_collectionsignals[username].append(sig)
                elif (sig=='clear'):
                    html_customsignals[username]=[]
                    html_collectionsignals[username]=[]
                elif (sig=='timeseries'):#creates new timeseries plot
                    html_viewsettings[username].append({'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
                elif (sig=='spectrum'):#creates new spectrum plot
                    html_viewsettings[username].append({'figtype':'spectrum'  ,'type':'pow','xtype':'ch','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
                elif (sig[:9]=='waterfall'):#creates new waterfall plot
                    html_viewsettings[username].append({'figtype':sig ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showxticklabel':'on','showyticklabel':'on','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)                    
                    
        elif (args[0]=='setflags'):
            print args
            for theviewsettings in html_viewsettings[username]:
                if (theviewsettings['figtype']=='spectrum'):
                    theviewsettings['version']+=1
            ringbufferrequestqueue.put(['setflags',args[1:],0,0,0,0])        
        elif (args[0]=='showonlineflags' or args[0]=='showflags'):#onlineflags on, onlineflags off; flags on, flags off
            print args
            html_layoutsettings[username][args[0]]=args[1]
            for theviewsettings in html_viewsettings[username]:
                if (theviewsettings['figtype']=='spectrum' or theviewsettings['figtype'][:9]=='waterfall'):
                    theviewsettings['version']+=1
        elif (args[0]=='getusers'):
            print args
            userstats=[]
            usrnamelist=[]
            nviewlist=[]
            for thisusrname in html_viewsettings.keys():
                usrnamelist.append(thisusrname)
                nviewlist.append(int(sum([thisusrname==usrname for usrname in websockrequest_username.values()])))
            for ind in np.argsort(nviewlist)[::-1]:
                userstats.append(usrnamelist[ind]+':'+str(nviewlist[ind]))
            try:
                startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
                startupdictstr=startupfile.read()
                startupfile.close()
            except:
                startupdictstr=''
                pass
            if (len(startupdictstr)>0):
                startupdict=convertunicode(json.loads(startupdictstr))
                send_websock_cmd('logconsole("Saved: '+','.join(startupdict['html_viewsettings'].keys())+'",true,false,false)',handlerkey)
            else:
                startupdict={'html_viewsettings':{},'html_customsignals':{},'html_collectionsignals':{},'html_layoutsettings':{}}
                send_websock_cmd('logconsole("No profiles saved",true,false,false)',handlerkey)
            send_websock_cmd('logconsole("'+','.join(userstats)+'",true,true,true)',handlerkey)
        elif (args[0]=='inputs'):
            print args
            ringbufferrequestqueue.put(['inputs',0,0,0,0,0])
            fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating inputs",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)
        elif (args[0]=='info'):
            print args
            ringbufferrequestqueue.put(['info',0,0,0,0,0])
            fig=ringbufferresultqueue.get()
            if (fig=={}):#an exception occurred
                send_websock_cmd('logconsole("Server exception occurred evaluating info",true,true,true)',handlerkey)
            elif ('logconsole' in fig):
                for printline in ((fig['logconsole']).split('\n')):
                    send_websock_cmd('logconsole("'+printline+'",true,true,true)',handlerkey)
        elif (args[0]=='memoryleak'):
            print args
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
        
        elif (args[0]=='RESTART' or args[0]=='restartspead' or args[0]=='metadata'):
            print args
            if (args[0]=='RESTART'):
                ringbufferrequestqueue.put(['RESTART',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
                if (fig=={}):#an exception occurred
                    send_websock_cmd('logconsole("Server exception occurred evaluating RESTART",true,true,true)',handlerkey)
                else:
                    send_websock_cmd('logconsole("Exit ring buffer process",true,true,true)',handlerkey)
                    time.sleep(2)
                    Process(target=RingBufferProcess,args=(opts.spead_port, opts.memusage, opts.datafilename, ringbufferrequestqueue, ringbufferresultqueue)).start()
                    print 'RESTART performed, using port=',opts.spead_port,' memusage=',opts.memusage,' datafilename=', opts.datafilename
                    send_websock_cmd('logconsole("RESTART performed.",true,true,true)',handlerkey)
                    time.sleep(2)
                    send_websock_cmd('logconsole("Reissuing metadata.",true,true,true)',handlerkey)
            if (args[0]=='restartspead'):
                ringbufferrequestqueue.put(['restartspead',0,0,0,0,0])
                fig=ringbufferresultqueue.get()
                if (fig=={}):#an exception occurred
                    send_websock_cmd('logconsole("Server exception occurred evaluating restartspead",true,true,true)',handlerkey)
                elif ('logconsole' in fig):
                    send_websock_cmd('logconsole("'+fig['logconsole']+'",true,true,true)',handlerkey)
                send_websock_cmd('logconsole("Reset performed. Now issue metadata instruction",true,true,true)',handlerkey)
            #reissue metadata (in both cases)
            capture_server,capture_server_port_str=opts.capture_server.split(':')
            try:
                client = katcp.BlockingClient(capture_server,int(capture_server_port_str))#note this is kat-dc1.karoo.kat.ac.za, not obs.kat7.karoo
                #client = katcp.BlockingClient('192.168.193.5',2040)#note this is kat-dc1.karoo.kat.ac.za, not obs.kat7.karoo
                # client.is_connected()
                client.start()
                time.sleep(0.1)            
                if client.is_connected():
                    # ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.193.7'), timeout=5)
                    # ret = client.blocking_request(katcp.Message.request('add-sdisp-ip','192.168.6.110'), timeout=5)
                    ret = client.blocking_request(katcp.Message.request('add-sdisp-ip',client._sock.getsockname()[0]), timeout=5)            
                    ret = client.blocking_request(katcp.Message.request('sd-metadata-issue'), timeout=5)
                    client.stop()
                    send_websock_cmd('logconsole("Added '+client._sock.getsockname()[0]+' to '+opts.capture_server+' list of signal displays ",true,true,true)',handlerkey)
                    print 'Added '+client._sock.getsockname()[0]+' to '+opts.capture_server+' list of signal displays'
                else:
                    print 'Unable to connect to '+opts.capture_server
                    send_websock_cmd('logconsole("Unable to connect to '+opts.capture_server+'",true,true,true)',handlerkey)                
            except:
                print 'Exception occurred in metadata'
        elif (args[0]=='server'):
            cmd=','.join(args[1:])
            print args[0],':',cmd
            ret=commands.getoutput(cmd).split('\n')
            for thisret in ret:
                send_websock_cmd('logconsole("'+thisret+'",true,true,true)',handlerkey)
        elif (args[0]=='help'):
            print args            
            if (len(args)!=1 or args[1] not in helpdict):
                for line in helpdict[args[1]]:
                    send_websock_cmd('logconsole("'+line+'",false,true,true)',handlerkey)
        elif (args[0]=='delete' and len(args)==2):#deletes specified user's settings from startup settings file as well as from server memory
            print args
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
                send_websock_cmd('logconsole("Deleted '+theusername+' from '+SETTINGS_PATH+'/usersettings.json'+'",true,false,false)',handlerkey)
            else:
                startupfile.close()        
                send_websock_cmd('logconsole("'+theusername+' not found in '+SETTINGS_PATH+'/usersettings.json'+'",true,false,false)',handlerkey)
            if (theusername in html_viewsettings):
                html_viewsettings.pop(theusername)
                html_customsignals.pop(theusername)
                html_collectionsignals.pop(theusername)
                html_layoutsettings.pop(theusername)
                send_websock_cmd('logconsole("Deleted '+theusername+' from active server memory",true,false,false)',handlerkey)
            send_websock_cmd('logconsole("Saved: '+','.join(startupdict['html_viewsettings'].keys())+'",true,false,false)',handlerkey)
            send_websock_cmd('logconsole("Active: '+','.join(html_viewsettings.keys())+'",true,true,true)',handlerkey)
        elif (args[0]=='save'):#saves this user's settings in startup settings file        
            print args
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
        elif (args[0]=='load'):#loads this user's settings from startup settings file        
            print args
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
                        send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
            elif (theusername in html_viewsettings):
                html_viewsettings[username]=copy.deepcopy(html_viewsettings[theusername])
                html_customsignals[username]=copy.deepcopy(html_customsignals[theusername])
                html_collectionsignals[username]=copy.deepcopy(html_collectionsignals[theusername])
                html_layoutsettings[username]=copy.deepcopy(html_layoutsettings[theusername])
                send_websock_cmd('logconsole("'+theusername+' not found in startup settings file, but copied from active process instead",true,false,true)',handlerkey)
                for thishandler in websockrequest_username.keys():
                    if (websockrequest_username[thishandler]==username):
                        send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+','+str(html_layoutsettings[username]['ncols'])+')',thishandler)
            else:
                send_websock_cmd('logconsole("'+theusername+' not found in '+SETTINGS_PATH+'/usersettings.json'+'",true,false,false)',handlerkey)
                send_websock_cmd('logconsole("Saved: '+','.join(startupdict['html_viewsettings'].keys())+'",true,false,false)',handlerkey)
                send_websock_cmd('logconsole("Active: '+','.join(html_viewsettings.keys())+'",true,true,true)',handlerkey)
            
    except Exception, e:
        logger.warning("User event exception %s" % str(e))
        
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
        
#decodes signals of form 1h3h to ('ant1h','ant3h')
#returns () if invalid
def decodecustomsignal(signalstr):
    sreg=re.compile('[h|v|H|V]').split(signalstr)    
    if (len(sreg)!=3 or len(sreg[2])!=0 or (not sreg[0].isdigit()) or (not sreg[1].isdigit())):
        return ();
    # return ('ant'+sreg[0]+signalstr[len(sreg[0])].lower(),'ant'+sreg[1]+signalstr[len(sreg[0])+1+len(sreg[1])].lower())
    return (ANTNAMEPREFIX%(int(sreg[0]))+signalstr[len(sreg[0])].lower(),ANTNAMEPREFIX%(int(sreg[1]))+signalstr[len(sreg[0])+1+len(sreg[1])].lower())
    
#converts eg ('ant1h','ant2h') into '1h2h'
#            ('m000h','m001h') into '0h1h'
def printablesignal(product):
    if (product[0][:3]=='ant'):
        rv=product[0][3:]
    else:
        rv=str(int(product[0][1:-1]))+product[0][-1]
    if (product[1][:3]=='ant'):
        rv+=product[1][3:]
    else:
        rv+=str(int(product[1][1:-1]))+product[1][-1]
    return rv
    

def send_timeseries(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
        timeseries_fig=ringbufferresultqueue.get()
        count=0
        if (timeseries_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return
        elif ('logconsole' in timeseries_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+timeseries_fig['logconsole']+'",true,false,true)',handlerkey)
            return
        elif ('logignore' in timeseries_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return
            
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
            for ispan,span in enumerate(timeseries_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(timeseries_fig['span'][ispan]),'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),timeseries_fig['spancolor'],'b'),handlerkey);count+=1;
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):              
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'reset','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
        else:#only send update
            where=np.where(timeseries_fig['xdata']>lastts+0.01)[0]#next time stamp index
            #print 'len(where)',len(where),'lastts',lastts,'new lastts',timeseries_fig['lastts']
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
                for itwin,twinplotyseries in enumerate(local_yseries):
                    for iline,linedata in enumerate(twinplotyseries):
                        send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'augmentydata','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
                send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
    except Exception, e:
        logger.warning("User event exception %s" % str(e))

def send_spectrum(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
        spectrum_fig=ringbufferresultqueue.get()
        count=0
        if (spectrum_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return
        elif ('logconsole' in spectrum_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+spectrum_fig['logconsole']+'",true,false,true)',handlerkey)
            return
        elif ('logignore' in spectrum_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return
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
    except Exception, e:
        logger.warning("User event exception %s" % str(e))


def send_waterfall(handlerkey,thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels,outlierhash,ifigure):
    try:
        ringbufferrequestqueue.put([thelayoutsettings,theviewsettings,thesignals,lastts,lastrecalc,view_npixels])
        waterfall_fig=ringbufferresultqueue.get()
        count=0
        if (waterfall_fig=={}):#an exception occurred
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("Server exception occurred evaluating figure'+str(ifigure)+'",true,false,true)',handlerkey)
            return
        elif ('logconsole' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            send_websock_cmd('logconsole("'+waterfall_fig['logconsole']+'",true,false,true)',handlerkey)
            return
        elif ('logignore' in waterfall_fig):
            send_websock_data(pack_binarydata_msg('fig[%d].action'%(ifigure),'none','s'),handlerkey);count+=1;
            send_websock_data(pack_binarydata_msg('fig[%d].totcount'%(ifigure),count+1,'i'),handlerkey);count+=1;
            return
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
            where=np.where(waterfall_fig['ydata']>lastts+0.01)[0]#next time stamp index
            if (len(where)>0):                
                its=np.min(where)
                local_cseries=(waterfall_fig['cdata'])[its:]
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
        logger.warning("User event exception %s" % str(e))

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
        print "Received invalid request: %s" % s
        logger.warning("Cannot find request method %s" % s)

def send_websock_data(binarydata, handlerkey):
    try:
        handlerkey.ws_stream.send_message(binarydata,binary=True)
    except AttributeError:         # connection has gone
        print "Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0]
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        print "Failed to send message (%s)" % str(e)
        print "Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0]
        deregister_websockrequest_handler(handlerkey)

def send_websock_cmd(cmd, handlerkey):
    try:
        frame="/*exec_user_cmd*/ function callme(){%s; return;};callme();" % cmd;#ensures that vectors of data is not sent back to server!
        handlerkey.ws_stream.send_message(frame.decode('utf-8'))
    except AttributeError:
         # connection has gone
        print "Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0]
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)" % str(e))
        print "Failed to send message (%s)" % str(e)
        print "Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0]
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
            print "Caught exception (%s). Removing registered handler" % str(e)
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
            #print 'raw request:',self.raw_requestline
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
                    filetext=filetext.replace('<!--data_port-->',str(opts.data_port))
                
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

# Parse command-line opts and arguments
parser = optparse.OptionParser(usage="%prog [opts] <file or 'stream' or 'k7simulator'>",
                               description="Launches the HTML5 signal displays front end server. "
                               "If no <file> is given then it defaults to 'stream'.")
parser.add_option("-d", "--debug", dest="debug", action="store_true",default=False,
                  help="Display debug messages.")
parser.add_option("-m", "--memusage", dest="memusage", default=10.0, type='float',
                  help="Percentage memory usage. Percentage of available memory to be allocated for buffer (default=%default)")
parser.add_option("--rts", dest="rts_antenna_labels", action="store_true",default=False,
                  help="Use RTS style antenna labels (eg m001,m002) instead of KAT-7 style (eg ant1,ant2)")
parser.add_option("--html_port", dest="html_port", default=8080, type='int',
                  help="Port number used to serve html pages for signal displays (default=%default)")
parser.add_option("--data_port", dest="data_port", default=8081, type='int',
                  help="Port number used to serve data for signal displays (default=%default)")
parser.add_option("--spead_port", dest="spead_port", default=7149, type='int',
                  help="Port number used to connect to spead stream (default=%default)")
parser.add_option("--capture_server", dest="capture_server", default="kat-dc1.karoo.kat.ac.za:2040", type='string',
                  help="Server ip-address:port that runs kat_capture (default=%default)")
                

(opts, args) = parser.parse_args()
SETTINGS_PATH=os.path.expanduser(SETTINGS_PATH)
SERVE_PATH=os.path.expanduser(SERVE_PATH)
np.random.seed(0)

if (len(args)==0):
    args=['stream']

if (opts.rts_antenna_labels):
    ANTNAMEPREFIX='m%03d' #meerkat
else:
    ANTNAMEPREFIX='ant%d' #kat7    
    
# loads usersettings
try:
    if not os.path.exists(SETTINGS_PATH):
        os.makedirs(SETTINGS_PATH)
    startupfile=open(SETTINGS_PATH+'/usersettings.json','r')
    startupdictstr=startupfile.read()
    startupfile.close()
    startupdict=convertunicode(json.loads(startupdictstr))
    usernames=[]
    print 'Importing saved user settings from '+SETTINGS_PATH+'/usersettings.json'
    for username in startupdict['html_viewsettings']:
        html_viewsettings[username]=copy.deepcopy(startupdict['html_viewsettings'][username])
        html_customsignals[username]=copy.deepcopy(startupdict['html_customsignals'][username])
        html_collectionsignals[username]=copy.deepcopy(startupdict['html_collectionsignals'][username])
        html_layoutsettings[username]=copy.deepcopy(startupdict['html_layoutsettings'][username])
        usernames.append(username)
    print ', '.join(usernames)
except:
    print 'Unable to import saved user settings from '+SETTINGS_PATH+'/usersettings.json'
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
    print 'Unable to load help file '+SERVE_PATH+'/help.txt'
    pass

##Disable debug warning messages that clutters the terminal, especially when streaming
np.seterr(all='ignore')
logging.basicConfig()
logger = logging.getLogger()
if (opts.debug):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.CRITICAL)
#    logger.setLevel(logging.WARNING)

ringbufferrequestqueue=Queue()
ringbufferresultqueue=Queue()
opts.datafilename=args[0]
Process(target=RingBufferProcess,args=(opts.spead_port, opts.memusage, opts.datafilename, ringbufferrequestqueue, ringbufferresultqueue)).start()
htmlrequest_handlers={}

try:
    websockserver=simple_server.WebSocketServer(('', opts.data_port), websock_transfer_data, simple_server.WebSocketRequestHandler)
    print 'Started data websocket server on port ' , opts.data_port
    thread.start_new_thread(websockserver.serve_forever, ())
    
except Exception, e:
    print "Failed to create data websocket server. (%s)" % str(e)
    sys.exit(1)

try:
    server = HTTPServer(("", opts.html_port), htmlHandler)
    print 'Started httpserver on port ' , opts.html_port
    server.serve_forever()

except KeyboardInterrupt:
    print '^C received, shutting down the web server'
    server.socket.close()

websockserver.shutdown()

