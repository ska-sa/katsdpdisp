#!/usr/bin/python
import optparse
from multiprocessing import Process, Queue, Pipe, Manager, current_process
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
import mplh5canvas.simple_server as simple_server
from os import curdir, sep
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

#SERVE_PATH='/Users/mattieu/git/katsdpdisp/katsdpdisp/html'
SERVE_PATH='/home/mattieu/git/katsdpdisp/katsdpdisp/html'

#To run simulator: 
#first ./meertime_plot.py k7simulator 
#then run ./k7_simulator.py --test-addr :7149 --standalone
#
#if there is a crash that blocks port - use lsof (ls open files) to determine if there is a  process still running that should be killed
#
#####################################################################################
##Important before running this script:
##If running on a MAC and when streaming over the network (ie not read from local file,
## ie datafile='stream') then you may need to increase your buffer size using the command:
#
#sudo sysctl -w net.inet.udp.recvspace=6000000
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
#file will be in kat@kat-dc1:/var/kat/data/
#and synced to eg kat@kat-archive:/var/kat/archive/data/comm/2012/10
#note may need to reaugment file if sensor data missing:
#on kat-dc1.karoo execute ps aux | grep aug
#see something like /usr/bin/python /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -v -b -d /var/kat/data/staging --dbe=dbe7
#must then run /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -o -f filename.h5 to augment file in place
#####################################################################################
##to debug somewhere in code, run this command: from IPython.Shell import IPShellEmbed; IPShellEmbed()()
##or if crashed then just type debug
#####################################################################################


HOST_HTML="localhost"
HOST_WEBSOCKET='localhost'
HOST_WATERFALL="localhost"
HOST_TIMESERIES="localhost"
HOST_COLLECTOR="localhost"
PORT_HTML = 8080            #port on which html pages are served
PORT_WEBSOCKET = 8081       #port on which html pages are served
PORT_WATERFALL = 9000       #port on which waterfall data is served to data collector processes
PORT_TIMESERIES = 9001      #port on which timeseries data is served to data collector processes
PORTBASE_HTML2COLLECTOR=50000  #base port on which data is served to html clients from their respective data collector processes

#note timeseries ringbuffer should also store flaglist(as fn of channel) per time instant, or atleast whereever a change occurs

class RingBufferWaterfallHandler(SocketServer.BaseRequestHandler):
    """
    The RequestHandler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """
    def handle(self):
        #handles requests that reads from katsdpdisp object
        # self.request is the TCP socket connected to the client
        self.data = self.request.recv(1024).strip()
        print "{} wrote:".format(self.client_address[0])
        print self.data
        # just send back the same data, but upper-cased
        self.request.sendall(self.data.upper())

def StartRingBufferWaterfallServer(host, port, memusage, datafilename):
    dh=katsdpdisp.KATData()
    if (datafilename=='stream'):
        dh.start_spead_receiver(capacity=memusage/100.0,store2=True)
        datasd=dh.sd
    elif (datafilename=='k7simulator'):
        dh.start_direct_spead_receiver(capacity=memusage/100.0,store2=True)
        datasd=dh.sd
    else:
        try:
            dh.load_k7_data(datafilename,rows=rows,startrow=startrow)
        except Exception,e:
            print time.asctime()+" Failed to load file using k7 loader (%s)" % e
            dh.load_ff_data(datafilename)
        datasd=dh.sd_hist    
    
    try:
        #first construct katsdpdisp object
        server = SocketServer.TCPServer((host, port), RingBufferWaterfallHandler)
        print 'Started ring RingBufferWaterfallServer on port ' , port
        server.serve_forever()

    except KeyboardInterrupt:
        print '^C received, shutting down the web server'
        server.socket.close()
        
def report_compact_traceback(tb):
    """Produce a compact traceback report."""
    print '--------------------------------------------------------'
    print 'Session interrupted while doing (most recent call last):'
    print '--------------------------------------------------------'
    while tb:
        f = tb.tb_frame
        print '%s %s(), line %d' % (f.f_code.co_filename, f.f_code.co_name, f.f_lineno)
        tb = tb.tb_next
    print '--------------------------------------------------------'

