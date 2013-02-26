#!/usr/bin/python
#####################################################################################
##Author: Mattieu de Villiers
##Email: mattieu@ska.ac.za
#####################################################################################
##Files:
## time_plot.py: This is the main file for running the html5 signal display front end
## time_plot.html: contains figure and interface elements for displaying time series
## spectrum_plot.html: contains figure and interface elements for displaying spectrum
## waterfall_plot.html: contains figure and interface elements for displaying waterfall
## matrix_plot.html: contains figure and interface elements for displaying baseline matrix
## help.html: contains interface help information
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
##Import libraries used
import matplotlib
import optparse
matplotlib.use('module://mplh5canvas.backend_h5canvas')
import katsdisp
import numpy as np
from pylab import *
import time
import logging
import sys
from pkg_resources import resource_filename
import signal
import mplh5canvas.simple_server as simple_server
import thread
import socket
import struct
import sys
import types
import string
import operator

try:
    import netifaces
except:
    netifaces = None


np.seterr(divide='ignore')

def signal_handler(signal, frame):
    stopdataservers()
    print 'You pressed Ctrl+C!'
    exit()

signal.signal(signal.SIGINT, signal_handler)

def get_refcounts():
    d = {}
    sys.modules
    for m in sys.modules.values():
        for sym in dir(m):
            o = getattr (m, sym)
            if type(o) is types.ClassType:
                d[o] = sys.getrefcount (o)
    pairs = map (lambda x: (x[1],x[0]), d.items())
    pairs.sort()
    pairs.reverse()
    return pairs

priors = {}
def print_top_100():
    print "Top 100 Changed Reference Counts"
    print "================================"
    for n, c in get_refcounts()[:100]:
        if priors.has_key(c):
            if priors[c] != n: print '%s\t%10d\t%10d' % (c.__name__,n,priors[c])
        else: print '%s\t%10d\tnew' % (c.__name__, n)
        priors[c] = n

# Parse command-line opts and arguments
parser = optparse.OptionParser(usage="%prog [opts] <file or 'stream' or 'k7simulator'>",
                               description="Launches the HTML5 signal displays front end server. "
                               "If no <file> is given then it defaults to 'stream'.")
parser.add_option("-o", "--open_browser",dest="open_plot",action="store_true", default=False,
                  help="Opens browser")
parser.add_option("-d", "--debug", dest="debug", action="store_true",default=False,
                  help="Display debug messages.")

(opts, args) = parser.parse_args()

html_directory=resource_filename("katsdisp","") + "/html/"
#html_directory=sys.path[0]+'/'
#html_directory = '/var/kat/static/'
#html_directory='/Users/mattieu/svnDS/katsdisp/katsdisp/html/'

##Disable debug warning messages that clutters the terminal, especially when streaming
logging.basicConfig()
logger = logging.getLogger()
if (opts.debug):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.CRITICAL)
#    logger.setLevel(logging.WARNING)

#datafile can be 'stream' or 'k7simulator' or a file like '1269960310.h5'
if (len(args)==0):
    datafile='stream'
    rows=None
elif (len(args)==1):
    datafile=args[0]
    rows=None
    startrow=None
elif (len(args)==2):
    datafile=args[0]
    rows=int(args[1])
    startrow=None
elif (len(args)==3):
    datafile=args[0]
    rows=int(args[1])
    startrow=int(args[2])

datasd=[]
antennamappingmode=1;#zero means dbe style correlator inputs; 1 means regular antenna layout style
antdisp=[]
"""Plot embedded in HTML wrapper with custom user events...
"""
if (antennamappingmode==0):
    number_of_antennas=8
    antposx=cos(np.linspace(-np.pi,np.pi,number_of_antennas,False))
    antposy=sin(np.linspace(-np.pi,np.pi,number_of_antennas,False))
    antdisp=[1 for x in range(number_of_antennas)]
else:
    antposx=[44.038593,119.731720,19.561749,-10.166619,-29.503662,-56.560379,-87.177673]
    antposy=[-18.156813,17.405912,17.866343,16.517134,-11.631535,-88.967461,66.925705]
    antennamapping={'ant1H':'1H','ant1V':'1V','ant2H':'2H','ant2V':'2V','ant3H':'3H','ant3V':'3V','ant4H':'4H','ant4V':'4V','ant5H':'5H','ant5V':'5V','ant6H':'6H','ant6V':'6V','ant7H':'7H','ant7V':'7V'}
#    antennamapping={'ant1H':'0H','ant1V':'0V','ant2H':'1H','ant2V':'1V','ant3H':'2H','ant3V':'2V','ant4H':'3H','ant4V':'3V','ant5H':'4H','ant5V':'4V','ant6H':'5H','ant6V':'5V','ant7H':'6H','ant7V':'6V'}
    antdisp=[]
    for k in range(len(antposx)):
        if (('ant'+str(k+antennamappingmode)+'H' or 'ant'+str(k+antennamappingmode)+'V') in antennamapping):
            antdisp.append(1)
        else:
            antdisp.append(0)

colourlist_R=[204,000,000,255,000,051,128]
colourlist_G=[000,102,000,000,255,051,064]
colourlist_B=[000,051,255,255,255,051,000]
colourlist_R_html='['+''.join(str(x)+',' for x in colourlist_R[:-1])+str(colourlist_R[-1])+']'
colourlist_G_html='['+''.join(str(x)+',' for x in colourlist_G[:-1])+str(colourlist_G[-1])+']'
colourlist_B_html='['+''.join(str(x)+',' for x in colourlist_B[:-1])+str(colourlist_B[-1])+']'

spectrum_width=None;#will be populated below by reading file or waiting for streamed data
spectrum_flagstr='';
spectrum_flag0=[]
spectrum_flag1=[]
spectrum_flagmask=[]
time_now=0
time_nownow=0
linestyledict={'HH':'-','VV':'-','HV':'--','VH':':','XX':'-','YY':'-','XY':'--','YX':':','xx':'-','yy':'-','xy':'--','yx':':'}
linewidthdict={'HH':2,'VV':1,'HV':1,'VH':1,'XX':2,'YY':1,'XY':1,'YX':1,'xx':2,'yy':1,'xy':1,'yx':1}
antposx_html='['+''.join(str(x)+',' for x in antposx[:-1])+str(antposx[-1])+']'
antposy_html='['+''.join(str(x)+',' for x in antposy[:-1])+str(antposy[-1])+']'
antdisp_html='['+''.join(str(x)+',' for x in antdisp[:-1])+str(antdisp[-1])+']'
time_corrHH='true'
time_corrVV='true'
time_corrHV='false'
time_corrVH='false'
time_antbase0=[]
time_antbase1=[]
time_legend='false'
time_seltypemenu='pow'
time_minF=''
time_maxF=''
time_minx=''
time_maxx=''
time_absminx=-1
time_absmaxx=-1
time_timeavg=''
time_channelphase=''
spectrum_corrHH='true'
spectrum_corrVV='true'
spectrum_corrHV='false'
spectrum_corrVH='false'
spectrum_antbase0=[]
spectrum_antbase1=[]
spectrum_legend='false'
spectrum_seltypemenu='pow'
spectrum_minF=''
spectrum_maxF=''
spectrum_seltypemenux='channel'
spectrum_minx=''
spectrum_maxx=''
spectrum_timeinst=''
spectrum_timeavg=''
spectrum_abstimeinst=-1;
waterfall_corrHH='true'
waterfall_corrVV='false'
waterfall_corrHV='false'
waterfall_corrVH='false'
waterfall_antbase0=[]
waterfall_antbase1=[]
waterfall_seltypemenu='phase'
waterfall_minF=''
waterfall_maxF=''
waterfall_seltypemenux='channel'
waterfall_minx=''
waterfall_maxx=''
waterfall_miny=''
waterfall_maxy=''

#input tuple (ant0,ant1,prod) eg (0,0,'HH')
#returns tuple (ant0,ant1,prod) eg (0,0,'HH')
def antennamap(antnumber0,antnumber1,prod):
    global antennamappingmode;
    if (antennamappingmode):
        ant0str=antennamapping['ant'+str(antnumber0+antennamappingmode)+prod[0]]
        ant1str=antennamapping['ant'+str(antnumber1+antennamappingmode)+prod[1]]
        return (int(ant0str[0:-1]),int(ant1str[0:-1]),ant0str[-1]+ant1str[-1])
    else:
        return (antnumber0,antnumber1,prod)

def user_cmd_ret(*args):
    """Handle any data returned from calls to canvas.send_cmd()"""
#    print "Got return from user event: %s" % str(args)#to debug
    logger.debug("Got return from user event: %s" % str(args))

def delayformatter(x,pos):
    global time_now,time_absminx,time_absmaxx
    'The two args are the value and tick position'
    if (time_absmaxx>=0):
        return time.ctime(x+time_now).split(' ')[-2]
    else:
        return str(x)+' \n'+time.ctime(x+time_now).split(' ')[-2]
    
time_serverselectdata=0
time_serverflaglogavg=0
spectrum_serverselectdata=0
spectrum_serverflaglogavg=0
waterfall_serverselectdata=0
waterfall_serverflaglogavg=0

lasttimeproducts=0
lasttimedtype=0
lastspectrum_flagmask=0
lasttime_timeavg=0

subsubdebugline='a'

def wrap_get_time_series(self, dtype='mag', product=None, timestamps=None, start_channel=0, stop_channel=spectrum_width):
    global timeseries_fig
    global lasttimeproducts
    global lasttimedtype
    global lastspectrum_flagmask
    global lasttime_timeavg
    global subsubdebugline
    subsubdebugline='a'
    if (lasttimedtype==dtype and np.array_equal(spectrum_flagmask,lastspectrum_flagmask) and time_timeavg==lasttime_timeavg and (product in lasttimeproducts)):
        subsubdebugline+='b'
        timestamp=timeseries_fig['timestamp']
        iprod=lasttimeproducts.index(product)
        
        subsubdebugline+='c'
        invalidts=(timestamp not in timestamps)
        if (invalidts or len(timeseries_fig['ydata'])<1 or len(timeseries_fig['ydata'][0])<=iprod or len(timeseries_fig['ydata'][0][iprod])<2):
            subsubdebugline+='d'
            if (invalidts):
                print 'timestamp ',timestamp, ' not in timestamps of length ',len(timestamps)
            return get_time_series(self, dtype=dtype, product=product, timestamps=timestamps, start_channel=start_channel, stop_channel=stop_channel)
        elif (timestamp<timestamps[-1]):
            subsubdebugline+='e'
            itimestamp=timestamps.index(timestamp)#this should always be in timestamp list
            [tp,prodstr]=get_time_series(self, dtype=dtype, product=product, timestamps=timestamps[itimestamp:], start_channel=start_channel, stop_channel=stop_channel)
            subsubdebugline+='f'
            startind=len(tp)+len((timeseries_fig['ydata'][0][iprod])[:-1])-len(timestamps);
            return [np.concatenate([(timeseries_fig['ydata'][0][iprod])[startind:-1],tp]),str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]
        else:
            subsubdebugline+='g'
            print 'returning same'
            return [timeseries_fig['ydata'][0][iprod],str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]
    else:
        subsubdebugline+='h'
        return get_time_series(self, dtype=dtype, product=product, timestamps=timestamps, start_channel=start_channel, stop_channel=stop_channel)
        

