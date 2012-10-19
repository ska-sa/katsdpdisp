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
#note may need to reaugment file:
#on kat-dc1.karoo do ps aux | grep aug
#see something like /usr/bin/python /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -v -b -d /var/kat/data/staging --dbe=dbe7
#must then run /usr/local/bin/k7_augment.py -c xmlrpc:http://192.168.193.3:2010 -s systems/karoo_kat.conf -o -f filename.h5 to augment in place
#####################################################################################
##to debug somewhere in code, run this command: from IPython.Shell import IPShellEmbed; IPShellEmbed()()
##or if crashed then just type debug
#####################################################################################
##Import libraries used
import matplotlib
import optparse
matplotlib.use('module://mplh5canvas.backend_h5canvas')
import katsdisp
import numpy
from pylab import *
import time
import logging
import sys
from pkg_resources import resource_filename

import sys
import types

numpy.seterr(divide='ignore')

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
    logger.debug("Got return from user event: %s" % str(args))

def delayformatter(x,pos):
    global time_now,time_absminx,time_absmaxx
    'The two args are the value and tick position'
    if (time_absmaxx>=0):
        return time.ctime(x+time_now).split(' ')[-2]
    else:
        return str(x)+' \n'+time.ctime(x+time_now).split(' ')[-2]
    
def get_time_series(self, dtype='mag', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    global spectrum_flagmask,time_timeavg,time_now,spectrum_flagstr,spectrum_width
    if product is None: product = self.default_product
#    tp = self.select_data(dtype=dtype, sum_axis=1, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel)
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [nan*numpy.zeros(97,dtype='float64'),nan*numpy.zeros(97,dtype='float32'),""]
    if (dtype=='pow' or dtype=='mag'):
        tp = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel)
        #tp[1]=sum(tp[1],1)
        if (tp[1]==[]):
            tp[0]=np.array([0])
            tp[1]=np.array([0])
        else:
            if (np.shape(tp[1])[1]!=spectrum_width):
                spectrum_width=np.shape(tp[1])[1]
                spectrum_flagmask=numpy.ones([spectrum_width])
                spectrum_flagstr=''
            tp[1]=dot(tp[1],spectrum_flagmask)
            #tp[1] = np.asarray([np.dot(t,spectrum_flagmask) for t in tp[1]])
    elif (dtype=='phase'):
        if (time_channelphase!=''):
            ch=int(time_channelphase);
            if (ch<0):
                ch=0
            elif (ch>=spectrum_width):
                ch=spectrum_width-1
            tp = self.select_data(dtype=dtype, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=ch, stop_channel=ch+1)
            if (tp[1]==[]):
                tp[0]=np.array([0])
                tp[1]=np.array([0])
        else:
            tp = self.select_data(dtype='complex', product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel)
            if (tp[1]==[]):
                tp[0]=np.array([0])
                tp[1]=np.array([0])
            else:
                if (np.shape(tp[1])[1]!=spectrum_width):
                    spectrum_width=np.shape(tp[1])[1]
                    spectrum_flagmask=numpy.ones([spectrum_width])
                    spectrum_flagstr=''
                tp[1]=np.angle(np.dot(np.array(tp[1]),spectrum_flagmask))
    if (dtype=='pow'):
        tp[1]=10.0*log10(tp[1]);
    ts = tp[0]-tp[0][-1]    #time delay
    time_now=tp[0][-1]
    if (time_timeavg!=''):
        reduction=int(time_timeavg);
#        reduction=int(double(time_timeavg)/(tp[0][1]-tp[0][0]));
        tp[1]=numpy.diff(numpy.cumsum(tp[1])[0::reduction])/double(reduction);
        ts=ts[0::reduction][0:len(tp[1])];
#    print tp[0][0],time.ctime(tp[0][0])
    return [ts,tp[1],str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]#self.cpref.id_to_real_str(product, short=True)