#idea is to store the averaged time series profile in channel 0
def RingBufferProcess(memusage, datafilename, ringbufferrequestqueue, ringbufferresultqueue):
    typelookup={'arg':'phase','phase':'phase','pow':'mag','abs':'mag','mag':'mag'}
    fig={'title':['my figure title'],'xdata':np.arange(100),'ydata':[[np.random.randn(100),np.random.randn(100)]],'color':np.array([[0,255,0,0],[255,0,0,0]]),'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':['s'],'yunit':['dB'],'span':[],'spancolor':[]}
    dh=katsdpdisp.KATData()
    if (datafilename=='stream'):
        dh.start_spead_receiver(capacity=memusage/100.0,store2=True)
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
    try:
        while(True):
            if (datasd.storage.frame_count==0):
                time.sleep(1)
            else:
                #datasd.storage.set_mask('..170,220..')
                #ts = datasd.select_data(product=0, start_time=0, end_time=-1, start_channel=0, stop_channel=0, include_ts=True)[0]#gets last timestamp only
                #ts[0] contains times
                #antbase=np.unique([0 if len(c)!=5 else int(c[3:-1])-1 for c in datasd.cpref.inputs])
                #datasd.cpref.inputs=['ant1h','ant1v','ant2h','ant2v','ant3h','ant3v','ant4h','ant4v','ant5h','ant5v','ant6h','ant6v']
                #print antbase
                #ts[0] # [  1.37959922e+09   1.37959922e+09]
                [theviewsettings,thesignals,lastts,lastrecalc]=ringbufferrequestqueue.get()
                try:
                    if (theviewsettings=='setflags'):
                        datasd.storage.set_mask(str(','.join(thesignals)))
                        continue
                    thetype=typelookup[theviewsettings['type']]
                    #hfeeds=datasd.cpref.inputs
                    collectionsignals=thesignals[0]
                    customsignals=thesignals[1]
                    
                    ts = datasd.select_data(product=0, start_time=0, end_time=1e100, start_channel=0, stop_channel=0, include_ts=True)[0]#gets all timestamps only
                    if (len(ts)>1):
                        samplingtime=ts[-1]-ts[-2]
                    else:
                        samplingtime=np.nan
                    if (theviewsettings['figtype']=='timeseries'):
                        ydata=[]
                        color=[]
                        legend=[]
                        np.random.seed(0)
                        collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                        for colprod in collectionsignals:
                            if (colprod in collections):
                                icolprod=collections.index(colprod)
                                c=np.array(np.r_[np.random.random(3)*255,1],dtype='int')
                                for iprod in range(5):
                                    product=icolprod*5+iprod
                                    signal = datasd.select_data_collection(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod)
                                    if (iprod==4):
                                        c=np.array(np.r_[c[:-1],0],dtype='int')
                                    color.append(c)
                            
                        for product in customsignals:
                            signal = datasd.select_data(dtype=thetype, product=product, start_time=ts[0], end_time=ts[-1], include_ts=False, start_channel=0, stop_channel=1)
                            signal=np.array(signal).reshape(-1)
                            ydata.append(signal)#should check that correct corresponding values are returned
                            legend.append(product[0][3:]+product[1][3:])
                            color.append(np.r_[np.random.random(3)*255,0])
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
                        fig['title']='Timeseries'
                        fig['lastts']=ts[-1]
                        fig['lastdt']=samplingtime
                        fig['version']=theviewsettings['version']
                        fig['showtitle']=theviewsettings['showtitle']
                        fig['showlegend']=theviewsettings['showlegend']
                        fig['showxlabel']=theviewsettings['showxlabel']
                        fig['showylabel']=theviewsettings['showylabel']
                        fig['xlabel']='Time since '+time.asctime(time.localtime(ts[-1]))
                    elif (theviewsettings['figtype']=='spectrum'):
                        #nchannels=datasd.receiver.channels
                        ch=datasd.receiver.center_freqs_mhz[:]
                        ydata=[]
                        color=[]
                        legend=[]
                        np.random.seed(0)
                        collections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
                        for colprod in collectionsignals:
                            if (colprod in collections):
                                icolprod=collections.index(colprod)
                                c=np.array(np.r_[np.random.random(3)*255,1],dtype='int')
                                for iprod in range(5):
                                    product=icolprod*5+iprod
                                    signal = datasd.select_data_collection(dtype=thetype, product=product, end_time=-1, include_ts=False)
                                    ydata.append(signal.reshape(-1))
                                    legend.append(colprod)
                                    if (iprod==4):
                                        c=np.array(np.r_[c[:-1],0],dtype='int')
                                    color.append(c)

                        for product in customsignals:
                            signal = datasd.select_data(dtype=thetype, product=product, end_time=-1, include_ts=False)
                            signal=np.array(signal).reshape(-1)
                            ydata.append(signal)#should check that correct corresponding values are returned
                            legend.append(product[0][3:]+product[1][3:])
                            color.append(np.r_[np.random.random(3)*255,0])
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
                        fig['title']='Spectrum at '+time.asctime(time.localtime(ts[-1]))
                        fig['lastts']=ts[-1]
                        fig['lastdt']=samplingtime
                        fig['version']=theviewsettings['version']
                        fig['showtitle']=theviewsettings['showtitle']
                        fig['showlegend']=theviewsettings['showlegend']
                        fig['showxlabel']=theviewsettings['showxlabel']
                        fig['showylabel']=theviewsettings['showylabel']
                        spancolor=[]
                        span=[]
                        if (theviewsettings['xtype']=='mhz'):
                            fig['xdata']=ch
                            fig['xlabel']='Frequency'
                            fig['xunit']='MHz'
                            if (len(datasd.storage.spectrum_flag0)):
                                spancolor.append([255,0,0,128])
                                span.append([[ch[datasd.storage.spectrum_flag0[a]],ch[datasd.storage.spectrum_flag1[a]]] for a in range(len(datasd.storage.spectrum_flag0))])
                        elif (theviewsettings['xtype']=='ghz'):
                            fig['xdata']=np.array(ch)/1e3
                            fig['xlabel']='Frequency'
                            fig['xunit']='GHz'
                            if (len(datasd.storage.spectrum_flag0)):
                                spancolor.append([255,0,0,128])
                                span.append([[ch[datasd.storage.spectrum_flag0[a]]/1e3,ch[datasd.storage.spectrum_flag1[a]]/1e3] for a in range(len(datasd.storage.spectrum_flag0))])
                        else:
                            fig['xdata']=np.arange(len(ch))
                            fig['xlabel']='Channel number'
                            fig['xunit']=''
                            if (len(datasd.storage.spectrum_flag0)):
                                spancolor.append([255,0,0,128])
                                span.append([[datasd.storage.spectrum_flag0[a],datasd.storage.spectrum_flag1[a]] for a in range(len(datasd.storage.spectrum_flag0))])
                            
                        fig['spancolor']=np.array(spancolor)
                        fig['span']=span
                            
                    elif (theviewsettings['figtype'][:9]=='waterfall'):
                        collections=['auto0','auto100','auto25','auto75','auto50','autohh0','autohh100','autohh25','autohh75','autohh50','autovv0','autovv100','autovv25','autovv75','autovv50','autohv0','autohv100','autohv25','autohv75','autohv50','cross0','cross100','cross25','cross75','cross50','crosshh0','crosshh100','crosshh25','crosshh75','crosshh50','crossvv0','crossvv100','crossvv25','crossvv75','crossvv50','crosshv0','crosshv100','crosshv25','crosshv75','crosshv50']
                        collectionsalt=['automin','automax','auto25','auto75','auto','autohhmin','autohhmax','autohh25','autohh75','autohh','autovvmin','autovvmax','autovv25','autovv75','autovv','autohvmin','autohvmax','autohv25','autohv75','autohv','crossmin','crossmax','cross25','cross75','cross','crosshhmin','crosshhmax','crosshh25','crosshh75','crosshh','crossvvmin','crossvvmax','crossvv25','crossvv75','crossvv','crosshvmin','crosshvmax','crosshv25','crosshv75','crosshv']
                        productstr=theviewsettings['figtype'][9:]
                        if (productstr in collections):
                            product=collections.index(productstr)
                            productstr=collectionsalt[product]
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True)
                        elif (productstr in collectionsalt):
                            product=collectionsalt.index(productstr)
                            rvcdata = datasd.select_data_collection(dtype=thetype, product=product, end_time=-120, include_ts=True)
                        else:                        
                            product=decodecustomsignal(productstr)
                            rvcdata = datasd.select_data(dtype=thetype, product=product, end_time=-120, include_ts=True)
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
                        fig['color']=[]
                        fig['title']='Waterfall '+productstr
                        fig['lastts']=ts[-1]
                        fig['lastdt']=samplingtime
                        fig['version']=theviewsettings['version']
                        fig['showtitle']=theviewsettings['showtitle']
                        fig['showlegend']=theviewsettings['showlegend']
                        fig['showxlabel']=theviewsettings['showxlabel']
                        fig['showylabel']=theviewsettings['showylabel']
                        if (theviewsettings['xtype']=='mhz'):
                            fig['xdata']=ch
                            fig['xlabel']='Frequency'
                            fig['xunit']='MHz'
                        elif (theviewsettings['xtype']=='ghz'):
                            fig['xdata']=np.array(ch)/1e3
                            fig['xlabel']='Frequency'
                            fig['xunit']='GHz'
                        else:
                            fig['xdata']=np.arange(len(ch))
                            fig['xlabel']='Channel number'
                            fig['xunit']=''
                    else:                        
                        ts=np.arange(-99,1)
                        ydata=[]
                        color=[]
                        np.random.seed(time.time())
                        for product in theviewsignals:
                            ydata.append(np.random.randn(len(ts)))
                        np.random.seed(0)
                        for product in theviewsignals:
                            color.append(np.r_[np.random.random(3)*255,0])
                        fig['xdata']=ts
                        fig['ydata']=[ydata]
                        fig['color']=np.array(color)
                        fig['title']='Random'
                        fig['lastts']=ts[-1]
                        fig['lastdt']=samplingtime
                        fig['version']=0
                        fig['xlabel']='Time'
                        fig['ylabel']=['Power']
                        fig['xunit']=''
                        fig['yunit']=['']
                except Exception, e:
                    print 'Exception in RingBufferProcess:',str(e)
                    etype, evalue, etraceback=sys.exc_info()
                    report_compact_traceback(etraceback)
                    pass
                
                ringbufferresultqueue.put(fig)
            
    except KeyboardInterrupt:
        print '^C received, shutting down the ringbuffer process'
        