sub3debugline='a'
def get_time_series(self, dtype='mag', product=None, timestamps=None, start_channel=0, stop_channel=spectrum_width):
    global time_serverselectdata, time_serverflaglogavg
    global spectrum_flagmask,time_timeavg,spectrum_flagstr,spectrum_width
    global sub3debugline
    sub3debugline='a'
    t00=time.time()
    if product is None: product = self.default_product
    sub3debugline+='b'
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [nan*np.zeros(97,dtype='float32'),""]
    lentimestamps=len(timestamps)
    start_time=timestamps[0]
    end_time=timestamps[-1]
    sub3debugline+='c'
    if (dtype=='pow' or dtype=='mag'):
        t0=time.time()
        sub3debugline+='d'
        tp = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=False, start_channel=start_channel, stop_channel=stop_channel)
        sub3debugline+='e'
        t1=time.time()
        thetime_selectdatatime=t1-t0
        if (np.shape(tp)[0]!=lentimestamps):
            sub3debugline+='ee'
            print 'product contains %d less samples than expected... padding'%(lentimestamps-np.shape(tp)[0])
            ts = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=0, stop_channel=0)
            ts=ts[0].tolist()
            if (len(ts)!=np.shape(tp)[0]):
                print 'some seriously weird inconsistency, tp:',np.shape(tp),', ts: ',np.shape(ts),' timestamps',np.shape(timestamps)
            print 'timestamps[0] ',timestamps[0],' timestamps[-1] ',timestamps[-1]
            print 'ts[0] ',ts[0],' ts[-1] ',ts[-1]
                
            t1=time.time()
            thetime_selectdatatime=t1-t0
            ntp=np.zeros([lentimestamps,np.shape(tp)[1]])
            sub3debugline+='-ee-'
            for ti,tim in enumerate(timestamps):
                if (tim in ts):
                    tsi=ts.index(tim)
                    ntp[ti,:]=tp[tsi,:]
                elif (ti>0):
                    ntp[ti,:]=ntp[ti-1,:]
                elif (np.shape(tp)[0]):
                    ntp[ti,:]=tp[0,:]
                else:
                    ntp[ti,:]=np.zeros(spectrum_width)
            tp=ntp
        sub3debugline+='f'
        if (np.shape(tp)[1]!=spectrum_width):
            spectrum_width=np.shape(tp)[1]
            spectrum_flagmask=np.ones([spectrum_width])
            spectrum_flagstr=''
        sub3debugline+='g'
        tp=dot(tp,spectrum_flagmask)
    elif (dtype=='phase'):
        if (time_channelphase!=''):
            ch=int(time_channelphase);
            if (ch<0):
                ch=0
            elif (ch>=spectrum_width):
                ch=spectrum_width-1
            t0=time.time()
            tp = self.select_data(dtype=dtype, product=product, start_time=start_time, end_time=end_time, include_ts=False, start_channel=ch, stop_channel=ch+1)
            t1=time.time()
            thetime_selectdatatime=t1-t0
            if (np.shape(tp)[0]!=lentimestamps):
                print 'product contains %d less samples than expected... padding'%(lentimestamps-np.shape(tp)[0])
                ts = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=0, stop_channel=0)
                if (len(ts)!=np.shape(tp)[0]):
                    print 'some seriously weird inconsistency'
                t1=time.time()
                thetime_selectdatatime=t1-t0
                ntp=np.zeros([lentimestamps,1])
                for ti,tim in enumerate(timestamps):
                    if (tim in ts):
                        tsi=ts.index(tim)
                        ntp[ti,:]=tp[tsi,:]
                    elif (ti>0):
                        ntp[ti,:]=ntp[ti-1,:]
                    elif (tp.shape(tp)[0]):
                        ntp[ti,:]=tp[0,:]
                    else:
                        ntp[ti,:]=np.zeros(1)
                tp=ntp
        else:
            t0=time.time()
            tp = self.select_data(dtype='complex', product=product, start_time=start_time, end_time=end_time, include_ts=False, start_channel=start_channel, stop_channel=stop_channel)
            t1=time.time()
            thetime_selectdatatime=t1-t0
            if (np.shape(tp)[0]!=lentimestamps):
                print 'product contains %d less samples than expected... padding'%(lentimestamps-np.shape(tp)[0])
                ts = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=0, stop_channel=0)
                if (len(ts)!=np.shape(tp)[0]):
                    print 'some seriously weird inconsistency'
                t1=time.time()
                thetime_selectdatatime=t1-t0
                ntp=np.zeros([lentimestamps,np.shape(tp)[1]])
                for ti,tim in enumerate(timestamps):
                    if (tim in ts):
                        tsi=ts.index(tim)
                        ntp[ti,:]=tp[tsi,:]
                    elif (ti>0):
                        ntp[ti,:]=ntp[ti-1,:]
                    elif (tp.shape(tp)[0]):
                        ntp[ti,:]=tp[0,:]
                    else:
                        ntp[ti,:]=np.zeros(spectrum_width)
                tp=ntp;
            if (np.shape(tp)[1]!=spectrum_width):
                spectrum_width=np.shape(tp)[1]
                spectrum_flagmask=np.ones([spectrum_width])
                spectrum_flagstr=''
            tp=np.angle(dot(tp,spectrum_flagmask))

    sub3debugline+='h'
    if (dtype=='pow'):
        tp=10.0*log10(tp);
    sub3debugline+='i'
    if (time_timeavg!=''):
        reduction=int(time_timeavg);
#        reduction=int(double(time_timeavg)/(tp[0][1]-tp[0][0]));
        tp=np.diff(np.cumsum(tp)[0::reduction])/double(reduction);
    t11=time.time()
    sub3debugline+='j'
    time_serverselectdata+=thetime_selectdatatime
    time_serverflaglogavg+=t11-t00-(thetime_selectdatatime)
    return [tp,str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]#self.cpref.id_to_real_str(product, short=True)


subdebugline='a'

def plot_time_series(self, dtype='mag', products=None, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    global subdebugline
    global time_serverselectdata, time_serverflaglogavg
    global f1,f1a,f1b,spectrum_width,time_timeavg,time_now,time_nownow
    global time_absminx,time_absmaxx,time_minx,time_maxx
    plotyseries=[]
    plotyseries2=[]
    plotx=[]
    plotlegend=[]
    subdebugline='a'
    if products is None: products = self.default_products
    if (dtype=='phase' and time_channelphase!=''):
        title='Phase for channel '+time_channelphase
    else:
        if (dtype=='powphase' and time_channelphase!=''):
            title="Phase for channel "+time_channelphase+" and summed power for "+str(np.sum(spectrum_flagmask,dtype='int'))+" channels";
        else:
            title="Summed " + str(dtype) + " for "+str(np.sum(spectrum_flagmask,dtype='int'))+" channels";
        if (len(spectrum_flagstr)):
            if (len(spectrum_flagstr)>50):
                title+=", excluding ("+str(spectrum_flagstr[:50])+"...)";
            else:
                title+=", excluding ("+str(spectrum_flagstr)+")";
    subdebugline+='b'
    if (self.storage.frame_count==0):
        s=[[0]]
    else:
        t0=time.time()
        s = self.select_data(product=0, start_time=0, end_time=1e100, start_channel=0, stop_channel=0, include_ts=True)#gets all timestamps only
        t1=time.time()
        time_serverselectdata+=t1-t0
    subdebugline+='c'
    tslist=s[0].tolist()
    start_time=s[0][0]
    end_time=s[0][-1]
    minf1a=np.inf
    maxf1a=-np.inf
    if (time_absminx>0):
        start_time=time_absminx
    if (time_absmaxx>0):
        end_time=time_absmaxx
    subdebugline+='d'
    if (dtype=='powphase'):
        for i,product in enumerate(products):
            data = wrap_get_time_series(self,dtype='pow',product=product, timestamps=tslist, start_channel=start_channel, stop_channel=stop_channel)
            plotyseries.append(data[0])
            if (time_legend=='true'):
                plotlegend.append(data[1])
            data = get_time_series(self,dtype='phase',product=product, timestamps=tslist, start_channel=start_channel, stop_channel=stop_channel)
            plotyseries2.append(data[0])
    else:
        data_time = 0
        plot_time = 0
        for i,product in enumerate(products):
            data = wrap_get_time_series(self,dtype=dtype,product=product, timestamps=tslist, start_channel=start_channel, stop_channel=stop_channel)
            if data[0].shape == ():
                logger.warning("Insufficient data to plot time series")
                return
            plotyseries.append(data[0])
            if (time_legend=='true'):
                plotlegend.append(data[1])
    #
    subdebugline+='e'
    ts = s[0]    #time delay
    time_now=s[0][-1]
    time_nownow=s[0][-2]
    if (time_timeavg!=''):
        reduction=int(time_timeavg);
        ts=(ts[0::reduction])[0:len(plotyseries[0])];
    
    plotx=ts
    subdebugline+='f'
    plotxlabel="Time since " + time.ctime(s[0][-1])
    plottimestamp=s[0][-1]
    plotxunit='s'
    plotylabel2=""
    plotyunit2=""
    if dtype == 'phase':
        plotylabel="Phase"
        plotyunit="rad"
    elif (dtype=='pow'):
        plotylabel="Power"
        plotyunit="dB"
    elif (dtype=='powphase'):
        plotylabel="Power"
        plotyunit="dB"
        plotylabel2="Phase"
        plotyunit2="rad"
    else:
        plotylabel="Magitude"
        plotyunit="counts"
    if (dtype=='powphase'):
        plotyseries=[plotyseries,plotyseries2]
        plotylabel=[plotylabel,plotylabel2]
        plotyunit=[plotyunit,plotyunit2]
    else:
        plotyseries=[plotyseries]
        plotylabel=[plotylabel]
        plotyunit=[plotyunit]
        
    subdebugline+='g'
    global lasttimeproducts
    global lasttimedtype
    global lastspectrum_flagmask
    global lasttime_timeavg
    lasttimeproducts=products
    if (dtype=='powphase'):
        lasttimedtype='pow'
    else:
        lasttimedtype=dtype
    lastspectrum_flagmask=spectrum_flagmask
    lasttime_timeavg=time_timeavg
    subdebugline+='h'
    
    return plotx,plotyseries,title,plotxlabel,plotylabel,plotxunit,plotyunit,plotlegend,plottimestamp

def get_spectrum(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False):
    global spectrum_serverselectdata,spectrum_serverflaglogavg
    global spectrum_seltypemenux,spectrum_abstimeinst,spectrum_timeinst,spectrum_timeavg,spectrum_width
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [nan*np.zeros(97,dtype='float64'),nan*np.zeros(97,dtype='float32'),""],np.zeros(97,dtype='int')
    t00=time.time()
    if (dtype=='pow'):
        t0=time.time()
        s,flagarray = self.select_data(product=product, dtype="mag", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=reverse_order, avg_axis=avg_axis, sum_axis=sum_axis, include_ts=include_ts,include_flags=True)
        t1=time.time()
        thespectrum_selectdatatime=t1-t0
        s=10.0*log10(s);
    else:
        t0=time.time()
        s,flagarray = self.select_data(product=product, dtype=dtype, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=reverse_order, avg_axis=avg_axis, sum_axis=sum_axis, include_ts=include_ts,include_flags=True)
        t1=time.time()
        thespectrum_selectdatatime=t1-t0
            
    if (s.shape==()):
        sx=np.nan
    elif (spectrum_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
        sx=[f for f in range(0,s.shape[0])]
    elif (spectrum_seltypemenux=='mhz'):
        sx=[(self.receiver.center_freqs_mhz[start_channel+f]) for f in range(0,s.shape[0])]
    else:
        sx=[(self.receiver.center_freqs_mhz[start_channel+f]/1000.0) for f in range(0,s.shape[0])]
    t11=time.time()
    spectrum_serverselectdata+=thespectrum_selectdatatime
    spectrum_serverflaglogavg+=t11-t00-(thespectrum_selectdatatime)
    return [sx,s,str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])],flagarray