def plot_time_series(self, dtype='mag', products=None, end_time=-120, start_channel=0, stop_channel=spectrum_width,colours=None):
    global f1,f1a,f1b,spectrum_width
    global time_absminx,time_absmaxx,time_minx,time_maxx
    if products is None: products = self.default_products
    if (dtype=='phase' and time_channelphase!=''):
        title='Phase for channel '+time_channelphase
    else:
        if (dtype=='powphase' and time_channelphase!=''):
            title="Phase for channel "+time_channelphase+" and summed power for "+str(numpy.sum(spectrum_flagmask,dtype='int'))+" channels";
        else:
            title="Summed " + str(dtype) + " for "+str(numpy.sum(spectrum_flagmask,dtype='int'))+" channels";
        if (len(spectrum_flagstr)):
            if (len(spectrum_flagstr)>50):
                title+=", excluding\n("+spectrum_flagstr[:50]+"...)";
            else:
                title+=", excluding\n("+spectrum_flagstr+")";
    f1a.set_title(title)
    f1a.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(delayformatter))
    if (self.storage.frame_count==0):
        s=[[0]]
    else:
        s = self.select_data(product=0, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
    start_time=0
    end_time=s[0][-1]
    minf1a=np.inf
    maxf1a=-np.inf
    if (time_absminx>0):
        start_time=time_absminx
    if (time_absmaxx>0):
        end_time=time_absmaxx
    if (dtype=='powphase'):
        if (f1b==0):
            f1b=f1a.twinx()
        f1b.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(delayformatter))
        for i,product in enumerate(products):
            data = get_time_series(self,dtype='pow',product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            f1a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
            minf1a=min(minf1a,min(data[1]));
            maxf1a=max(maxf1a,max(data[1]));
            data = get_time_series(self,dtype='phase',product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            f1b.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
    else:
        if (f1b):
            f1b.clear()
            f1.delaxes(f1b)
            f1b=0
        data_time = 0
        plot_time = 0
        for i,product in enumerate(products):
            ts_start = time.time()
            data = get_time_series(self,dtype=dtype,product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
            if data[1].shape == ():
                logger.warning("Insufficient data to plot time series")
                return
            ts_mid = time.time()
            f1a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
            data_time += ts_mid - ts_start
            plot_time += time.time() - ts_mid
            minf1a=min(minf1a,min(data[1]));
            maxf1a=max(maxf1a,max(data[1]));
        logger.warning("Data time: %.3fs, Plot time: %.3fs\n" % (data_time, plot_time))
    if (time_legend=='true'):
        f1a.legend(loc=0)
    if (spectrum_abstimeinst>0):
        timeline=spectrum_abstimeinst-time_now;
        f1a.axvspan(timeline,timeline,0,1,color='g',alpha=0.5)

    if (f1b):
        f1b.axis('tight')
        f1b.set_ylabel('Phase [radians]')
    f1a.axis('tight')
    extrapadding=(maxf1a-minf1a)*0.025;
    f1a.set_ylim([minf1a-extrapadding,maxf1a+extrapadding])
    f1a.set_xlabel("Time since " + time.ctime(s[0][-1]))
    if dtype == 'phase':
        f1a.set_ylabel("Phase [radians]")
    elif (dtype=='pow' or dtype=='powphase'): f1a.set_ylabel("dB")
    else: f1a.set_ylabel("Magitude [arbitrary units]")

def get_spectrum(self, product=None, dtype='mag', start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width, reverse_order=False, avg_axis=None, sum_axis=None, include_ts=False):
    global spectrum_seltypemenux,spectrum_abstimeinst,spectrum_timeinst,spectrum_timeavg,spectrum_width
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [nan*numpy.zeros(97,dtype='float64'),nan*numpy.zeros(97,dtype='float32'),""],numpy.zeros(97,dtype='int')

    if (dtype=='pow'):
        s,flagarray = self.select_data(product=product, dtype="mag", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=reverse_order, avg_axis=avg_axis, sum_axis=sum_axis, include_ts=include_ts,include_flags=True)
        s=10.0*log10(s);
    else:
        s,flagarray = self.select_data(product=product, dtype=dtype, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=reverse_order, avg_axis=avg_axis, sum_axis=sum_axis, include_ts=include_ts,include_flags=True)
            
    if (s.shape==()):
        sx=numpy.nan
    elif (spectrum_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
        sx=[f for f in range(0,s.shape[0])]
    elif (spectrum_seltypemenux=='mhz'):
        sx=[(self.receiver.center_freqs_mhz[start_channel+f]) for f in range(0,s.shape[0])]
    else:
        sx=[(self.receiver.center_freqs_mhz[start_channel+f]/1000.0) for f in range(0,s.shape[0])]
    return [sx,s,str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])],flagarray

def plot_spectrum(self, dtype='mag', products=None, start_channel=0, stop_channel=spectrum_width, colours=None):
    global f2,f2a,f2b,spectrum_width
    global spectrum_abstimeinst,spectrum_timeavg

    if products is None: products = self.default_products
    if (spectrum_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
        f2a.set_xlabel("Channel Number")
    elif (spectrum_seltypemenux=='mhz'):
        f2a.set_xlabel("Frequency [MHz]")
    else:
        f2a.set_xlabel("Frequency [GHz]")
    if (spectrum_abstimeinst>0):
        s=[[spectrum_abstimeinst]]
    elif (self.storage.frame_count==0):
        s=[[0]]
    else:
        s = self.select_data(product=0, end_time=-1, start_channel=0, stop_channel=1, include_ts=True)
    avg = ""
    average=1;
    if (spectrum_timeavg!=''):
        average=int(spectrum_timeavg);
    if average > 1: avg = " (" + str(average) + " dump average)"
    if dtype == 'phase':
        f2a.set_ylabel("Phase [radians]")
        f2a.set_ylim(ymin=-np.pi,ymax=np.pi)
    elif (dtype=='pow' or dtype=='powphase'): f2a.set_ylabel("dB")
    else: f2a.set_ylabel("Magitude [arbitrary units]")
    if (spectrum_abstimeinst>0):
        start_time=spectrum_abstimeinst
        end_time=spectrum_abstimeinst+average
    else:
        start_time=0
        end_time=-average

    flagarray=np.zeros(stop_channel-start_channel,'bool')
    if (dtype=='powphase'):
        if (f2b==0):
            f2b=f2a.twinx()
        for i,product in enumerate(products):
            data,flagsa=get_spectrum(self,product=product, dtype='pow', start_channel=start_channel, stop_channel=stop_channel, start_time=start_time,end_time=end_time, avg_axis=0);
            if np.shape(flagsa)!=np.shape(flagarray):
                flagsa=flagsa.any(axis=0)
            flagarray|=np.array(flagsa,dtype='bool')
            f2a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
            data,flagsa=get_spectrum(self,product=product, dtype='phase', start_channel=start_channel, stop_channel=stop_channel, start_time=start_time, end_time=end_time, avg_axis=0);
            f2b.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])
    else:
        if (f2b):
            f2b.clear()
            f2.delaxes(f2b)
            f2b=0
        for i,product in enumerate(products):
            data,flagsa=get_spectrum(self,product=product, dtype=dtype, start_channel=start_channel, stop_channel=stop_channel, start_time=start_time,end_time=end_time, avg_axis=0);
            if np.shape(flagsa)!=np.shape(flagarray):
                flagsa=flagsa.any(axis=0)
            flagarray|=np.array(flagsa,dtype='bool')
            f2a.plot(data[0],data[1],color=colours[i],label=data[2],linewidth=linewidthdict[product[2]],linestyle=linestyledict[product[2]])

    flags=[]
    chanwidth=stop_channel-start_channel
    flagstart=0
    flagstop=0
    
    while (flagstop<chanwidth):
        flagstart=flagstop
        while (flagstart<chanwidth and flagarray[flagstart]==0):
            flagstart+=1
        flagstop=flagstart
        while (flagstop<chanwidth and flagarray[flagstop]!=0):
            flagstop+=1
        flags.append((flagstart,flagstop))
    
    if dtype == 'phase': f2a.set_title("Phase Spectrum at " + time.ctime(s[0][-1]) + avg)
    elif (dtype=='powphase'): f2a.set_title("Power&Phase Spectrum at " + time.ctime(s[0][-1]) + avg)
    else: f2a.set_title("Power Spectrum at " + time.ctime(s[0][-1]) + avg)
    if (f2b):
        f2b.axis('tight')
        f2b.set_ylabel('Phase [radians]')
    f2a.axis('tight')
    if (spectrum_legend=='true'):
        f2a.legend(loc=0)
    return flags

def get_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    global time_now
    if product is None: product = self.default_product
    if (self.storage.frame_count==0 or self.cpref.user_to_id(product)<0):
        return [[],[],""]
    if (dtype=="pow"):
        rv=self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel,reverse_order=False,include_flags=True)
        tp0,tp1,flags = self.select_data(dtype="mag", product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel,reverse_order=False,include_flags=True)
        tp1=10.0*log10(tp1);
    else:
        tp0,tp1,flags = self.select_data(dtype=dtype, product=product, start_time=start_time, end_time=end_time, include_ts=True, start_channel=start_channel, stop_channel=stop_channel,reverse_order=False,include_flags=True)
    ts = tp0-tp0[-1]
    time_now=tp0[-1]
    tp1=numpy.array(tp1)
    if len(tp1.shape) == 1:
        logger.warning("Insufficient data to plot waterfall")
        return [[],[],""]
    return [ts,tp1,flags,str(product[0])+str(product[2][0])+str(product[1])+str(product[2][1])]