html_customsignals= {'default': [],
                     'all':     [],
                     'test':    [('ant1h','ant2h'),('ant1h','ant2v'),('ant1v','ant2v')]
                    }
html_collectionsignals= {'default': ['auto','cross'],
                         'all':     ['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv'],
                         'test':    ['auto','cross']
                        }
html_viewsettings={'default':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0}
                             ],
                   'all':[  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0}
                             ],
                    'test':  [  {'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'ghz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'pow','xtype':'ch' ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'mag','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'spectrum'  ,'type':'mag','xtype':'ch','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0},
                                {'figtype':'waterfall1h2h' ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0}
                             ]                            
                  }

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
            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[args[1]]))+')',handlerkey)
        elif (username not in html_viewsettings):
            print 'Warning: unrecognised username'            
        elif (args[0]=='sendfigure'):
            # print args
            lastts=np.round(float(args[1])*1000.0)/1000.0
            lastrecalc=float(args[2])
            ifigure=int(args[3])
            if (ifigure<0 or ifigure>=len(html_viewsettings[username])):
                print 'Warning: Update requested by %s for figure %d which does not exist'%(username,ifigure)
                return
            theviewsettings=html_viewsettings[username][ifigure]
            thesignals=(html_collectionsignals[username],html_customsignals[username])
            if (theviewsettings['figtype']=='timeseries'):
                send_timeseries(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure)
            elif (theviewsettings['figtype']=='spectrum'):
                send_spectrum(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure)
            elif (theviewsettings['figtype'][:9]=='waterfall'):
                send_waterfall(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure)
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
                    send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+')',thishandler)
        elif (args[0]=='setsignals'):
            print args
            #decodes signals of from 1h3h to ('ant1h','ant3h')
            html_customsignals[username]=[]
            standardcollections=['auto','autohh','autovv','autohv','cross','crosshh','crossvv','crosshv']
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
                    html_viewsettings[username].append({'figtype':'timeseries','type':'pow','xtype':'s'  ,'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+')',thishandler)
                elif (sig=='spectrum'):#creates new spectrum plot
                    html_viewsettings[username].append({'figtype':'spectrum'  ,'type':'pow','xtype':'ch','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+')',thishandler)
                elif (sig[:9]=='waterfall'):#creates new waterfall plot
                    html_viewsettings[username].append({'figtype':sig ,'type':'pow','xtype':'mhz','xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'showlegend':'on','showxlabel':'off','showylabel':'off','showtitle':'on','version':0})
                    for thishandler in websockrequest_username.keys():
                        if (websockrequest_username[thishandler]==username):
                            send_websock_cmd('ApplyViewLayout('+str(len(html_viewsettings[username]))+')',thishandler)
                    
        elif (args[0]=='setflags'):
            print args
            for theviewsettings in html_viewsettings[username]:
                if (theviewsettings['figtype']=='spectrum'):
                    theviewsettings['version']+=1
            ringbufferrequestqueue.put(['setflags',args[1:],0,0])

    except Exception, e:
        logger.warning("User event exception %s" % str(e))
        
#decodes signals of form 1h3h to ('ant1h','ant3h')
#returns () if invalid
def decodecustomsignal(signalstr):
    sreg=re.compile('[h|v|H|V]').split(signalstr)    
    if (len(sreg)!=3 or len(sreg[2])!=0 or (not sreg[0].isdigit()) or (not sreg[1].isdigit())):
        return ();
    return ('ant'+sreg[0]+signalstr[len(sreg[0])].lower(),'ant'+sreg[1]+signalstr[len(sreg[0])+1+len(sreg[1])].lower())
    
def send_timeseries(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure):
    try:
        ringbufferrequestqueue.put([theviewsettings,thesignals,lastts,lastrecalc])
        timeseries_fig=ringbufferresultqueue.get()

        if (lastrecalc<timeseries_fig['version']):
            send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_yseries=(timeseries_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].ydata.completed'%(ifigure),np.zeros(np.shape(local_yseries)[:2]),'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),timeseries_fig['version'],'i'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),timeseries_fig['lastts'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),timeseries_fig['lastdt'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),timeseries_fig['showtitle'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),timeseries_fig['showlegend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),timeseries_fig['showxlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),timeseries_fig['showylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),timeseries_fig['title'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),timeseries_fig['xlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),timeseries_fig['ylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),timeseries_fig['xunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),timeseries_fig['yunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),timeseries_fig['legend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),timeseries_fig['xdata'],'I'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),timeseries_fig['color'],'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
            for ispan,span in enumerate(timeseries_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(timeseries_fig['span'][ispan]),'H'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),timeseries_fig['spancolor'],'b'),handlerkey)
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):                    
                    send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(twinplotyseries)),handlerkey)
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey)
        else:#only send update
            where=np.where(timeseries_fig['xdata']>lastts+0.01)[0]#next time stamp index
            #print 'len(where)',len(where),'lastts',lastts,'new lastts',timeseries_fig['lastts']
            if (len(where)>0):
                its=np.min(where)
                send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
                #print 'len',len(timeseries_fig['ydata']),'shp',np.shape(timeseries_fig['ydata']),'its',its,'len(where)',len(where),'where',where
                local_yseries=np.array(timeseries_fig['ydata'])[:,:,its:]
                send_websock_data(pack_binarydata_msg('fig[%d].augmentlevel'%(ifigure),1,'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].augmenttargetlength'%(ifigure),len(timeseries_fig['xdata']),'h'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].augment.ydata.completed'%(ifigure),np.zeros(np.shape(local_yseries)[:2]),'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),timeseries_fig['lastts'],'d'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),timeseries_fig['lastdt'],'d'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),timeseries_fig['title'],'s'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),timeseries_fig['xlabel'],'s'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),timeseries_fig['xdata'],'I'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
                for itwin,twinplotyseries in enumerate(local_yseries):
                    for iline,linedata in enumerate(twinplotyseries):
                        send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(twinplotyseries)),handlerkey)
                        send_websock_data(pack_binarydata_msg('fig[%d].augment.ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey)
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].ignore.completed'%(ifigure),np.zeros([1]),'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ignore[0]'%(ifigure),np.zeros([1]),'b'),handlerkey)
                send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending nothing"',handlerkey)
    except Exception, e:
        logger.warning("User event exception %s" % str(e))

def send_spectrum(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure):
    try:
        ringbufferrequestqueue.put([theviewsettings,thesignals,lastts,lastrecalc])
        spectrum_fig=ringbufferresultqueue.get()
        if (lastrecalc<spectrum_fig['version'] or spectrum_fig['lastts']>lastts+0.01):
            send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_yseries=(spectrum_fig['ydata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].ydata.completed'%(ifigure),np.zeros(np.shape(local_yseries)[:2]),'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),spectrum_fig['version'],'i'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),spectrum_fig['lastts'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),spectrum_fig['lastdt'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),spectrum_fig['showtitle'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),spectrum_fig['showlegend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),spectrum_fig['showxlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),spectrum_fig['showylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),spectrum_fig['title'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),spectrum_fig['xlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),spectrum_fig['ylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),spectrum_fig['xunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),spectrum_fig['yunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),spectrum_fig['legend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),spectrum_fig['xdata'],'I'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),spectrum_fig['color'],'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
            for ispan,span in enumerate(spectrum_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(spectrum_fig['span'][ispan]),'H'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),spectrum_fig['spancolor'],'b'),handlerkey)
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(twinplotyseries)),handlerkey)
                    send_websock_data(pack_binarydata_msg('fig[%d].ydata[%d][%d]'%(ifigure,itwin,iline),linedata,'H'),handlerkey)
        else:#nothing new
            send_websock_data(pack_binarydata_msg('fig[%d].ignore.completed'%(ifigure),np.zeros([1]),'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ignore[0]'%(ifigure),np.zeros([1]),'b'),handlerkey)
            send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending nothing"',handlerkey)
    except Exception, e:
        logger.warning("User event exception %s" % str(e))