def plot_spectrum(self, dtype='mag', products=None, start_channel=0, stop_channel=spectrum_width):
    global spectrum_serverselectdata,spectrum_serverflaglogavg
    global f2,f2a,f2b,spectrum_width
    global spectrum_abstimeinst,spectrum_timeavg
    plotyseries=[]
    plotyseries2=[]
    plotx=[]
    plotlegend=[]

    if products is None: products = self.default_products
    if (spectrum_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
        plotxlabel="Channel Number"
        plotxunit=""
    elif (spectrum_seltypemenux=='mhz'):
        plotxlabel="Frequency"
        plotxunit="MHz"
    else:
        plotxlabel="Frequency"
        plotxunit="GHz"
    if (spectrum_abstimeinst>0):
        s=[[spectrum_abstimeinst]]
    elif (self.storage.frame_count==0):
        s=[[0]]
    else:
        t0=time.time()
        s = self.select_data(product=0, end_time=-2, start_channel=0, stop_channel=1, include_ts=True)
        t1=time.time()
        spectrum_serverselectdata+=t1-t0
    avg = ""
    average=1;
    if (spectrum_timeavg!=''):
        average=int(spectrum_timeavg);
    if average > 1: avg = " (" + str(average) + " dump average)"
    plotylabel2=""
    plotyunit2=""
    if dtype == 'phase':
        plotylabel="Phase"
        plotyunit="rad"
    elif (dtype=='pow'):
        plotylabel="Power"
        plotyunit="dB"
    elif (dtype=='powphase'):
        plotylabel="Power"
        plotyunit="dB"
        plotylabel2="Phase"
        plotyunit2="rad"
    else:
        plotylabel="Magitude"
        plotyunit="counts"
    if (spectrum_abstimeinst>0):
        start_time=spectrum_abstimeinst
        end_time=spectrum_abstimeinst+average
    else:
        start_time=0
        end_time=-average

    flagarray=np.zeros(stop_channel-start_channel,'bool')
    if (dtype=='powphase'):
        for i,product in enumerate(products):
            data,flagsa=get_spectrum(self,product=product, dtype='pow', start_channel=start_channel, stop_channel=stop_channel, start_time=start_time,end_time=end_time, avg_axis=0);
            plotyseries.append(data[1])
            if (spectrum_legend=='true'):
                plotlegend.append(data[2])
            if np.shape(flagsa)!=np.shape(flagarray):
                flagsa=flagsa.any(axis=0)
            flagarray|=np.array(flagsa,dtype='bool')
            # f2a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
            data,flagsa=get_spectrum(self,product=product, dtype='phase', start_channel=start_channel, stop_channel=stop_channel, start_time=start_time, end_time=end_time, avg_axis=0);
            plotyseries2.append(data[1])
            # f2b.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
    else:
        for i,product in enumerate(products):
            data,flagsa=get_spectrum(self,product=product, dtype=dtype, start_channel=start_channel, stop_channel=stop_channel, start_time=start_time,end_time=end_time, avg_axis=0);
            if np.shape(flagsa)!=np.shape(flagarray):
                flagsa=flagsa.any(axis=0)
            flagarray|=np.array(flagsa,dtype='bool')
            # f2a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
            plotyseries.append(data[1])
            if (spectrum_legend=='true'):
                plotlegend.append(data[2])

    plotx=data[0]
    flags=[]
    chanwidth=stop_channel-start_channel
    flagstart=0
    flagstop=0
    plottimestamp=s[0][-1]
    
    while (flagstop<chanwidth):
        flagstart=flagstop
        while (flagstart<chanwidth and flagarray[flagstart]==0):
            flagstart+=1
        flagstop=flagstart
        while (flagstop<chanwidth and flagarray[flagstop]!=0):
            flagstop+=1
        flags.append((flagstart,flagstop))
    
    if dtype == 'phase':
        title="Phase Spectrum at " + time.ctime(s[0][-1]) + avg
    elif (dtype=='powphase'):
        title="Power&Phase Spectrum at " + time.ctime(s[0][-1]) + avg
    else:
        title="Power Spectrum at " + time.ctime(s[0][-1]) + avg

    if (dtype=='powphase'):
        plotyseries=[plotyseries,plotyseries2]
        plotylabel=[plotylabel,plotylabel2]
        plotyunit=[plotyunit,plotyunit2]
    else:
        plotyseries=[plotyseries]
        plotylabel=[plotylabel]
        plotyunit=[plotyunit]
    
    return plotx,plotyseries,title,plotxlabel,plotylabel,plotxunit,plotyunit,plotlegend,plottimestamp,flags

def get_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    global waterfall_serverselectdata,waterfall_serverflaglogavg
    global time_now,time_nownow
    if product is None: product = self.default_product
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [[],[],""]
    if (dtype=="pow"):
        t0=time.time()
        tp0,tp1,flags = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel,reverse_order=False,include_flags=True)
        t1=time.time()
        tp1=10.0*log10(tp1);
        t2=time.time()
    else:
        t0=time.time()
        tp0,tp1,flags = self.select_data(dtype=dtype, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel,reverse_order=False,include_flags=True)
        t1=time.time()
        t2=t1
    ts = tp0
    time_now=tp0[-1]
    time_nownow=tp0[-2]
    tp1=np.array(tp1)
    waterfall_serverselectdata+=t1-t0
    waterfall_serverflaglogavg+=t2-t1
    
    if len(tp1.shape) == 1:
        logger.warning("Insufficient data to plot waterfall")
        return [[],[],""]
    return [ts,tp1,flags,str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]