def plot_waterfall(self, dtype='phase', product=None, start_time=0, end_time=-120, start_channel=0, stop_channel=spectrum_width):
    global f3,f3a
    if product is None: product = self.default_product
    if self.storage is not None:
        tp = get_waterfall(self,dtype=dtype, product=product, start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel)
        if (tp[0]==[]):return 0
        f3a.set_title("Spectrogram (" + str(dtype) + ") for " + tp[3])
        f3a.set_ylabel("Time in seconds before now") # since " + time.ctime(sk[-frames:][0]))
        extent=[start_channel,stop_channel, tp[0][-1],tp[0][0]];
        if (waterfall_seltypemenux=='channel' or self.receiver.center_freqs_mhz==[]):
            f3a.set_xlabel("Channel Number")
        elif (waterfall_seltypemenux=='mhz'):
            f3a.set_xlabel("Frequency [MHz]")
            extent=[self.receiver.center_freqs_mhz[start_channel],self.receiver.center_freqs_mhz[stop_channel-1],tp[0][-1],tp[0][0]]
        else:
            f3a.set_xlabel("Frequency [GHz]")
            extent=[self.receiver.center_freqs_mhz[start_channel]/1000.0,self.receiver.center_freqs_mhz[stop_channel-1]/1000.0,tp[0][-1],tp[0][0]]
        shp=np.shape(tp[1])
        tp[1].reshape(-1)[find(tp[2])]=np.nan;
        tp[1].reshape(shp)
        cax = f3a.imshow(tp[1], aspect='auto', interpolation='bicubic', animated=True,extent=extent)
        cbar = f3.colorbar(cax)
        f3a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(delayformatter))
        theylim=f3a.get_ylim()
        f3a.set_ylim((max(theylim),min(theylim)))
        if (waterfall_seltypemenux!='channel'):
            f3a.set_xlim(f3a.get_xlim()[::-1])
    else:
        print time.asctime()+" No stored data available..."

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
                    spectrum_flagmask=numpy.ones([spectrum_width])
                    spectrum_flagstr=''
                im[a0*2+ip0][a0*2+ip1]=20.0*np.log10(dot(magdata,spectrum_flagmask))
                for a1 in range(a0+1,7):
                    if (a1 in antindices):
                        product=antennamap(a0,a1,pol[ip0]+pol[ip1])
                        magdata=self.select_data(product=product, dtype="mag", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=False, avg_axis=0, sum_axis=None, include_ts=False,include_flags=False)
                        phasedata=self.select_data(product=product, dtype="phase", start_time=start_time, end_time=end_time, start_channel=start_channel, stop_channel=stop_channel, reverse_order=False, avg_axis=0, sum_axis=None, include_ts=False,include_flags=False)
                        if (np.shape(magdata)[0]!=spectrum_width):
                            spectrum_width=np.shape(magdata)[0]
                            spectrum_flagmask=numpy.ones([spectrum_width])
                            spectrum_flagstr=''
                        im[a0*2+ip0][a1*2+ip1]=20.0*np.log10(dot(magdata,spectrum_flagmask))
                        if (np.shape(phasedata)[0]!=spectrum_width):
                            spectrum_width=np.shape(phasedata)[0]
                            spectrum_flagmask=numpy.ones([spectrum_width])
                            spectrum_flagstr=''
                        im[a1*2+ip0][a0*2+ip1]=dot(phasedata,spectrum_flagmask)
    return im