def send_waterfall(handlerkey,theviewsettings,thesignals,lastts,lastrecalc,ifigure):
    try:
        ringbufferrequestqueue.put([theviewsettings,thesignals,lastts,lastrecalc])
        waterfall_fig=ringbufferresultqueue.get()
        # print 'waterfall newlastts',waterfall_fig['lastts'],'lastts',lastts,'new version',waterfall_fig['version'],'lastversion',lastrecalc
        if (lastrecalc<waterfall_fig['version']):
            send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_cseries=(waterfall_fig['cdata'])[:]
            send_websock_data(pack_binarydata_msg('fig[%d].cdata.completed'%(ifigure),np.zeros(np.shape(local_cseries)[:1]),'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].version'%(ifigure),waterfall_fig['version'],'i'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showtitle'%(ifigure),waterfall_fig['showtitle'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showlegend'%(ifigure),waterfall_fig['showlegend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showxlabel'%(ifigure),waterfall_fig['showxlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].showylabel'%(ifigure),waterfall_fig['showylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xlabel'%(ifigure),waterfall_fig['xlabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].clabel'%(ifigure),waterfall_fig['clabel'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xunit'%(ifigure),waterfall_fig['xunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].yunit'%(ifigure),waterfall_fig['yunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].cunit'%(ifigure),waterfall_fig['cunit'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].legend'%(ifigure),waterfall_fig['legend'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xdata'%(ifigure),waterfall_fig['xdata'],'I'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].color'%(ifigure),waterfall_fig['color'],'b'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].figtype'%(ifigure),theviewsettings['figtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].type'%(ifigure),theviewsettings['type'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xtype'%(ifigure),theviewsettings['xtype'],'s'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey)
            for ispan,span in enumerate(waterfall_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_websock_data(pack_binarydata_msg('fig[%d].span[%d]'%(ifigure,ispan),np.array(waterfall_fig['span'][ispan]),'H'),handlerkey)
            send_websock_data(pack_binarydata_msg('fig[%d].spancolor'%(ifigure),waterfall_fig['spancolor'],'b'),handlerkey)
            for iline,linedata in enumerate(local_cseries):
                send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(local_cseries)),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey)
        else:#only send update
            where=np.where(waterfall_fig['ydata']>lastts+0.01)[0]#next time stamp index
            #print 'len(where)',len(where),'lastts',lastts,'new lastts',waterfall_fig['lastts']
            # print 'should send update, len(where)',len(where)
            if (len(where)>0):                
                its=np.min(where)
                send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
                # print 'len(waterfall_fig[cdata]))',len(waterfall_fig['cdata']),'shape',np.shape(waterfall_fig['cdata'])
                local_cseries=(waterfall_fig['cdata'])[its:]
                # print 'len(local_cseries)',len(local_cseries),'shape',np.shape(local_cseries)
                send_websock_data(pack_binarydata_msg('fig[%d].augmentlevel'%(ifigure),0,'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].augmenttargetlength'%(ifigure),len(waterfall_fig['ydata']),'h'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].augment.cdata.completed'%(ifigure),np.zeros(np.shape(local_cseries)[:1]),'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].lastts'%(ifigure),waterfall_fig['lastts'],'d'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].lastdt'%(ifigure),waterfall_fig['lastdt'],'d'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].title'%(ifigure),waterfall_fig['title'],'s'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ylabel'%(ifigure),waterfall_fig['ylabel'],'s'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ydata'%(ifigure),waterfall_fig['ydata'],'I'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey)
                for iline,linedata in enumerate(local_cseries):
                    send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(local_cseries)),handlerkey)
                    send_websock_data(pack_binarydata_msg('fig[%d].augment.cdata[%d]'%(ifigure,iline),linedata,'B'),handlerkey)
            else:#nothing new; note it is misleading, that min max sent here, because a change in min max will result in version increment; however note also that we want to minimize unnecessary redraws on html side
                send_websock_data(pack_binarydata_msg('fig[%d].ignore.completed'%(ifigure),np.zeros([1]),'b'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmin'%(ifigure),theviewsettings['xmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].xmax'%(ifigure),theviewsettings['xmax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymin'%(ifigure),theviewsettings['ymin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ymax'%(ifigure),theviewsettings['ymax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].cmin'%(ifigure),theviewsettings['cmin'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].cmax'%(ifigure),theviewsettings['cmax'],'f'),handlerkey)
                send_websock_data(pack_binarydata_msg('fig[%d].ignore[0]'%(ifigure),np.zeros([1]),'b'),handlerkey)
                send_websock_cmd('document.getElementById("timeclientusereventroundtrip").innerHTML="sending nothing"',handlerkey)
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
def pack_binarydata_msg(varname,val,dtype):
    bytesize  ={'s':1, 'f':4,   'd':8,   'b':1,   'h':2,   'i':4,   'B':1,   'H':2,   'I':4}
    structconv={'s':1, 'f':'f', 'd':'d', 'b':'B', 'h':'H', 'i':'I', 'B':'B', 'H':'H', 'I':'I'}
    npconv={'s':1, 'f':'float32', 'd':'float64', 'b':'uint8', 'h':'uint16', 'i':'uint32', 'B':'uint8', 'H':'uint16', 'I':'uint32'}
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
        val=np.array(val,dtype='float')
        wval=np.zeros(np.shape(val),dtype=npconv[dtype])
        finiteind=np.nonzero(np.isfinite(val)==True)[0]
        finitevals=val[finiteind]
        minval=np.min(finitevals)
        maxval=np.max(finitevals)
        if (maxval==minval):
            maxval=minval+1
        maxrange=2**(8*bytesize[dtype])-4;#also reserve -inf,inf,nan
    
        wval[finiteind]=np.array(((val[finiteind]-minval)/(maxval-minval)*(maxrange)),dtype=npconv[dtype])+3
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
        buff+=struct.pack('<%d'%(len(val))+structconv[dtype],*wval.tolist())
        
    return buff

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
            websockrequest_username[request]='no-name'
        websockrequest_time[request]=time.time()
        if (action=='data_user_event_timeseries'):
            handle_websock_event(request,*args)
        
    except AttributeError:
        logger.warning("Cannot find request method handle_%s" % action)