def plot_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    tp = get_waterfall(self,dtype=dtype, product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
    if (tp[0]==[]):
        return [],[],[],'','','','','','','','',0
    if (dtype=='phase'):
        title="Spectrogram (Phase) for " + tp[3]
        plotclabel='Phase'
        plotcunit='rad'
    elif (dtype=='pow'):
        title="Spectrogram (Power) for " + tp[3]
        plotclabel='Power'
        plotcunit='dB'
    else:
        title="Spectrogram (Magnitude) for " + tp[3]
        plotclabel='Magnitude'
        plotcunit='counts'
    plotylabel="Time since "+time.ctime(tp[0][-1])
    plotyunit='s'
    
    plottimestamp=tp[0][-1]
    if (waterfall_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
        plotxlabel="Channel Number"
        plotxunit=""
        plotx=[start_channel,stop_channel]
    elif (waterfall_seltypemenux=='mhz'):
        plotxlabel="Frequency"
        plotxunit="MHz"
        plotx=[self.receiver.center_freqs_mhz[start_channel],self.receiver.center_freqs_mhz[stop_channel-1]]
    else:
        plotxlabel="Frequency"
        plotxunit="GHz"
        plotx=[self.receiver.center_freqs_mhz[start_channel]/1000.0,self.receiver.center_freqs_mhz[stop_channel-1]/1000.0]
    shp=np.shape(tp[1])
    tmp=tp[1].reshape(-1)
    tmp[np.nonzero(tp[2].reshape(-1))[0]]=np.nan;
    ploty=tp[0]
    plotyseries=tmp.reshape(shp)
    plotlegend=""
    return plotx,ploty,plotyseries,title,plotxlabel,plotylabel,plotclabel,plotxunit,plotyunit,plotcunit,plotlegend,plottimestamp

def get_baseline_matrix(self, start_channel=0, stop_channel=spectrum_width):
    global spectrum_abstimeinst,spectrum_timeavg,spectrum_flagstr,spectrum_width,spectrum_flagmask
    average=1;
    if (spectrum_timeavg!=''):
        average=int(spectrum_timeavg);
    if (spectrum_abstimeinst>0):
        start_time=spectrum_abstimeinst
        end_time=spectrum_abstimeinst+average
    else:
        start_time=0
        end_time=-average
    im = np.zeros((14,14),dtype=np.float32)
    keys=self.cpref.antennas.keys()
    if ('0' in keys):
        keys.remove('0')
    if ('ant8' in keys):
        keys.remove('ant8')
    antindices=np.sort([int(c[3])-1 for c in keys])
    pol=['H','V']
    for ip0 in range(2):
        for ip1 in range(2):
            for a0 in antindices:
                product=antennamap(a0,a0,pol[ip0]+pol[ip1])
                magdata=self.select_data(product=product, dtype="mag", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=False, avg_axis=0, sum_axis=None, include_ts=False,include_flags=False)
                if (np.shape(magdata)[0]!=spectrum_width):
                    spectrum_width=np.shape(magdata)[0]
                    spectrum_flagmask=np.ones([spectrum_width])
                    spectrum_flagstr=''
                im[a0*2+ip0][a0*2+ip1]=20.0*np.log10(dot(magdata,spectrum_flagmask))
                for a1 in range(a0+1,7):
                    if (a1 in antindices):
                        product=antennamap(a0,a1,pol[ip0]+pol[ip1])
                        magdata=self.select_data(product=product, dtype="mag", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=False, avg_axis=0, sum_axis=None, include_ts=False,include_flags=False)
                        phasedata=self.select_data(product=product, dtype="phase", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=False, avg_axis=0, sum_axis=None, include_ts=False,include_flags=False)
                        if (np.shape(magdata)[0]!=spectrum_width):
                            spectrum_width=np.shape(magdata)[0]
                            spectrum_flagmask=np.ones([spectrum_width])
                            spectrum_flagstr=''
                        im[a0*2+ip0][a1*2+ip1]=20.0*np.log10(dot(magdata,spectrum_flagmask))
                        if (np.shape(phasedata)[0]!=spectrum_width):
                            spectrum_width=np.shape(phasedata)[0]
                            spectrum_flagmask=np.ones([spectrum_width])
                            spectrum_flagstr=''
                        im[a1*2+ip0][a0*2+ip1]=dot(phasedata,spectrum_flagmask)
    return im

def plot_baseline_matrix(self, start_channel=0, stop_channel=spectrum_width):
    """Plot a matrix showing auto correlation power on the diagonal and cross correlation
    phase and power in the upper and lower segments."""
    global f4,f4a,spectrum_width,spectrum_flagmask
    if self.storage is not None:
        im = get_baseline_matrix(self,start_channel=0, stop_channel=spectrum_width)
        title="Baseline matrix, summed "+str(np.sum(spectrum_flagmask,dtype='int'))+" channels";
        f4a.set_title(title)
        if (len(spectrum_flagstr)):
            if (len(spectrum_flagstr)>50):
                f4a.set_xlabel("Excluding ("+spectrum_flagstr[:50]+"...)");
            else:
                f4a.set_xlabel("Excluding ("+spectrum_flagstr+")");
        cax = f4a.matshow(im, cmap=cm.spectral)
        cbar = f4.colorbar(cax)
        f4a.set_yticks(np.arange(14))
        f4a.set_yticklabels([str(int(x/2)+1) + (x % 2 == 0 and 'H' or 'V') for x in range(14)])
        f4a.set_xticks(np.arange(14))
        f4a.set_xticklabels([str(int(x/2)+1) + (x % 2 == 0 and 'H' or 'V') for x in range(14)])
        f4a.set_ylim((13.5,-0.5))
    else:
        print time.asctime()+" No stored data available..."

def makenewcontent(_flagstr,_antennamappingmode,_antbase0,_antbase1,_corrHH,_corrVV,_corrHV,_corrVH,_legend,_seltypemenu,_minF,_maxF,_seltypemenux,_minx,_maxx,_seltypemenuy,_miny,_maxy,_timeinst,_timeavg,_channelphase,_healthtext):
    if (len(_antbase0)):
        newcontent='\n'+'antbase0=['+''.join(str(x)+',' for x in _antbase0[:-1])+str(_antbase0[-1])+'];\n'
        newcontent+='antbase1=['+''.join(str(x)+',' for x in _antbase1[:-1])+str(_antbase1[-1])+'];\n'
    else:
        newcontent='\n'+'antbase0=[];\n'
        newcontent+='antbase1=[];\n'
    newcontent+='antennamappingmode='+str(_antennamappingmode)+';\n'
    newcontent+='var seltypemenu = document.getElementById("typemenu");\n'
    if (_seltypemenu=='pow'):
        newcontent+='seltypemenu.selectedIndex=0;\n';
    elif (_seltypemenu=='mag'):
        newcontent+='seltypemenu.selectedIndex=1;\n';
    elif (_seltypemenu=='phase'):
        newcontent+='seltypemenu.selectedIndex=2;\n';
    else:
        newcontent+='seltypemenu.selectedIndex=3;\n';
    if (_seltypemenux!=''):
        newcontent+='var seltypemenux = document.getElementById("typemenux");\n'
        if (_seltypemenux=='channel'):
            newcontent+='seltypemenux.selectedIndex=0;\n';
        elif (_seltypemenux=='mhz'):
            newcontent+='seltypemenux.selectedIndex=1;\n';
        else:
            newcontent+='seltypemenux.selectedIndex=2;\n';
    newcontent+='var tmp;'
    newcontent+='tmp=document.getElementById("textminF");\nif(tmp)tmp.value="'+_minF+'";\n';
    newcontent+='tmp=document.getElementById("textmaxF");\nif(tmp)tmp.value="'+_maxF+'";\n';
    newcontent+='tmp=document.getElementById("textminx");\nif(tmp)tmp.value="'+_minx+'";\n';
    newcontent+='tmp=document.getElementById("textmaxx");\nif(tmp)tmp.value="'+_maxx+'";\n';
    newcontent+='tmp=document.getElementById("textminy");\nif(tmp)tmp.value="'+_miny+'";\n';
    newcontent+='tmp=document.getElementById("textmaxy");\nif(tmp)tmp.value="'+_maxy+'";\n';
    newcontent+='tmp=document.getElementById("texttimeinst");\nif(tmp)tmp.value="'+_timeinst+'";\n';
    newcontent+='tmp=document.getElementById("texttimeavg");\nif(tmp)tmp.value="'+_timeavg+'";\n';
    newcontent+='tmp=document.getElementById("textchannelphase");\nif(tmp)tmp.value="'+_channelphase+'";\n';
    newcontent+='document.getElementById("optionHH").checked='+_corrHH+';\n';
    newcontent+='document.getElementById("optionVV").checked='+_corrVV+';\n';
    newcontent+='document.getElementById("optionHV").checked='+_corrHV+';\n';
    newcontent+='document.getElementById("optionVH").checked='+_corrVH+';\n';
    newcontent+='document.getElementById("healthtext").innerHTML='+_healthtext+';\n';
    if (_legend!=''):
        newcontent+='document.getElementById("optionlegend").checked='+_legend+';\n';
    if (_flagstr!='none'):
        newcontent+='document.getElementById("textflag").value="'+_flagstr+'";\n';
    newcontent+='redrawCanvas();'
    return newcontent
    
def setloadpage(cc,newcontent):
    if (cc==None):
        return cc;
    i0=cc.find('//beginloadpage')+len('//beginloadpage');
    i1=cc.find('//endloadpage');
    cc=cc[:i0]+str(newcontent)+cc[i1:]
    return cc;

timeseries_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[],'timestamp':[]}

def timeseries_draw():
    global subdebugline
    global subsubdebugline
    global sub3debugline
    
    subdebugline='a'
    debugline='a'
    try:
        global time_serverselectdata, time_serverflaglogavg
        global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx
        global f1,f1a,f1b,spectrum_width
        ts_start = time.time()
        
        new_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[],'timestamp':[]}
        time_serverselectdata=0
        time_serverflaglogavg=0
        products=[]
        styles=[]

        efftime_antbase0=[]
        efftime_antbase1=[]
        antbase=np.unique(([int(c[3:-1])-1 for c in datasd.cpref.inputs]))#unique antenna zero based indices
        for c in range(len(time_antbase0)):
            if (time_antbase0[c] in antbase and time_antbase1[c] in antbase):
                efftime_antbase0.append(time_antbase0[c])
                efftime_antbase1.append(time_antbase1[c])

        debugline+='b'
        for c in range(len(time_antbase0)):
            _rgb=[(colourlist_R[efftime_antbase0[c]]+colourlist_R[efftime_antbase1[c]])/2,(colourlist_G[efftime_antbase0[c]]+colourlist_G[efftime_antbase1[c]])/2,(colourlist_B[efftime_antbase0[c]]+colourlist_B[efftime_antbase1[c]])/2 ]
            crossstyle = 0 if (efftime_antbase0[c]==efftime_antbase1[c]) else 4
            if (time_corrHH=='true'):
                products.append(antennamap(efftime_antbase0[c],efftime_antbase1[c],'HH'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],0+crossstyle])
            if (time_corrVV=='true'):
                products.append(antennamap(efftime_antbase0[c],efftime_antbase1[c],'VV'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],1+crossstyle])
            if (time_corrHV=='true'):
                products.append(antennamap(efftime_antbase0[c],efftime_antbase1[c],'HV'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],2+crossstyle])
            if (time_corrVH=='true'):
                products.append(antennamap(efftime_antbase0[c],efftime_antbase1[c],'VH'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],3+crossstyle])
        debugline+='c'
        if (len(products)):
            new_fig['xdata'],new_fig['ydata'],new_fig['title'],new_fig['xlabel'],new_fig['ylabel'],new_fig['xunit'],new_fig['yunit'],new_fig['legend'],new_fig['timestamp']=plot_time_series(self=datasd,dtype=time_seltypemenu, products=products, end_time=-3600)
        debugline+='d'
        if (time_absminx<=0 and time_minx!=''):
            new_fig['xmin']=double(time_minx)
        elif (time_absminx>0):
            new_fig['xmin']=double(time_absminx-time_now)
        else:
            new_fig['xmin']=np.nan
        if (time_absmaxx<=0 and time_maxx!=''):
            new_fig['xmax']=double(time_maxx)
        elif (time_absmaxx>0):
            new_fig['xmax']=double(time_absmaxx-time_now)
        else:
            new_fig['xmax']=np.nan
        if (time_minF!=''):
            new_fig['ymin']=double(time_minF)
        else:
            new_fig['ymin']=np.nan
        if (time_maxF!=''):
            new_fig['ymax']=double(time_maxF)
        else:
            new_fig['ymax']=np.nan
        debugline+='e'
        ts_draw = time.time()
        new_fig['ydata']=np.array(new_fig['ydata'])
        new_fig['span']=[]#this doesnt evaluate to a numpy array generally...
        new_fig['spancolor']=[]
        new_fig['color']=np.array(styles)

        debugline+='f'
        ts_end = time.time()
            
        global timeseries_fig
        timeseries_fig=new_fig

        ts_finalend = time.time()

        time_servertotal=ts_end-ts_start
        time_serverprepmsg=ts_end-ts_draw
        time_serverinit=time_servertotal-(time_serverselectdata+time_serverflaglogavg+time_serverprepmsg)
        time_serversend=ts_finalend-ts_end;

        debugline+='g'
        f1.canvas.send_cmd("serverperf("+str(np.round(time_servertotal*1000.0))+','+str(np.round(time_serverinit*1000.0))+','+str(np.round(time_serverselectdata*1000.0))+','+str(np.round(time_serverflaglogavg*1000.0))+','+str(np.round(time_serverprepmsg*1000.0))+','+str(np.round(time_serversend*1000.0))+" );")

        strng='last server data requests (interval): '
        sortedbytime = sorted(_request_lasttime.iteritems(), key=operator.itemgetter(1), reverse=True)
        for key,lastreqtime in sortedbytime:
            if (_request_type[key]=='data_user_event_timeseries'):
                strng+=str(int(np.round(ts_finalend-_request_time[key])))+'s ('+str(int(np.round((_request_time[key]-lastreqtime)*1000.0)))+')   '

        debugline+='h'
        f1.canvas.send_cmd('document.getElementById("timeserverreqinterval").innerHTML="'+strng+'";')
        
    except Exception,e:
        print time.asctime()+' Exception in timeseries_draw (%s) debugline '%e,debugline,' subdebugline ',subdebugline, ' subsub ',subsubdebugline, ' sub3 ',sub3debugline


spectrum_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[],'timestamp':[]}