def plot_baseline_matrix(self, start_channel=0, stop_channel=spectrum_width):
    """Plot a matrix showing auto correlation power on the diagonal and cross correlation
    phase and power in the upper and lower segments."""
    global f4,f4a,spectrum_width,spectrum_flagmask
    if self.storage is not None:
        im = get_baseline_matrix(self,start_channel=0, stop_channel=spectrum_width)
        title="Baseline matrix, summed "+str(numpy.sum(spectrum_flagmask,dtype='int'))+" channels";
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

def makenewcontent(_flagstr,_antennamappingmode,_antbase0,_antbase1,_corrHH,_corrVV,_corrHV,_corrVH,_legend,_seltypemenu,_minF,_maxF,_seltypemenux,_minx,_maxx,_seltypemenuy,_miny,_maxy,_timeinst,_timeavg,_channelphase):
    if (len(_antbase0)):
        newcontent='\n'+'antbase0=['+''.join(str(x)+',' for x in _antbase0[:-1])+str(_antbase0[-1])+'];\n'
        newcontent+='antbase1=['+''.join(str(x)+',' for x in _antbase1[:-1])+str(_antbase1[-1])+'];\n'
    else:
        newcontent='\n'+'antbase0=[];\n'
        newcontent+='antbase1=[];\n'
    newcontent+='antennamappingmode='.join(str(_antennamappingmode))+';\n'
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
    cc=cc[:i0]+newcontent+cc[i1:]
    return cc;