def send_websock_data(binarydata, handlerkey):
    try:
        handlerkey.ws_stream.send_message(binarydata,binary=True)
    except AttributeError:         # connection has gone
        print "Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0]
        deregister_websockrequest_handler(handlerkey)
    except Exception, e:
        print "Failed to send message (%s)" % str(e)

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

def register_websockrequest_handler(request):
    websockrequest_handlers[request] = request.connection.remote_addr[0]
    
def deregister_websockrequest_handler(request):
    del websockrequest_type[request]
    del websockrequest_time[request]
    del websockrequest_lasttime[request]
    del websockrequest_username[request]
    del websockrequest_handlers[request]

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
        
             
#This class will handle any incoming request from the browser 
def WebSocketProcess(requesthandler,webid,host,ringbufferwaterfallport):
    """Transfers data from ring buffer servers and client html pages, as needed. 
       Terminates if client connection closes or time out occurs"""
       
    
    # Create a socket (SOCK_STREAM means a TCP socket)
    for cnt in range(3):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((HOST_WATERFALL, ringbufferwaterfallport))
            sock.sendall("request to ringbuffer %d "%(cnt))
            received = sock.recv(1024)
            print 'Websocket process received from ringbuffer:',received
        finally:
            sock.close()
    
    #note requesthandler contains 
    # print 'requesthandler.request',requesthandler.request
    # print 'requesthandler.client_address',requesthandler.client_address
    # print 'requesthandler.server',requesthandler.server
    #time.sleep(10)
    #client_conn.send([requesthandler,'quit'])
    #print 'current_process',current_process()
    time.sleep(10)

    #informs html server that client is closed
    data = "/*cmd*/close websocket,"+str(webid)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST_HTML, PORT_HTML))
        sock.sendall(data + "\n")
        received = sock.recv(1024)
        print 'Collector process received:',received
    finally:
        sock.close()
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
                # f = open(curdir + sep + self.path) 
                f = open(SERVE_PATH + self.path)
                self.send_response(200)
                self.send_header('Content-type',mimetype)
                self.end_headers()
                filetext=f.read()
                if (self.path=="/index.html"):
                    #webid=register_htmlrequest_handler(self)
                    #parent_conn, child_conn = Pipe()
                    #p=Process(target=WebSocketProcess, args=(self,webid,HOST_WATERFALL,PORT_WATERFALL))
                    #p.start()
                    #print 'Current client processes',htmlrequest_handlers
                    filetext=filetext.replace('<!--data_port-->',str(PORT_WEBSOCKET))
                
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