def spectrum_draw():
    try:
        global spectrum_serverselectdata,spectrum_serverflaglogavg
        global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend, spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx
        global f2,f2a,f2b,spectrum_width
        ts_start = time.time()
        
        new_fig={'title':[],'xdata':[],'ydata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'xlabel':[],'ylabel':[],'xunit':[],'yunit':[],'span':[],'spancolor':[],'timestamp':[]}
        spectrum_serverselectdata=0
        spectrum_serverflaglogavg=0
        products=[]
        styles=[]

        minx=0
        maxx=spectrum_width-1
        
        effspectrum_antbase0=[]
        effspectrum_antbase1=[]
        antbase=np.unique(([int(c[3:-1])-1 for c in datasd.cpref.inputs]))#unique antenna zero based indices
        for c in range(len(spectrum_antbase0)):
            if (spectrum_antbase0[c] in antbase and spectrum_antbase1[c] in antbase):
                effspectrum_antbase0.append(spectrum_antbase0[c])
                effspectrum_antbase1.append(spectrum_antbase1[c])
        
        for c in range(len(effspectrum_antbase0)):
            _rgb=[(colourlist_R[effspectrum_antbase0[c]]+colourlist_R[effspectrum_antbase1[c]])/2,(colourlist_G[effspectrum_antbase0[c]]+colourlist_G[effspectrum_antbase1[c]])/2,(colourlist_B[effspectrum_antbase0[c]]+colourlist_B[effspectrum_antbase1[c]])/2 ]
            crossstyle = 0 if (effspectrum_antbase0[c]==effspectrum_antbase1[c]) else 4
            if (spectrum_corrHH=='true'):
                products.append(antennamap(effspectrum_antbase0[c],effspectrum_antbase1[c],'HH'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],0+crossstyle])
            if (spectrum_corrVV=='true'):
                products.append(antennamap(effspectrum_antbase0[c],effspectrum_antbase1[c],'VV'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],1+crossstyle])
            if (spectrum_corrHV=='true'):
                products.append(antennamap(effspectrum_antbase0[c],effspectrum_antbase1[c],'HV'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],2+crossstyle])
            if (spectrum_corrVH=='true'):
                products.append(antennamap(effspectrum_antbase0[c],effspectrum_antbase1[c],'VH'))
                styles.append([_rgb[0],_rgb[1],_rgb[2],3+crossstyle])
        if (len(products)):
            new_fig['xdata'],new_fig['ydata'],new_fig['title'],new_fig['xlabel'],new_fig['ylabel'],new_fig['xunit'],new_fig['yunit'],new_fig['legend'],new_fig['timestamp'],onlineflags=plot_spectrum(self=datasd,dtype=spectrum_seltypemenu, products=products, start_channel=1,stop_channel=spectrum_width)
        else:
            onlineflags=[]

        plottimechannelphase=None
        plotflagspan0=[]
        plotflagspan1=[]
        plotonlineflagspan0=[]
        plotonlineflagspan1=[]
        if (spectrum_seltypemenux=='channel' or datasd.receiver.center_freqs_mhz==[]):
            if (time_channelphase!=''):
                plottimechannelphase=(np.floor(time_channelphase)-0.5)
            for c in range(len(spectrum_flag0)):
                plotflagspan0.append((spectrum_flag0[c]-0.5))
                plotflagspan1.append((spectrum_flag1[c]-0.5))
            for pair in onlineflags:
                plotonlineflagspan0.append((pair[0]-0.5))
                plotonlineflagspan1.append((pair[1]-0.5))
        elif (spectrum_seltypemenux=='mhz'):
            halfchanwidth=abs(datasd.receiver.center_freqs_mhz[0]-datasd.receiver.center_freqs_mhz[1])/2.0
            minx=datasd.receiver.center_freqs_mhz[spectrum_width-1]
            maxx=datasd.receiver.center_freqs_mhz[0]
            if (time_channelphase!=''):
                plottimechannelphase=(datasd.receiver.center_freqs_mhz[int(time_channelphase)]-halfchanwidth)
            for c in range(len(spectrum_flag0)):
                plotflagspan0.append((datasd.receiver.center_freqs_mhz[spectrum_flag0[c]]-halfchanwidth))
                plotflagspan1.append((datasd.receiver.center_freqs_mhz[spectrum_flag1[c]]-halfchanwidth))
            for pair in onlineflags:
                plotonlineflagspan0.append((datasd.receiver.center_freqs_mhz[pair[0]]-halfchanwidth))
                plotonlineflagspan1.append((datasd.receiver.center_freqs_mhz[pair[1]]-halfchanwidth))
        else:
            halfchanwidth=abs(datasd.receiver.center_freqs_mhz[0]-datasd.receiver.center_freqs_mhz[1])/1000.0/2.0
            minx=datasd.receiver.center_freqs_mhz[spectrum_width-1]/1000.0
            maxx=datasd.receiver.center_freqs_mhz[0]/1000.0
            if (time_channelphase!=''):
                plottimechannelphase=(datasd.receiver.center_freqs_mhz[int(time_channelphase)]/1000.0-halfchanwidth)
            for c in range(len(spectrum_flag0)):
                plotflagspan0.append((datasd.receiver.center_freqs_mhz[spectrum_flag0[c]]/1000.0-halfchanwidth))
                plotflagspan1.append((datasd.receiver.center_freqs_mhz[spectrum_flag1[c]]/1000.0-halfchanwidth))
            for pair in onlineflags:
                plotonlineflagspan0.append((datasd.receiver.center_freqs_mhz[pair[0]]/1000.0-halfchanwidth))
                plotonlineflagspan1.append((datasd.receiver.center_freqs_mhz[pair[1]]/1000.0-halfchanwidth))

        #gdb python; set args ./time_plot.py; run; bt;
    #    matplotlib.pylab.plot(np.array(range(10)),sin(np.array(range(10)))+2)
    #    matplotlib.pylab.axvline(10,0,1,color='b',alpha=0.5)

        if (spectrum_minx!=''):
            new_fig['xmin']=double(spectrum_minx)
        else:
            new_fig['xmin']=np.nan
        if (spectrum_maxx!=''):
            new_fig['xmax']=double(spectrum_maxx)
        else:
            new_fig['xmax']=np.nan
        if (spectrum_minF!=''):
            new_fig['ymin']=double(spectrum_minF)
        else:
            new_fig['ymin']=np.nan
        if (spectrum_maxF!=''):
            new_fig['ymax']=double(spectrum_maxF)
        else:
            new_fig['ymax']=np.nan
        ts_draw=time.time()

        spancolor=[]
        span=[]
        if (plottimechannelphase!=None):
            spancolor.append([0,200,0,128])
            span.append([[plottimechannelphase,plottimechannelphase]])#note it has 0.5 channel positions typically
        if (len(plotflagspan0)):
            spancolor.append([255,0,0,128])
            span.append([[plotflagspan0[a],plotflagspan1[a]] for a in range(len(plotflagspan0))])
        if (len(plotonlineflagspan0)):
            spancolor.append([200,200,0,128])
            span.append([[plotonlineflagspan0[a],plotonlineflagspan1[a]] for a in range(len(plotonlineflagspan0))])

        if (len(new_fig['xdata'])):
            new_fig['xdata']=[new_fig['xdata'][0],new_fig['xdata'][-1]]
        new_fig['ydata']=np.array(new_fig['ydata'])
        new_fig['span']=span#this doesnt evaluate to a numpy array generally...
        new_fig['spancolor']=np.array(spancolor)
        new_fig['color']=np.array(styles)
        ts_end = time.time()

        global spectrum_fig
        spectrum_fig=new_fig
            
        ts_finalend = time.time()
        spectrum_servertotal=ts_finalend-ts_start
        spectrum_serverprepmsg=ts_end-ts_draw
        spectrum_serverinit=(ts_draw-ts_start)-(spectrum_serverselectdata+spectrum_serverflaglogavg)
        spectrum_serversend=ts_finalend-ts_end;

        f2.canvas.send_cmd("serverperf("+str(np.round(spectrum_servertotal*1000.0))+','+str(np.round(spectrum_serverinit*1000.0))+','+str(np.round(spectrum_serverselectdata*1000.0))+','+str(np.round(spectrum_serverflaglogavg*1000.0))+','+str(np.round(spectrum_serverprepmsg*1000.0))+','+str(np.round(spectrum_serversend*1000.0))+" );")

        strng='last server data requests (interval): '
        sortedbytime = sorted(_request_lasttime.iteritems(), key=operator.itemgetter(1), reverse=True)
        for key,lastreqtime in sortedbytime:
            if (_request_type[key]=='data_user_event_spectrum'):
                strng+=str(int(np.round(ts_finalend-_request_time[key])))+'s ('+str(int(np.round((_request_time[key]-lastreqtime)*1000.0)))+')   '

        f2.canvas.send_cmd('document.getElementById("timeserverreqinterval").innerHTML="'+strng+'";')
        
    except Exception,e:
        print time.asctime()+' Exception in spectrum_draw (%s)'%e


waterfall_fig={'title':[],'xdata':[],'ydata':[],'cdata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'xlabel':[],'ylabel':[],'clabel':[],'xunit':[],'yunit':[],'cunit':[],'span':[],'spancolor':[],'timestamp':[]}

def waterfall_draw():
    try:
        global waterfall_serverselectdata,waterfall_serverflaglogavg
        global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
        global f3,f3a,spectrum_width
        ts_start = time.time()

        new_fig={'title':[],'xdata':[],'ydata':[],'cdata':[],'color':[],'legend':[],'xmin':[],'xmax':[],'ymin':[],'ymax':[],'cmin':[],'cmax':[],'xlabel':[],'ylabel':[],'clabel':[],'xunit':[],'yunit':[],'cunit':[],'span':[],'spancolor':[],'timestamp':[]}
        waterfall_serverselectdata=0
        waterfall_serverflaglogavg=0

        products=[]
        for c in range(len(waterfall_antbase0)):
            if (waterfall_corrHH=='true'):
                products.append(antennamap(waterfall_antbase0[c],waterfall_antbase1[c],'HH'))
            if (waterfall_corrVV=='true'):
                products.append(antennamap(waterfall_antbase0[c],waterfall_antbase1[c],'VV'))
            if (waterfall_corrHV=='true'):
                products.append(antennamap(waterfall_antbase0[c],waterfall_antbase1[c],'HV'))
            if (waterfall_corrVH=='true'):
                products.append(antennamap(waterfall_antbase0[c],waterfall_antbase1[c],'VH'))
        if (len(products)):
            new_fig['xdata'],new_fig['ydata'],new_fig['cdata'],new_fig['title'],new_fig['xlabel'],new_fig['ylabel'],new_fig['clabel'],new_fig['xunit'],new_fig['yunit'],new_fig['cunit'],new_fig['legend'],new_fig['timestamp']=plot_waterfall(self=datasd,dtype=waterfall_seltypemenu,product=products[0],start_channel=1,stop_channel=spectrum_width)

        if (waterfall_minF!=''):
            new_fig['cmin']=double(waterfall_minF);
        else:
            new_fig['cmin']=np.nan
        if (waterfall_maxF!=''):
            new_fig['cmax']=double(waterfall_maxF);
        else:
            new_fig['cmax']=np.nan
        if (waterfall_minx!=''):
            new_fig['xmin']=double(waterfall_minx)
        else:
            new_fig['xmin']=np.nan
        if (waterfall_maxx!=''):
            new_fig['xmax']=double(waterfall_maxx)
        else:
            new_fig['xmax']=np.nan
        if (waterfall_miny!=''):
            new_fig['ymin']=double(waterfall_miny)
        else:
            new_fig['ymin']=np.nan
        if (waterfall_maxy!=''):
            new_fig['ymax']=double(waterfall_maxy)
        else:
            new_fig['ymax']=np.nan

        ts_draw=time.time()
        ts_end = time.time()
        global waterfall_fig
        waterfall_fig=new_fig
        ts_finalend = time.time()
        
        waterfall_servertotal=ts_finalend-ts_start
        waterfall_serverprepmsg=ts_end-ts_draw
        waterfall_serverinit=(ts_draw-ts_start)-(waterfall_serverselectdata+waterfall_serverflaglogavg)
        waterfall_serversend=ts_finalend-ts_end;

        f3.canvas.send_cmd("serverperf("+str(np.round(waterfall_servertotal*1000.0))+','+str(np.round(waterfall_serverinit*1000.0))+','+str(np.round(waterfall_serverselectdata*1000.0))+','+str(np.round(waterfall_serverflaglogavg*1000.0))+','+str(np.round(waterfall_serverprepmsg*1000.0))+','+str(np.round(waterfall_serversend*1000.0))+" );")

        strng='last server data requests (interval): '
        sortedbytime = sorted(_request_lasttime.iteritems(), key=operator.itemgetter(1), reverse=True)
        for key,lastreqtime in sortedbytime:
            if (_request_type[key]=='data_user_event_spectrum'):
                strng+=str(int(np.round(ts_finalend-_request_time[key])))+'s ('+str(int(np.round((_request_time[key]-lastreqtime)*1000.0)))+')   '

        f3.canvas.send_cmd('document.getElementById("timeserverreqinterval").innerHTML="'+strng+'";')
        

    except Exception,e:
        print time.asctime()+' Exception in waterfall_draw (%s)'%e

def matrix_draw():
    try:
        global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
        global f4,f4a,spectrum_width
        f4.clf()
        ts_init = time.time()
        f4a=f4.add_subplot(111)
        ts_start = time.time()
        plot_baseline_matrix(self=datasd, start_channel=1, stop_channel=spectrum_width)
        ts_plot = time.time()
        f4.canvas.draw()
        ts_end = time.time()
    #    print "Matrix timing| Init: %.3fs, Plot: %.3fs, Draw: %.3fs\n" % (ts_start - ts_init, ts_plot - ts_start, ts_end - ts_plot)
    except Exception,e:
        print time.asctime()+' Exception in matrix_draw (%s)'%e
    
def timeseries_event(figno,*args):
    global forcerecalc
    global dh,datasd,rows,startrow,spectrum_width
    global time_absminx,time_absmaxx,time_now,time_channelphase,antennamappingmode
    global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx, time_timeavg
    global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend, spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx, spectrum_timeinst, spectrum_timeavg
    global spectrum_flagstr,spectrum_flag0,spectrum_flag1,spectrum_flagmask,spectrum_abstimeinst
    global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
    print(time.asctime()+' '+str(args))
    if (args[0]=='timer'):
        return;
    elif (args[0]=="settextchannelphase"):
        time_channelphase=args[1]
        if (datafile!='stream'):
            spectrum_draw()
        else:
            forcerecalc=True
    elif (args[0]=="settimeinstant"):
        xlim=f1a.get_xlim();
        spectrum_abstimeinst=time_now+double(args[1])*(xlim[1]-xlim[0])+xlim[0];
        spectrum_timeinst=time.ctime(spectrum_abstimeinst).split(' ')[-2];
        if (datafile!='stream'):
            spectrum_draw()
        else:
            forcerecalc=True
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg);
        f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
        f2.canvas.send_cmd(newcontent2)
    elif (args[0]=="setflags"):#eg ..200,32,2..40,3..100,700..800,1000..
        spectrum_flagstr=''
        spectrum_flag0=[]
        spectrum_flag1=[]
        spectrum_flagmask=np.ones([spectrum_width])
        for c in range(1,len(args)):
            spectrum_flagstr+=args[c]
            if (c<len(args)-1):
                spectrum_flagstr+=","
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
            else:
                a=1#error
        #should still look for overlapping ranges here
        if (datafile!='stream'):
            spectrum_draw()
            matrix_draw()
        else:
            forcerecalc=True
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg);
        f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
        f2.canvas.send_cmd(newcontent2)
        f4.canvas.send_cmd("")
    elif (args[0]=="applytoall"):
        spectrum_antbase0=time_antbase0[:]
        spectrum_antbase1=time_antbase1[:]
        spectrum_corrHH=time_corrHH;
        spectrum_corrVV=time_corrVV;
        spectrum_corrHV=time_corrHV;
        spectrum_corrVH=time_corrVH;
        if (datafile!='stream'):
            spectrum_draw()
        else:
            forcerecalc=True
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg);
        f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
        if (len(time_antbase0)):
            waterfall_antbase0=[time_antbase0[0]]
            waterfall_antbase1=[time_antbase1[0]]
        else:
            waterfall_antbase0=[]
            waterfall_antbase1=[]
        waterfall_corrHH=time_corrHH;
        waterfall_corrVV=time_corrVV;
        waterfall_corrHV=time_corrHV;
        waterfall_corrVH=time_corrVH;
        if (waterfall_corrHH=='true'):
            waterfall_corrVV='false';
            waterfall_corrHV='false';
            waterfall_corrVH='false';
        elif (waterfall_corrVV=='true'):
            waterfall_corrHV='false';
            waterfall_corrVH='false';
        elif (waterfall_corrHV=='true'):
            waterfall_corrVH='false';
        if (datafile!='stream'):
            waterfall_draw()
        else:
            forcerecalc=True
        newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","",lastmsg);
        f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
        f2.canvas.send_cmd(newcontent2)
        f3.canvas.send_cmd(newcontent3)
    elif (args[0]=="setbaseline"):
        time_antbase0=[]
        time_antbase1=[]
        antbase=np.unique(([int(c[3:-1])-1 for c in datasd.cpref.inputs]))#unique antenna zero based indices
        for c in range((len(args)-1)/2):
            i0=int(args[c*2+1])
            i1=int(args[c*2+2])
            if (i0 in antbase and i1 in antbase):
                time_antbase0.append(i0)
                time_antbase1.append(i1)
    elif (rows!=None and (args[0]=="nextchunk" or args[0]=="prevchunk")):
        try:
#            dh.stop_sdisp()
#            del dh
            if (startrow==None):
                startrow=0
            if (args[0]=="nextchunk"):
                startrow=startrow+rows/4
            else:
                startrow=startrow-rows/4
            dh.load_k7_data(datafile,rows=rows,startrow=startrow)
            datasd=dh.sd_hist
        except Exception,e:
            print time.asctime()+" Failed to load file using k7 loader (%s)" % e
    else:
        time_corrHH=args[0]
        time_corrVV=args[1]
        time_corrHV=args[2]
        time_corrVH=args[3]
        time_legend=args[4]
        time_seltypemenu=args[5]
        time_minF=args[6]
        time_maxF=args[7]
        #args[8]
        time_minx=args[9]
        time_maxx=args[10]
        #args[11]
        #args[12]
        #args[13]
        #args[14]
        time_timeavg=args[15]
        time_channelphase=args[16]
        time_absminx=-1
        time_absmaxx=-1
        time_tmpmin=-1
        time_tmpmax=-1
        if (datasd.storage.frame_count > 0):
            tt = datasd.select_data(product=0, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
            fkeys = tt[0]#datasd.storage.corr_prod_frames[0].keys();
            time_now=fkeys[-1];          #get latest element
            if (len(time_minx.split(':'))==3):
                for f in fkeys:
                    if (time.ctime(f).split(' ')[-2]==time_minx):    #f is presumably UTC
                        time_absminx=f;
                        break
                if (time_absminx==-1):
                    #                'Tue Apr 12 14:13:23 2011'  (2011, 4, 12, 14, 13, 20, 1, 102, -1)
                    #                time.ctime(time.mktime(time.strptime(time.ctime(time.time()))))
                    thesplit=time_minx.split(':');
                    thetuple=time.gmtime(time_now)#returns a tuple
                    time_absminx=(time.mktime((thetuple[0],thetuple[1],thetuple[2],int(thesplit[0]),int(thesplit[1]),0,thetuple[6],thetuple[7],thetuple[8]))+double(thesplit[2]));
#                    time_minx='';
                time_tmpmin=time_absminx
            else:
                if (time_minx!=''):
                    time_tmpmin=double(time_minx)
            if (len(time_maxx.split(':'))==3):
                for f in fkeys:
                    if (time.ctime(f).split(' ')[-2]==time_maxx):
                        time_absmaxx=f;
                        break
                if (time_absmaxx==-1):
                    thesplit=time_maxx.split(':');
                    thetuple=time.gmtime(time_now)#returns a tuple
                    time_absmaxx=(time.mktime((thetuple[0],thetuple[1],thetuple[2],int(thesplit[0]),int(thesplit[1]),0,thetuple[6],thetuple[7],thetuple[8]))+double(thesplit[2]));
#                    time_maxx='';
                time_tmpmax=time_absmaxx
            else:
                if (time_maxx!=''):
                    time_tmpmax=double(time_maxx)
            if (time_minx!='' and time_maxx!='' and time_tmpmax<time_tmpmin):
                tmp=time_absmaxx
                time_absmaxx=time_absminx
                time_absminx=tmp
                tmp=time_maxx
                time_maxx=time_minx
                time_minx=tmp

    if (datafile!='stream'):
        timeseries_draw()
    else:
        forcerecalc=True
    newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
    f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
    f1.canvas.send_cmd(newcontent1)#if there are other clients with this page
   # f1.canvas.send_cmd("alert('Server says: Plot updated...'); document.documentURI;")

#coverts time from hms to a floating point value
def converthmstof(hms):
    thehms=hms.split(':');
    if (thehms.length==3):
        val=float(thehms[0])*60.0*60.0+float(thehms[1])*60.0+float(thehms[2])
    else:
        val=-1;
    return val;

#do this per figure
data_server_portbase=4321;
data_server_n=5;
data_server_port=[]
data_server=[]
data_thread=[]
_request_handlers = {}
_request_type = {}
_request_time = {}
_request_lasttime = {}

def handle_data_user_event_timeseries(handlerkey,*args):
    try:
        # print(time.asctime()+' DATA '+str(args))
        if (args[0]=='sendfigure'):
            send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_yseries=(timeseries_fig['ydata'])[:]
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ydata.completed',np.zeros(np.shape(local_yseries)[:2]),'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.title',timeseries_fig['title'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xlabel',timeseries_fig['xlabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ylabel',timeseries_fig['ylabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xunit',timeseries_fig['xunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.yunit',timeseries_fig['yunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.legend',timeseries_fig['legend'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xdata',timeseries_fig['xdata'],'I'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.color',timeseries_fig['color'],'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmin',timeseries_fig['xmin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmax',timeseries_fig['xmax'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymin',timeseries_fig['ymin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymax',timeseries_fig['ymax'],'f'),handlerkey)
            for ispan,span in enumerate(timeseries_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.span[%d]'%(ispan),np.array(timeseries_fig['span'][ispan]),'H'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.spancolor',timeseries_fig['spancolor'],'b'),handlerkey)
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(twinplotyseries)),handlerkey)
                    send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ydata[%d][%d]'%(itwin,iline),linedata,'H'),handlerkey)
    except Exception, e:
        logger.warning("User event exception %s" % str(e))


def handle_data_user_event_spectrum(handlerkey,*args):
    try:
        # print(time.asctime()+' DATA '+str(args))
        if (args[0]=='sendfigure'):
            send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_yseries=(spectrum_fig['ydata'])[:]
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ydata.completed',np.zeros(np.shape(local_yseries)[:2]),'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.title',spectrum_fig['title'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xlabel',spectrum_fig['xlabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ylabel',spectrum_fig['ylabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xunit',spectrum_fig['xunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.yunit',spectrum_fig['yunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.legend',spectrum_fig['legend'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xdata',spectrum_fig['xdata'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.color',spectrum_fig['color'],'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmin',spectrum_fig['xmin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmax',spectrum_fig['xmax'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymin',spectrum_fig['ymin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymax',spectrum_fig['ymax'],'f'),handlerkey)
            for ispan,span in enumerate(spectrum_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.span[%d]'%(ispan),np.array(spectrum_fig['span'][ispan]),'H'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.spancolor',spectrum_fig['spancolor'],'b'),handlerkey)
            for itwin,twinplotyseries in enumerate(local_yseries):
                for iline,linedata in enumerate(twinplotyseries):
                    send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(twinplotyseries)),handlerkey)
                    send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ydata[%d][%d]'%(itwin,iline),linedata,'H'),handlerkey)
    except Exception, e:
        logger.warning("User event exception %s" % str(e))


def handle_data_user_event_waterfall(handlerkey,*args):
    try:
        # print(time.asctime()+' DATA '+str(args))
        if (args[0]=='sendfigure'):
            send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="starting data transfer"',handlerkey)
            local_cseries=(waterfall_fig['cdata'])[:]
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.cdata.completed',np.zeros(np.shape(local_cseries)[:2]),'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.title',waterfall_fig['title'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xlabel',waterfall_fig['xlabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ylabel',waterfall_fig['ylabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.clabel',waterfall_fig['clabel'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xunit',waterfall_fig['xunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.yunit',waterfall_fig['yunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.cunit',waterfall_fig['cunit'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.legend',waterfall_fig['legend'],'s'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xdata',waterfall_fig['xdata'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ydata',waterfall_fig['ydata'],'I'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.color',waterfall_fig['color'],'b'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmin',waterfall_fig['xmin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.xmax',waterfall_fig['xmax'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymin',waterfall_fig['ymin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.ymax',waterfall_fig['ymax'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.cmin',waterfall_fig['cmin'],'f'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.cmax',waterfall_fig['cmax'],'f'),handlerkey)
            for ispan,span in enumerate(waterfall_fig['span']):#this must be separated because it doesnt evaluate to numpy arrays individially
                send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.span[%d]'%(ispan),np.array(waterfall_fig['span'][ispan]),'H'),handlerkey)
            send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.spancolor',waterfall_fig['spancolor'],'b'),handlerkey)
            for iline,linedata in enumerate(local_cseries):
                send_data_cmd_handlerkey('document.getElementById("timeclientusereventroundtrip").innerHTML="sending line %d of %d"'%(iline+1,len(local_cseries)),handlerkey)
                send_binarydata_cmd_handlerkey(pack_binarydata_msg('fig.cdata[%d]'%(iline),linedata,'B'),handlerkey)
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
        finiteind=np.nonzero(np.isfinite(val)==True)[0]
        finitevals=val[finiteind]
        minval=np.min(finitevals)
        maxval=np.max(finitevals)
        if (maxval==minval):
            maxval=minval+1
        maxrange=2**(8*bytesize[dtype])-4;#also reserve -inf,inf,nan
        val[finiteind]=np.array((val[finiteind]-minval)/(maxval-minval)*(maxrange),dtype='int')+3
        val[np.nonzero(val==-np.inf)[0]]=0
        val[np.nonzero(val==np.inf)[0]]=1
        val[np.nonzero(np.isnan(val)==True)[0]]=2
        buff+=struct.pack('<%d'%(len(val))+structconv[dtype],*val)
        if (dtype=='I'):
            buff+=struct.pack('<d',minval)#use double precision limits here
            buff+=struct.pack('<d',maxval)
        else:
            buff+=struct.pack('<f',minval)
            buff+=struct.pack('<f',maxval)
    elif (dtype=='f' or dtype=='d' or dtype =='b' or dtype =='h' or dtype =='i'):#encodes list or ndarray of floats
        buff+=struct.pack('<%d'%(len(val))+structconv[dtype],*val)
    return buff

def parse_data_web_cmd(s, request):
    try:
        action = s[1:s.find(" ")]
        args = s[s.find("args='")+6:-2].split(",")
        _request_type[request]=action
        if (request in _request_lasttime):
            _request_lasttime[request]=_request_time[request]
        else:
            _request_lasttime[request]=time.time()
        _request_time[request]=time.time()
        if (action=='data_user_event_timeseries'):
            handle_data_user_event_timeseries(request,*args)
        elif (action=='data_user_event_spectrum'):
            handle_data_user_event_spectrum(request,*args)
        elif (action=='data_user_event_waterfall'):
            handle_data_user_event_waterfall(request,*args)
        
    except AttributeError:
        logger.warning("Cannot find request method handle_data_%s" % action)

def send_binarydata_cmd_handlerkey(binarydata, handlerkey):
    try:
#        handlerkey._request_handler.connection.send(binarydata)
        handlerkey.ws_stream.send_message(binarydata,binary=True)
    except AttributeError:
         # connection has gone
        logger.info("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_request_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)" % str(e))

def send_data_cmd_handlerkey(cmd, handlerkey):
    #for r in self._request_handlers.keys():
    try:
        frame="/*exec_user_cmd*/ function callme(){%s; return;};callme();" % cmd;#ensures that vectors of data is not sent back to server!
        handlerkey.ws_stream.send_message(frame.decode('utf-8'))
    except AttributeError:
         # connection has gone
        logger.info("Connection %s has gone. Closing..." % handlerkey.connection.remote_addr[0])
        deregister_request_handler(handlerkey)
    except Exception, e:
        logger.warning("Failed to send message (%s)" % str(e))

def register_request_handler(request):
    _request_handlers[request] = request.connection.remote_addr[0]

def deregister_request_handler(request):
    del _request_handlers[request]

def web_binarydata_socket_transfer_data(request):
    register_request_handler(request)
    while True:
        try:
            data = request.ws_stream.receive_message()
            # if isinstance(data, unicode):#unicode
            # else:#binary
            parse_data_web_cmd(line,request)
        except Exception, e:
            logger.error("Caught exception (%s). Removing registered handler" % str(e))
            deregister_request_handler(request)
            return

def web_data_socket_transfer_data(request):
    register_request_handler(request)
    while True:
        try:
            line = request.ws_stream.receive_message()
            logger.debug("Received web cmd: %s" % line)
            parse_data_web_cmd(line,request)
        except Exception, e:
            logger.error("Caught exception (%s). Removing registered handler" % str(e))
            deregister_request_handler(request)
            return
        
def makedataservers():
    global data_server_portbase,data_server_n,data_server_port,data_server,data_thread
    data_server_port=[]
    data_server=[]
    data_thread=[]
    try:
        for c in range(data_server_n):
            data_server_port.append(data_server_portbase+c)
            data_server.append(simple_server.WebSocketServer(('', data_server_portbase+c), web_data_socket_transfer_data, simple_server.WebSocketRequestHandler))
            data_thread.append(thread.start_new_thread(data_server[c].serve_forever, ()))
    except Exception, e:
        print "Failed to create webserver. (%s)" % str(e)
        # logger.error("Failed to create webserver. (%s)" % str(e))
        sys.exit(1)
    
def stopdataservers():
    for c in range(data_server_n):
        data_server[c].shutdown()
    
    
def spectrum_event(figno,*args):
    global forcerecalc
    global dh,datasd,rows,startrow,spectrum_width
    global spectrum_abstimeinst,time_channelphase,antennamappingmode;
    global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx, time_timeavg
    global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend,spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx, spectrum_timeinst, spectrum_timeavg
    global spectrum_flagstr,spectrum_flag0,spectrum_flag1,spectrum_flagmask
    global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
    if (args[0]!="sendfigure"):
        print(time.asctime()+' '+str(args))
    if (args[0]=="settexttimeinst"):
        spectrum_timeinst=args[1]
        spectrum_abstimeinst=-1;
        if (len(datasd.storage.frame_count)>0):
            tt = datasd.select_data(product=0, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
            fkeys = tt[0]#datasd.storage.corr_prod_frames[0].keys();
            if (len(spectrum_timeinst.split(':'))==3):
                for f in fkeys:
                    if (time.ctime(f).split(' ')[-2]==spectrum_timeinst):
                        spectrum_abstimeinst=f;
            elif (spectrum_timeinst!=''):#possibly just a negative number (in seconds previous to now)
                spectrum_abstimeinst=fkeys[-1]+double(spectrum_timeinst)
        if (datafile!='stream'):
            timeseries_draw()
        else:
            forcerecalc=True
    elif (args[0]=="setchannelphase"):
        xlim=f2a.get_xlim();
        chan=double(args[1])*(xlim[1]-xlim[0])+xlim[0];
        if (spectrum_seltypemenux=='channel' or datasd.receiver.center_freqs_mhz==[]):
            chan=chan
        elif (spectrum_seltypemenux=='mhz'):#work out channel number from freq
            chan=(chan-datasd.receiver.center_freqs_mhz[0])/(datasd.receiver.center_freqs_mhz[-1]-datasd.receiver.center_freqs_mhz[0])*spectrum_width;
        else:
            chan=(chan*1000.0-datasd.receiver.center_freqs_mhz[0])/(datasd.receiver.center_freqs_mhz[-1]-datasd.receiver.center_freqs_mhz[0])*spectrum_width;
        if (chan<0):
            chan=0
        elif(chan>=spectrum_width):
            chan=spectrum_width-1
        time_channelphase=str(int(chan))
        if (datafile!='stream'):
            timeseries_draw()
        else:
            forcerecalc=True
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        f1.canvas.send_cmd(newcontent1)
    elif (args[0]=="setflags"):#eg ..200,32,2..40,3..100,700..800,1000..
        spectrum_flagstr=''
        spectrum_flag0=[]
        spectrum_flag1=[]
        spectrum_flagmask=np.ones([spectrum_width])
        for c in range(1,len(args)):
            spectrum_flagstr+=args[c]
            if (c<len(args)-1):
                spectrum_flagstr+=","
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
            else:
                a=1#error
        #should still look for overlapping ranges here
        if (datafile!='stream'):
            timeseries_draw()
            matrix_draw()
        else:
            forcerecalc=True
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        f1.canvas.send_cmd(newcontent1)
        f4.canvas.send_cmd("")
    elif (args[0]=="applytoall"):
        time_antbase0=spectrum_antbase0[:]
        time_antbase1=spectrum_antbase1[:]
        time_corrHH=spectrum_corrHH;
        time_corrVV=spectrum_corrVV;
        time_corrHV=spectrum_corrHV;
        time_corrVH=spectrum_corrVH;
        if (datafile!='stream'):
            timeseries_draw()
        else:
            forcerecalc=True
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        if (len(time_antbase0)):
            waterfall_antbase0=[time_antbase0[0]]
            waterfall_antbase1=[time_antbase1[0]]
        else:
            waterfall_antbase0=[]
            waterfall_antbase1=[]
        waterfall_corrHH=time_corrHH;
        waterfall_corrVV=time_corrVV;
        waterfall_corrHV=time_corrHV;
        waterfall_corrVH=time_corrVH;
        if (waterfall_corrHH=='true'):
            waterfall_corrVV='false';
            waterfall_corrHV='false';
            waterfall_corrVH='false';
        elif (waterfall_corrVV=='true'):
            waterfall_corrHV='false';
            waterfall_corrVH='false';
        elif (waterfall_corrHV=='true'):
            waterfall_corrVH='false';
        if (datafile!='stream'):
            waterfall_draw()
        else:
            forcerecalc=True
        newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","",lastmsg);
        f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
        f1.canvas.send_cmd(newcontent1)
        f3.canvas.send_cmd(newcontent3)
    elif (args[0]=="setbaseline"):
        spectrum_antbase0=[]
        spectrum_antbase1=[]
        antbase=np.unique(([int(c[3:-1])-1 for c in datasd.cpref.inputs]))#unique antenna zero based indices
        for c in range((len(args)-1)/2):
            i0=int(args[c*2+1])
            i1=int(args[c*2+2])
            if (i0 in antbase and i1 in antbase):
                spectrum_antbase0.append(i0)
                spectrum_antbase1.append(i1)
    elif (rows!=None and (args[0]=="nextchunk" or args[0]=="prevchunk")):
        try:
            if (startrow==None):
                startrow=0
            if (args[0]=="nextchunk"):
                startrow=startrow+rows/4
            else:
                startrow=startrow-rows/4
            dh.load_k7_data(datafile,rows=rows,startrow=startrow)
            datasd=dh.sd_hist
        except Exception,e:
            print time.asctime()+"Failed to load file using k7 loader (%s)" % e
    else:
        spectrum_corrHH=args[0]
        spectrum_corrVV=args[1]
        spectrum_corrHV=args[2]
        spectrum_corrVH=args[3]
        spectrum_legend=args[4]
        spectrum_seltypemenu=args[5]
        spectrum_minF=args[6]
        spectrum_maxF=args[7]
        spectrum_seltypemenux=args[8]
        spectrum_minx=args[9]
        spectrum_maxx=args[10]
        #args[11]
        #args[12]
        #args[13]
        spectrum_timeinst=args[14]
        spectrum_timeavg=args[15]
        #args[16]
        spectrum_abstimeinst=-1;
        if (datasd.storage.frame_count > 0):
            tt = datasd.select_data(product=0, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
            fkeys = tt[0]#datasd.storage.corr_prod_frames[0].keys();
            if (len(spectrum_timeinst.split(':'))==3):
                for f in fkeys:
                    if (time.ctime(f).split(' ')[-2]==spectrum_timeinst):
                        spectrum_abstimeinst=f;
            elif (spectrum_timeinst!=''):#possibly just a negative number (in seconds previous to now)
                spectrum_abstimeinst=fkeys[-1]+double(spectrum_timeinst)
        if (spectrum_seltypemenux!='channel' and datasd.receiver.center_freqs_mhz==[]):
            spectrum_seltypemenux='channel'
            f2.canvas.send_cmd('alert("Warning: no center frequencies available, reverting to channel")')
            
    if (datafile!='stream'):
        spectrum_draw()
    else:
        forcerecalc=True
    newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg);
    f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
    f2.canvas.send_cmd(newcontent2)

def waterfall_event(figno,*args):
    global forcerecalc
    global dh,datasd,rows,startrow,spectrum_width
    global time_channelphase,antennamappingmode;
    global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx, time_timeavg
    global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend, spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx, spectrum_timeinst, spectrum_timeavg
    global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH, waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
    print(time.asctime()+' '+str(args))
    if (args[0]=="applytoall"):
        time_antbase0=waterfall_antbase0[:]
        time_antbase1=waterfall_antbase1[:]
        time_corrHH=waterfall_corrHH;
        time_corrVV=waterfall_corrVV;
        time_corrHV=waterfall_corrHV;
        time_corrVH=waterfall_corrVH;
        if (datafile!='stream'):
            timeseries_draw()
        else:
            forcerecalc=True
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        spectrum_antbase0=waterfall_antbase0[:]
        spectrum_antbase1=waterfall_antbase1[:]
        spectrum_corrHH=waterfall_corrHH;
        spectrum_corrVV=waterfall_corrVV;
        spectrum_corrHV=waterfall_corrHV;
        spectrum_corrVH=waterfall_corrVH;
        if (datafile!='stream'):
            spectrum_draw()
        else:
            forcerecalc=True
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg)
        f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
        f1.canvas.send_cmd(newcontent1)
        f2.canvas.send_cmd(newcontent2)
    elif (args[0]=="setbaseline"):
        waterfall_antbase0=[]
        waterfall_antbase1=[]
        for c in range((len(args)-1)/2):
            waterfall_antbase0.append(int(args[c*2+1]))
            waterfall_antbase1.append(int(args[c*2+2]))
    elif (rows!=None and (args[0]=="nextchunk" or args[0]=="prevchunk")):
        try:
            if (startrow==None):
                startrow=0
            if (args[0]=="nextchunk"):
                startrow=startrow+rows/4
            else:
                startrow=startrow-rows/4
            dh.load_k7_data(datafile,rows=rows,startrow=startrow)
            datasd=dh.sd_hist
        except Exception,e:
            print time.asctime()+" Failed to load file using k7 loader (%s)" % e
    else:
        waterfall_corrHH=args[0]
        waterfall_corrVV=args[1]
        waterfall_corrHV=args[2]
        waterfall_corrVH=args[3]
        #args[4]
        waterfall_seltypemenu=args[5]
        waterfall_minF=args[6]
        waterfall_maxF=args[7]
        waterfall_seltypemenux=args[8]
        waterfall_minx=args[9]
        waterfall_maxx=args[10]
        #args[11]
        waterfall_miny=args[12]
        waterfall_maxy=args[13]
        #args[14]
        #args[15]
        #args[16]
        if (waterfall_seltypemenux!='channel' and datasd.receiver.center_freqs_mhz==[]):
            waterfall_seltypemenux='channel'
            f3.canvas.send_cmd('alert("Warning: no center frequencies available, reverting to channel")')
    if (datafile!='stream'):
        waterfall_draw()
    else:
        forcerecalc=True
    newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","",lastmsg);
    f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
    f3.canvas.send_cmd(newcontent3)

def matrix_event(figno,*args):
    global forcerecalc
    global dh,datasd,rows,startrow,spectrum_width
    print(time.asctime()+' '+str(args))
    if (len(args) and rows!=None and (args[0]=="nextchunk" or args[0]=="prevchunk")):
        try:
            if (startrow==None):
                startrow=0
            if (args[0]=="nextchunk"):
                startrow=startrow+rows/4
            else:
                startrow=startrow-rows/4
            dh.load_k7_data(datafile,rows=rows,startrow=startrow)
            datasd=dh.sd_hist
        except Exception,e:
            print time.asctime()+" Failed to load file using k7 loader (%s)" % e
    if (datafile!='stream'):
        matrix_draw()
    else:
        forcerecalc=True
    f4.canvas.send_cmd("")
    
def help_event(figno,*args):
    print(time.asctime()+' '+str(args))
    if (args[0]=="requestdata"):
        print args[0],args[1],args[2]
        for iline in range(int(args[1])):
            vals=np.random.rand(int(args[2]))
            linestr=('['+string.join(['%.4f'%(a) for a in vals],',')+']')
            f5.canvas.send_cmd('receivedata(%d,%d,%d,'%(iline,int(args[1]),int(args[2]))+linestr+')')

f1=figure(1)
f1a=f1.add_subplot(111)
f1b=0
f2=figure(2)
f2a=f2.add_subplot(111)
f2b=0
f3=figure(3)
f3a=f3.add_subplot(111)
f4=figure(4)
f4a=f4.add_subplot(111)
f5=figure(5)
f5a=f5.add_subplot(111)
dh=katsdisp.KATData()
if (datafile=='stream'):
    dh.start_spead_receiver(capacity=0.05,store2=True)
    datasd=dh.sd
elif (datafile=='k7simulator'):
    datafile='stream'
    dh.start_direct_spead_receiver(capacity=0.05,store2=True)
    datasd=dh.sd
else:
    try:
        dh.load_k7_data(datafile,rows=rows,startrow=startrow)
    except Exception,e:
        print time.asctime()+" Failed to load file using k7 loader (%s)" % e
        dh.load_ff_data(datafile)
    datasd=dh.sd_hist

if (datasd.storage.frame_count > 0):
    spectrum_width=datasd.receiver.channels;
    spectrum_flagmask=np.ones([spectrum_width])
    spectrum_flagstr=''

#
lastmsg='loading'
makedataservers();

# show a plot
f1=figure(1)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"newtime_plot.html")
cc = html_wrap_file.read().replace("<!--data_port-->",str(data_server_port[0])).replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f1.canvas._custom_content = cc
f1.canvas._user_event = timeseries_event
f1.canvas._user_cmd_ret = user_cmd_ret
f1.canvas._user_event(0,time_corrHH, time_corrVV, time_corrHV, time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,-1);

f2=figure(2)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"newspectrum_plot.html")
cc = html_wrap_file.read().replace("<!--data_port-->",str(data_server_port[1])).replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f2.canvas._custom_content = cc
f2.canvas._user_event = spectrum_event
f2.canvas._user_cmd_ret = user_cmd_ret
f2.canvas._user_event(1,spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH,time_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",-1);

f3=figure(3)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"newwaterfall_plot.html")
cc = html_wrap_file.read().replace("<!--data_port-->",str(data_server_port[2])).replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f3.canvas._custom_content = cc
f3.canvas._user_event = waterfall_event
f3.canvas._user_cmd_ret = user_cmd_ret
f3.canvas._user_event(2,waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","",-1);

f4=figure(4)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"matrix_plot.html")
cc = html_wrap_file.read().replace("<!--data_port-->",str(data_server_port[3])).replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f4.canvas._custom_content = cc
f4.canvas._user_event = matrix_event
f4.canvas._user_cmd_ret = user_cmd_ret
f4.canvas._user_event(3,-1);

f5=figure(5)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"newhelp.html")
cc = html_wrap_file.read().replace("<!--data_port-->",str(data_server_port[4])).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f5.canvas._custom_content = cc
f5.canvas._user_event = help_event
f5.canvas._user_cmd_ret = user_cmd_ret
f4.canvas._user_event(4,-1);

forcerecalc=False
antbase=0
lastantbase=0
iloop=0
time_last=0
loop_time=0
last_real_time=time.time()
reissuenotice=0
nowdelay=0
if (datafile!='stream'):
    show(layout='figure1',open_plot=opts.open_plot)
else:
    show(layout='figure1',block=False,open_plot=opts.open_plot)
    while True:
        #if (datasd.storage.frame_count > 0 and datasd.storage.frame_count % 20 == 0): print_top_100()
        ts_start = time.time()
        if (datasd.storage.frame_count==0):
            if (reissuenotice==0):
                print 'Please resume capture, and then re-issue metadata'
                reissuenotice=1;
            msg='document.getElementById("healthtext").innerHTML="empty store for %ds";'%(ts_start-last_real_time)
        else:
            reissuenotice=0
            if (datasd.receiver.channels==0):
                msg='document.getElementById("healthtext").innerHTML="empty store for %ds";'%(ts_start-last_real_time)
            elif (spectrum_width is None or spectrum_width!=datasd.receiver.channels):
                print time.asctime()+' nchannels change from ',spectrum_width,' to ',datasd.receiver.channels
                spectrum_width=datasd.receiver.channels
                spectrum_flagmask=np.ones([spectrum_width])
                spectrum_flagstr=''
                msg='document.getElementById("healthtext").innerHTML="empty store for %ds";'%(ts_start-last_real_time)
            else:
                antbase=np.unique(([int(c[3:-1])-1 for c in datasd.cpref.inputs]))#unique antenna zero based indices
                s = datasd.select_data(product=0, end_time=-2, start_channel=0, stop_channel=1, include_ts=True)
                if (len(s[0])>0):#store not entirely empty
                    time_now=s[0][-1]
                    if (time_now==time_last):
                        nowdelay+=1;
                    else:
                        nowdelay=0;
                    if (len(s[0])>1):
                        time_nownow=s[0][-2]
                        if (nowdelay>(time_now-time_nownow)+1):
                            msg='document.getElementById("healthtext").innerHTML="halted stream";'
                        else:
                            msg='document.getElementById("healthtext").innerHTML="%gs dumps";'%(time_now-time_nownow)
                    else:#one element in store
                        msg='document.getElementById("healthtext").innerHTML="activating";'
                else:#store is empty
                    time_now=0
                    msg='document.getElementById("healthtext").innerHTML="store empty for %ds";'%(ts_start-last_real_time)
                
                if (1):#forcerecalc or time_last!=time_now):
                    forcerecalc=False
                    timeseries_draw()
                    ts_ts_end = time.time()
                    spectrum_draw()
                    ts_sp_end = time.time()
                    waterfall_draw()
                    ts_wf_end = time.time()
                    #matrix_draw()
                    ts_end = time.time()
                    last_real_time=ts_end
                    time_last=time_now
                    strn="Timeseries: %.2fs, Spectrum: %.2fs, Waterfall: %.2fs, Matrix: %.2fs, Total: %.2fs" % (ts_ts_end - ts_start, ts_sp_end - ts_ts_end, ts_wf_end - ts_sp_end, ts_end - ts_wf_end, ts_end - ts_start)
                    f1.canvas.send_cmd('document.getElementById("timeserveroverview").innerHTML="'+strn+'";')
                    f2.canvas.send_cmd('document.getElementById("timeserveroverview").innerHTML="'+strn+'";')
                    f3.canvas.send_cmd('document.getElementById("timeserveroverview").innerHTML="'+strn+'";')
        if (lastmsg!=msg or not np.array_equal(lastantbase,antbase)):
            lastmsg=msg
            if (not np.array_equal(lastantbase,antbase)):
                otime_antbase0=time_antbase0
                otime_antbase1=time_antbase1
                time_antbase0=[]
                time_antbase1=[]
                for c in range(len(otime_antbase0)):
                    if (otime_antbase0[c] in antbase and otime_antbase1[c] in antbase):
                        time_antbase0.append(otime_antbase0[c])
                        time_antbase1.append(otime_antbase1[c])
                ospectrum_antbase0=spectrum_antbase0
                ospectrum_antbase1=spectrum_antbase1
                spectrum_antbase0=[]
                spectrum_antbase1=[]
                for c in range(len(ospectrum_antbase0)):
                    if (ospectrum_antbase0[c] in antbase and ospectrum_antbase1[c] in antbase):
                        spectrum_antbase0.append(ospectrum_antbase0[c])
                        spectrum_antbase1.append(ospectrum_antbase1[c])
                owaterfall_antbase0=waterfall_antbase0
                owaterfall_antbase1=waterfall_antbase1
                waterfall_antbase0=[]
                waterfall_antbase1=[]
                for c in range(len(owaterfall_antbase0)):
                    if (owaterfall_antbase0[c] in antbase and owaterfall_antbase1[c] in antbase):
                        waterfall_antbase0.append(owaterfall_antbase0[c])
                        waterfall_antbase1.append(owaterfall_antbase1[c])
            
            newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase,lastmsg);
            f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
            newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"",lastmsg);
            f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
            newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","",lastmsg);
            f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
            if (not np.array_equal(lastantbase,antbase)):
                lastantbase=antbase
                f1.canvas.send_cmd(newcontent1)
                f2.canvas.send_cmd(newcontent2)
                f3.canvas.send_cmd(newcontent3)
                # f4.canvas.send_cmd(newcontent4)
        f1.canvas.send_cmd(msg)
        f2.canvas.send_cmd(msg)
        f3.canvas.send_cmd(msg)
        # f4.canvas.send_cmd(msg)
                
        
        loop_time = time.time() - ts_start
        iloop+=1
        time.sleep((1 - loop_time) if loop_time <= 1 else 0)