def timeseries_draw():
    try:
        global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx
        global f1,f1a,f1b,spectrum_width
        ts_start = time.time()
        f1a.clear()
        if (f1b):
            f1b.clear()
            f1.delaxes(f1b)
            f1b=0;
        products=[]
        colours=[]
        ts_loop = time.time()
        for c in range(len(time_antbase0)):
            RGB=[(colourlist_R[time_antbase0[c]]+colourlist_R[time_antbase1[c]])/(255.0+255.0),(colourlist_G[time_antbase0[c]]+colourlist_G[time_antbase1[c]])/(255.0+255.0),(colourlist_B[time_antbase0[c]]+colourlist_B[time_antbase1[c]])/(255.0+255.0) ]
            if (time_corrHH=='true'):
                products.append(antennamap(time_antbase0[c],time_antbase1[c],'HH'))
                colours.append(RGB)
            if (time_corrVV=='true'):
                products.append(antennamap(time_antbase0[c],time_antbase1[c],'VV'))
                colours.append(RGB)
            if (time_corrHV=='true'):
                products.append(antennamap(time_antbase0[c],time_antbase1[c],'HV'))
                colours.append(RGB)
            if (time_corrVH=='true'):
                products.append(antennamap(time_antbase0[c],time_antbase1[c],'VH'))
                colours.append(RGB)
        ts_plot = time.time()
        if (len(products)):
            plot_time_series(self=datasd,dtype=time_seltypemenu, products=products, colours=colours, end_time=-3600)
        ts_range = time.time()
        if (time_absminx<=0 and time_minx!=''):
            f1a.set_xlim(xmin=double(time_minx))
        elif (time_absminx>0):
            f1a.set_xlim(xmin=double(time_absminx-time_now))
        if (time_absmaxx<=0 and time_maxx!=''):
            f1a.set_xlim(xmax=double(time_maxx))
        elif (time_absmaxx>0):
            f1a.set_xlim(xmax=double(time_absmaxx-time_now))
        if (f1a.xaxis_inverted()):
            xlim=f1a.get_xlim();
            f1a.set_xlim(xlim[::-1])
        if (time_minF!=''):
            f1a.set_ylim(ymin=double(time_minF))
        if (time_maxF!=''):
            f1a.set_ylim(ymax=double(time_maxF))
        if (f1a.yaxis_inverted()):
            ylim=f1a.get_ylim();
            f1a.set_ylim(ylim[::-1])
        ts_draw = time.time()
        f1.canvas.draw()
        ts_end = time.time()
        logger.warning("Timeseries| Init: %.3fs, Loop: %.3fs, Plot: %.3fs, Limits: %.3fs, Draw: %.3fs" % (ts_loop - ts_start, ts_plot - ts_loop, ts_range - ts_plot, ts_draw - ts_range, ts_end-ts_draw))
    except Exception,e:
        print time.asctime()+' Exception in timeseries_draw (%s)'%e

def spectrum_draw():
    try:
        global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend, spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx
        global f2,f2a,f2b,spectrum_width
        f2a.clear()
        if (f2b):
            f2b.clear()
            f2.delaxes(f2b)
            f2b=0;
        products=[]
        colours=[]
        minx=0
        maxx=spectrum_width-1
        for c in range(len(spectrum_antbase0)):
            RGB=[(colourlist_R[spectrum_antbase0[c]]+colourlist_R[spectrum_antbase1[c]])/(255.0+255.0),(colourlist_G[spectrum_antbase0[c]]+colourlist_G[spectrum_antbase1[c]])/(255.0+255.0),(colourlist_B[spectrum_antbase0[c]]+colourlist_B[spectrum_antbase1[c]])/(255.0+255.0) ]
            if (spectrum_corrHH=='true'):
                products.append(antennamap(spectrum_antbase0[c],spectrum_antbase1[c],'HH'))
                colours.append(RGB)
            if (spectrum_corrVV=='true'):
                products.append(antennamap(spectrum_antbase0[c],spectrum_antbase1[c],'VV'))
                colours.append(RGB)
            if (spectrum_corrHV=='true'):
                products.append(antennamap(spectrum_antbase0[c],spectrum_antbase1[c],'HV'))
                colours.append(RGB)
            if (spectrum_corrVH=='true'):
                products.append(antennamap(spectrum_antbase0[c],spectrum_antbase1[c],'VH'))
                colours.append(RGB)
        if (len(products)):
            onlineflags=plot_spectrum(self=datasd,dtype=spectrum_seltypemenu, products=products, colours=colours,start_channel=1,stop_channel=spectrum_width)
        else:
            onlineflags=[]

        if (spectrum_seltypemenux=='channel' or datasd.receiver.center_freqs_mhz==[]):
            if (time_channelphase!=''):
                f2a.axvspan(int(time_channelphase)-0.5,int(time_channelphase)-0.5,0,1,color='g',alpha=0.5)
            for c in range(len(spectrum_flag0)):
                f2a.axvspan(spectrum_flag0[c]-0.5,spectrum_flag1[c]-0.5,0,1,color='r',alpha=0.5)
            for pair in onlineflags:
                f2a.axvspan(pair[0]-0.5,pair[1]-0.5,0,1,color='y',alpha=0.5)

        elif (spectrum_seltypemenux=='mhz'):
            halfchanwidth=abs(datasd.receiver.center_freqs_mhz[0]-datasd.receiver.center_freqs_mhz[1])/2.0
            minx=datasd.receiver.center_freqs_mhz[spectrum_width-1]
            maxx=datasd.receiver.center_freqs_mhz[0]
            if (time_channelphase!=''):
                f2a.axvspan(datasd.receiver.center_freqs_mhz[int(time_channelphase)]-halfchanwidth,datasd.receiver.center_freqs_mhz[int(time_channelphase)]-halfchanwidth,0,1,color='g',alpha=0.5)
            for c in range(len(spectrum_flag0)):
                f2a.axvspan(datasd.receiver.center_freqs_mhz[spectrum_flag0[c]]-halfchanwidth,datasd.receiver.center_freqs_mhz[spectrum_flag1[c]]-halfchanwidth,0,1,color='r',alpha=0.5)
            for pair in onlineflags:
                f2a.axvspan(datasd.receiver.center_freqs_mhz[pair[0]]-halfchanwidth,datasd.receiver.center_freqs_mhz[pair[1]]-halfchanwidth,0,1,color='y',alpha=0.5)
        else:
            halfchanwidth=abs(datasd.receiver.center_freqs_mhz[0]-datasd.receiver.center_freqs_mhz[1])/1000.0/2.0
            minx=datasd.receiver.center_freqs_mhz[spectrum_width-1]/1000.0
            maxx=datasd.receiver.center_freqs_mhz[0]/1000.0
            if (time_channelphase!=''):
                f2a.axvspan(datasd.receiver.center_freqs_mhz[int(time_channelphase)]/1000.0-halfchanwidth,datasd.receiver.center_freqs_mhz[int(time_channelphase)]/1000.0-halfchanwidth,0,1,color='g',alpha=0.5)
            for c in range(len(spectrum_flag0)):
                f2a.axvspan(datasd.receiver.center_freqs_mhz[spectrum_flag0[c]]/1000.0-halfchanwidth,datasd.receiver.center_freqs_mhz[spectrum_flag1[c]]/1000.0-halfchanwidth,0,1,color='r',alpha=0.5)
            for pair in onlineflags:
                f2a.axvspan(datasd.receiver.center_freqs_mhz[pair[0]]/1000.0-halfchanwidth,datasd.receiver.center_freqs_mhz[pair[1]]/1000.0-halfchanwidth,0,1,color='y',alpha=0.5)
        #gdb python; set args ./time_plot.py; run; bt;
    #    matplotlib.pylab.plot(numpy.array(range(10)),sin(numpy.array(range(10)))+2)
    #    matplotlib.pylab.axvline(10,0,1,color='b',alpha=0.5)

        if (spectrum_minx!=''):
            f2a.set_xlim(xmin=double(spectrum_minx))
        else:
            f2a.set_xlim(xmin=minx)
        if (spectrum_maxx!=''):
            f2a.set_xlim(xmax=double(spectrum_maxx))
        else:
            f2a.set_xlim(xmax=maxx)
        if (f2a.xaxis_inverted()):
            xlim=f2a.get_xlim();
            f2a.set_xlim(xlim[::-1])
        if (spectrum_minF!=''):
            f2a.set_ylim(ymin=double(spectrum_minF))
        if (spectrum_maxF!=''):
            f2a.set_ylim(ymax=double(spectrum_maxF))
        if (f2a.yaxis_inverted()):
            ylim=f2a.get_ylim();
            f2a.set_ylim(ylim[::-1])
        f2.canvas.draw()
    except Exception,e:
        print time.asctime()+' Exception in spectrum_draw (%s)'%e