#
# Parse command-line opts and arguments
parser = optparse.OptionParser(usage="%prog [opts] <file or 'stream' or 'k7simulator'>",
                               description="Launches the HTML5 signal displays front end server. "
                               "If no <file> is given then it defaults to 'stream'.")
parser.add_option("-d", "--debug", dest="debug", action="store_true",default=False,
                  help="Display debug messages.")
parser.add_option("-m", "--memusage", dest="memusage", default=10.0, type='float',
                  help="Percentage memory usage. Percentage of available memory to be allocated for buffer. (default=10)")

(opts, args) = parser.parse_args()

if (len(args)==0):
    args=['stream']
elif (args[0]=='file'):
    args=[SERVE_PATH+'/vira1822sep5_10.h5']

##Disable debug warning messages that clutters the terminal, especially when streaming
np.seterr(divide='ignore')
logging.basicConfig()
logger = logging.getLogger()
if (opts.debug):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.CRITICAL)
#    logger.setLevel(logging.WARNING)

ringbufferrequestqueue=Queue()
ringbufferresultqueue=Queue()
#Process(target=StartRingBufferWaterfallServer, args=(HOST_WATERFALL,PORT_WATERFALL,opts.memusage,args[0],ringbufferrequestqueue,ringbufferresultqueue)).start()
Process(target=RingBufferProcess,args=(opts.memusage, args[0], ringbufferrequestqueue, ringbufferresultqueue)).start()
htmlrequest_handlers={}

try:
    websockserver=simple_server.WebSocketServer(('', PORT_WEBSOCKET), websock_transfer_data, simple_server.WebSocketRequestHandler)
    print 'Started data websocket server on port ' , PORT_WEBSOCKET
    thread.start_new_thread(websockserver.serve_forever, ())
    
except Exception, e:
    print "Failed to create data websocket server. (%s)" % str(e)
    sys.exit(1)

try:
    server = HTTPServer(("", PORT_HTML), htmlHandler)
    print 'Started httpserver on port ' , PORT_HTML
    server.serve_forever()

except KeyboardInterrupt:
    print '^C received, shutting down the web server'
    server.socket.close()

websockserver.shutdown()