def waterfall_draw():
    try:
        global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
        global f3,f3a,spectrum_width
        f3.clf()
        f3a=f3.add_subplot(111)
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
            plot_waterfall(self=datasd,dtype=waterfall_seltypemenu,product=products[0],start_channel=1,stop_channel=spectrum_width)
        if (waterfall_minF!='' or waterfall_maxF!=''):
            minF=None;
            maxF=None;
            if (waterfall_minF!=''):
                minF=double(waterfall_minF);
            if (waterfall_maxF!=''):
                maxF=double(waterfall_maxF);
            for im in f3a.get_images():
                im.set_clim(minF,maxF)
        if (waterfall_minx!=''):
            f3a.set_xlim(xmin=double(waterfall_minx))
        if (waterfall_maxx!=''):
            f3a.set_xlim(xmax=double(waterfall_maxx))
        if (f3a.xaxis_inverted()):
            xlim=f3a.get_xlim();
            f3a.set_xlim(xlim[::-1])
        if (waterfall_miny!=''):
            f3a.set_ylim(ymin=double(waterfall_miny))
        if (waterfall_maxy!=''):
            f3a.set_ylim(ymax=double(waterfall_maxy))
        if (f3a.yaxis_inverted()):
            ylim=f3a.get_ylim();
            f3a.set_ylim(ylim[::-1])
        f3.canvas.draw()
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
    global dh,datasd,rows,startrow,spectrum_width
    global time_absminx,time_absmaxx,time_now,time_channelphase,antennamappingmode
    global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx, time_timeavg
    global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend, spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx, spectrum_timeinst, spectrum_timeavg
    global spectrum_flagstr,spectrum_flag0,spectrum_flag1,spectrum_flagmask,spectrum_abstimeinst
    global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
    print(time.asctime()+' '+str(args))
    if (args[0]=="settextchannelphase"):
        time_channelphase=args[1]
        if (datafile!='stream'):
            spectrum_draw()
    elif (args[0]=="settimeinstant"):
        xlim=f1a.get_xlim();
        spectrum_abstimeinst=time_now+double(args[1])*(xlim[1]-xlim[0])+xlim[0];
        spectrum_timeinst=time.ctime(spectrum_abstimeinst).split(' ')[-2];
        if (datafile!='stream'):
            spectrum_draw()
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"");
        f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
        f2.canvas.send_cmd(newcontent2)
    elif (args[0]=="setflags"):#eg ..200,32,2..40,3..100,700..800,1000..
        spectrum_flagstr=''
        spectrum_flag0=[]
        spectrum_flag1=[]
        spectrum_flagmask=numpy.ones([spectrum_width])
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
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"");
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
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"");
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
        newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","");
        f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
        f2.canvas.send_cmd(newcontent2)
        f3.canvas.send_cmd(newcontent3)
    elif (args[0]=="setbaseline"):
        time_antbase0=[]
        time_antbase1=[]
        for c in range((len(args)-1)/2):
            time_antbase0.append(int(args[c*2+1]))
            time_antbase1.append(int(args[c*2+2]))
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
    newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);
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
    
def spectrum_event(figno,*args):
    global dh,datasd,rows,startrow,spectrum_width
    global spectrum_abstimeinst,time_channelphase,antennamappingmode;
    global time_antbase0, time_antbase1, time_corrHH, time_corrVV, time_corrHV, time_corrVH, time_legend, time_seltypemenu, time_minF, time_maxF, time_minx, time_maxx, time_timeavg
    global spectrum_antbase0, spectrum_antbase1, spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH, spectrum_legend,spectrum_seltypemenu, spectrum_minF, spectrum_maxF, spectrum_seltypemenux, spectrum_minx, spectrum_maxx, spectrum_timeinst, spectrum_timeavg
    global spectrum_flagstr,spectrum_flag0,spectrum_flag1,spectrum_flagmask
    global waterfall_antbase0, waterfall_antbase1, waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,waterfall_seltypemenu, waterfall_minF, waterfall_maxF, waterfall_seltypemenux, waterfall_minx, waterfall_maxx, waterfall_miny, waterfall_maxy
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
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        f1.canvas.send_cmd(newcontent1)
    elif (args[0]=="setflags"):#eg ..200,32,2..40,3..100,700..800,1000..
        spectrum_flagstr=''
        spectrum_flag0=[]
        spectrum_flag1=[]
        spectrum_flagmask=numpy.ones([spectrum_width])
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
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);
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
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);
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
        newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","");
        f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
        f1.canvas.send_cmd(newcontent1)
        f3.canvas.send_cmd(newcontent3)
    elif (args[0]=="setbaseline"):
        spectrum_antbase0=[]
        spectrum_antbase1=[]
        for c in range((len(args)-1)/2):
            spectrum_antbase0.append(int(args[c*2+1]))
            spectrum_antbase1.append(int(args[c*2+2]))
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
    newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"");
    f2.canvas._custom_content = setloadpage(f2.canvas._custom_content,newcontent2);
    f2.canvas.send_cmd(newcontent2)

def waterfall_event(figno,*args):
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
        newcontent1=makenewcontent(spectrum_flagstr,antennamappingmode,time_antbase0,time_antbase1,time_corrHH,time_corrVV,time_corrHV,time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);
        f1.canvas._custom_content = setloadpage(f1.canvas._custom_content,newcontent1);
        spectrum_antbase0=waterfall_antbase0[:]
        spectrum_antbase1=waterfall_antbase1[:]
        spectrum_corrHH=waterfall_corrHH;
        spectrum_corrVV=waterfall_corrVV;
        spectrum_corrHV=waterfall_corrHV;
        spectrum_corrVH=waterfall_corrVH;
        if (datafile!='stream'):
            spectrum_draw()
        newcontent2=makenewcontent(spectrum_flagstr,antennamappingmode,spectrum_antbase0,spectrum_antbase1,spectrum_corrHH,spectrum_corrVV,spectrum_corrHV,spectrum_corrVH,spectrum_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"")
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
    newcontent3=makenewcontent("none",antennamappingmode,waterfall_antbase0,waterfall_antbase1,waterfall_corrHH,waterfall_corrVV,waterfall_corrHV,waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","");
    f3.canvas._custom_content = setloadpage(f3.canvas._custom_content,newcontent3);
    f3.canvas.send_cmd(newcontent3)

def matrix_event(figno,*args):
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
    f4.canvas.send_cmd("")
    
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
dh=katsdisp.KATData()
if (datafile=='stream'):
    dh.start_spead_receiver(capacity=0.3,store2=True)
    datasd=dh.sd
elif (datafile=='k7simulator'):
    datafile='stream'
    dh.start_direct_spead_receiver(capacity=0.3,store2=True)
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
    spectrum_flagmask=numpy.ones([spectrum_width])
    spectrum_flagstr=''

# show a plot
f1=figure(1)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"time_plot.html")
cc = html_wrap_file.read().replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f1.canvas._custom_content = cc
f1.canvas._user_event = timeseries_event
f1.canvas._user_cmd_ret = user_cmd_ret
f1.canvas._user_event(0,time_corrHH, time_corrVV, time_corrHV, time_corrVH,time_legend,time_seltypemenu,time_minF,time_maxF,"",time_minx,time_maxx,"","","","",time_timeavg,time_channelphase);

f2=figure(2)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"spectrum_plot.html")
cc = html_wrap_file.read().replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f2.canvas._custom_content = cc
f2.canvas._user_event = spectrum_event
f2.canvas._user_cmd_ret = user_cmd_ret
f2.canvas._user_event(1,spectrum_corrHH, spectrum_corrVV, spectrum_corrHV, spectrum_corrVH,time_legend,spectrum_seltypemenu,spectrum_minF,spectrum_maxF,spectrum_seltypemenux,spectrum_minx,spectrum_maxx,"","","",spectrum_timeinst,spectrum_timeavg,"");

f3=figure(3)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"waterfall_plot.html")
cc = html_wrap_file.read().replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f3.canvas._custom_content = cc
f3.canvas._user_event = waterfall_event
f3.canvas._user_cmd_ret = user_cmd_ret
f3.canvas._user_event(2,waterfall_corrHH, waterfall_corrVV, waterfall_corrHV, waterfall_corrVH,"",waterfall_seltypemenu,waterfall_minF,waterfall_maxF,waterfall_seltypemenux,waterfall_minx,waterfall_maxx,"",waterfall_miny,waterfall_maxy,"","","");

f4=figure(4)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"matrix_plot.html")
cc = html_wrap_file.read().replace("<!--antposx-list-->",antposx_html).replace("<!--antposy-list-->",antposy_html).replace("<!--antdisp-list-->",antdisp_html).replace("<!--colour-list-R>",colourlist_R_html).replace("<!--colour-list-G>",colourlist_G_html).replace("<!--colour-list-B>",colourlist_B_html).replace("<!--antennamappingmode-->",str(antennamappingmode)).replace("<!--datafile-->",datafile)
html_wrap_file.close()
f4.canvas._custom_content = cc
f4.canvas._user_event = matrix_event
f4.canvas._user_cmd_ret = user_cmd_ret
f4.canvas._user_event(3);

f5=figure(5)
# setup custom events and html wrapper
html_wrap_file = open(html_directory+"help.html")
cc = html_wrap_file.read().replace("<!--datafile-->",datafile)
html_wrap_file.close()
f5.canvas._custom_content = cc

time_last=time_now
ifailedframe=0
loop_time=0
reissuenotice=0
if (datafile!='stream'):
    show(layout='figure1',open_plot=opts.open_plot)
else:
    show(layout='figure1',block=False,open_plot=opts.open_plot)
    while True:
        #if (datasd.storage.frame_count > 0 and datasd.storage.frame_count % 20 == 0): print_top_100()
        if (datasd.storage.frame_count==0):
            if (reissuenotice==0):
                print 'Please resume capture, and then re-issue metadata'
                reissuenotice=1;
        else:
            reissuenotice=0
            if (datasd.receiver.channels==0):
                #fall through
                a=1
            elif (spectrum_width is None or spectrum_width!=datasd.receiver.channels):
                print time.asctime()+' nchannels change from ',spectrum_width,' to ',datasd.receiver.channels
                spectrum_width=datasd.receiver.channels
                spectrum_flagmask=numpy.ones([spectrum_width])
                spectrum_flagstr=''
            else:
                ts_start = time.time()
                timeseries_draw()
                ts_ts_end = time.time()
                spectrum_draw()
                ts_sp_end = time.time()
                waterfall_draw()
                ts_wf_end = time.time()
                #matrix_draw()
                ts_end = time.time()
                if (time_now==time_last):
                    ifailedframe+=1
                else:
                    ifailedframe=0
                    time_last=time_now
                if (ifailedframe>3):
                    f1.canvas.send_cmd('document.getElementById("healthtext").innerHTML="halted stream";')
                    f2.canvas.send_cmd('document.getElementById("healthtext").innerHTML="halted stream";')
                    f3.canvas.send_cmd('document.getElementById("healthtext").innerHTML="halted stream";')
                    f4.canvas.send_cmd('document.getElementById("healthtext").innerHTML="halted stream";')
                else:
                    f1.canvas.send_cmd('document.getElementById("healthtext").innerHTML="live stream";')
                    f2.canvas.send_cmd('document.getElementById("healthtext").innerHTML="live stream";')
                    f3.canvas.send_cmd('document.getElementById("healthtext").innerHTML="live stream";')
                    f4.canvas.send_cmd('document.getElementById("healthtext").innerHTML="live stream";')
                ts_end2 = time.time()
                logger.warning("Timeseries: %.2fs, Spectrum: %.2fs, Waterfall: %.2fs, Matrix: %.2fs, Total: %.2fs" % (ts_ts_end - ts_start, ts_sp_end - ts_ts_end, ts_wf_end - ts_sp_end, ts_end - ts_wf_end, ts_end2 - ts_start))
                loop_time = time.time() - ts_start
        time.sleep((1 - loop_time) if loop_time <= 1 else 0)
