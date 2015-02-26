var nfigures=0
var nfigcolumns=1
var RG_fig=[[]]

var console_timing='off'
var console_sendfigure='off'
var console_update='off'

var looptimer= null
var looptime=5
var loopusernames=[]


function setsignals(){
    signaltext = document.getElementById("signaltext").value;
    if (signaltext.slice(0,6)=='ncols=')
    {
        ncols=parseInt(signaltext.slice(6))
        if (ncols<1 || ncols>7)
        {
            alert('Number of columns must be between 1 and 7');
        }
        else
        {
            handle_data_user_event('setncols,'+signaltext.slice(6));
        }
    }else if (signaltext=='figureaspect')
    {
        logconsole('figureaspect='+figureaspect,true,true,true)
    }else if (signaltext.slice(0,13)=='figureaspect=')
    {
        figureaspect=parseFloat(signaltext.slice(13))
        ApplyViewLayout(nfigures,nfigcolumns)
    }
    else if (signaltext=='outlierthreshold')
    {
        handle_data_user_event('getoutlierthreshold');
    }else if (signaltext.slice(0,17)=='outlierthreshold=')
	{
		outlierthreshold=parseFloat(signaltext.slice(17))
        if (outlierthreshold<50 || outlierthreshold>100)
        {
            alert('Value for outlierthreshold must be between 50 and 100');
        }
        else
        {
            handle_data_user_event('setoutlierthreshold,'+outlierthreshold);
        }		
	}else if (signaltext=='outliertime')
    {
        handle_data_user_event('getoutliertime');
    }else if (signaltext.slice(0,12)=='outliertime=')
	{
		outliertime=parseFloat(signaltext.slice(12))
        if (outliertime<1 || outliertime>50.0)
        {
            alert('Value for outliertime must be between 1 and 50');
        }
        else
        {
            handle_data_user_event('setoutliertime,'+outliertime);
        }		
	}else if (signaltext=='flags')
    {
        handle_data_user_event('getflags');
    }else if (signaltext.slice(0,6)=='flags=')
    {
        handle_data_user_event('setflags,'+signaltext.slice(6));
    }else if (signaltext=='resetcolours')
    {
        handle_data_user_event('resetcolours');
    }else if (signaltext=='RESTART')
    {
        handle_data_user_event('RESTART');        
    }else if (signaltext=='DROP')
    {
        handle_data_user_event('DROP');        
    }
    else if (signaltext=='flags off')
    {
        handle_data_user_event('showflags,off');
    }
    else if (signaltext=='flags on')
    {
        handle_data_user_event('showflags,on');
    }else if (signaltext=='onlineflags off')
    {
        handle_data_user_event('showonlineflags,off');
    }else if (signaltext=='onlineflags on')
    {
        handle_data_user_event('showonlineflags,on');
    }else if (signaltext=='title off')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showtitle='off'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showtitle,off')
	    }
    }else if (signaltext=='title on')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showtitle='on'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showtitle,on')
	    }
    }else if (signaltext=='legend off')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showlegend='off'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showlegend,off')
	    }
    }else if (signaltext=='legend on')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showlegend='on'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showlegend,on')
	    }
    }else if (signaltext=='xlabel off')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showxlabel='off'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showxlabel,off')
	    }
    }else if (signaltext=='xlabel on')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showxlabel='on'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showxlabel,on')
	    }
    }else if (signaltext=='ylabel off')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showylabel='off'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showylabel,off')
	    }
    }else if (signaltext=='ylabel on')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showylabel='on'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showylabel,on')
	    }
    }else if (signaltext=='labels off')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showxlabel='off'
            RG_fig[ifig].showylabel='off'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showxlabel,off')
    	    handle_data_user_event('setfigparam,'+ifig+',showylabel,off')
	    }
    }else if (signaltext=='labels on')
    {
        for (ifig=0;ifig<nfigures;ifig++)
        {
            RG_fig[ifig].showxlabel='on'
            RG_fig[ifig].showylabel='on'
    	    redrawfigure(ifig)
    	    handle_data_user_event('setfigparam,'+ifig+',showxlabel,on')
    	    handle_data_user_event('setfigparam,'+ifig+',showylabel,on')
	    }
    }else if (signaltext=='swap')
    {
        swapaxes=!swapaxes
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].figtype=='timeseries')
        	    redrawfigure(ifig)
    }
    else if (signaltext.slice(0,5)=='tmin=' || signaltext.slice(0,5)=='tmax=' )
    {
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].figtype=='timeseries')
            {
                if (signaltext.slice(0,5)=='tmin=')
        		    RG_fig[ifig].xmin=parseFloat(signaltext.slice(5))
        		if (signaltext.slice(0,5)=='tmax=')
            	    RG_fig[ifig].xmax=parseFloat(signaltext.slice(5))
        		RG_fig[ifig].overridelimit=1;
        	    redrawfigure(ifig)
                handle_data_user_event('setzoom,'+ifig+','+RG_fig[ifig].xmin+','+RG_fig[ifig].xmax+','+RG_fig[ifig].ymin+','+RG_fig[ifig].ymax+','+RG_fig[ifig].cmin+','+RG_fig[ifig].cmax)
            }
    }
    else if (signaltext.slice(0,5)=='cmin=' || signaltext.slice(0,5)=='cmax=')
    {
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].xtype=='ch' && (RG_fig[ifig].figtype=='spectrum' || RG_fig[ifig].figtype.slice(0,9)=='waterfall'))
            {
                if (signaltext.slice(0,5)=='cmin=')
        		    RG_fig[ifig].xmin=parseFloat(signaltext.slice(5))
        		if (signaltext.slice(0,5)=='cmax=')
            	    RG_fig[ifig].xmax=parseFloat(signaltext.slice(5))
        		RG_fig[ifig].overridelimit=1;
        	    redrawfigure(ifig)
                handle_data_user_event('setzoom,'+ifig+','+RG_fig[ifig].xmin+','+RG_fig[ifig].xmax+','+RG_fig[ifig].ymin+','+RG_fig[ifig].ymax+','+RG_fig[ifig].cmin+','+RG_fig[ifig].cmax)
            }
    }
    else if (signaltext.slice(0,5)=='fmin=' || signaltext.slice(0,5)=='fmax=')
    {
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].xtype=='mhz' && (RG_fig[ifig].figtype=='spectrum' || RG_fig[ifig].figtype.slice(0,9)=='waterfall'))
            {
                if (signaltext.slice(0,5)=='fmin=')
        		    RG_fig[ifig].xmin=parseFloat(signaltext.slice(5))
        		if (signaltext.slice(0,5)=='fmax=')
            	    RG_fig[ifig].xmax=parseFloat(signaltext.slice(5))
        		RG_fig[ifig].overridelimit=1;
        	    redrawfigure(ifig)
                handle_data_user_event('setzoom,'+ifig+','+RG_fig[ifig].xmin+','+RG_fig[ifig].xmax+','+RG_fig[ifig].ymin+','+RG_fig[ifig].ymax+','+RG_fig[ifig].cmin+','+RG_fig[ifig].cmax)
            }
    }
    else if (signaltext.slice(0,5)=='Fmin=' || signaltext.slice(0,5)=='Fmax=')
    {
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].xtype=='ghz' && (RG_fig[ifig].figtype=='spectrum' || RG_fig[ifig].figtype.slice(0,9)=='waterfall'))
            {
                if (signaltext.slice(0,5)=='Fmin=')
        		    RG_fig[ifig].xmin=parseFloat(signaltext.slice(5))
        		if (signaltext.slice(0,5)=='Fmax=')
            	    RG_fig[ifig].xmax=parseFloat(signaltext.slice(5))
        		RG_fig[ifig].overridelimit=1;
        	    redrawfigure(ifig)
                handle_data_user_event('setzoom,'+ifig+','+RG_fig[ifig].xmin+','+RG_fig[ifig].xmax+','+RG_fig[ifig].ymin+','+RG_fig[ifig].ymax+','+RG_fig[ifig].cmin+','+RG_fig[ifig].cmax)
            }
    }
    else if (signaltext.slice(0,5)=='pmin=' || signaltext.slice(0,5)=='pmax=')
    {
        for (ifig=0;ifig<nfigures;ifig++)
            if (RG_fig[ifig].type=='pow')
            {
        		if (RG_fig[ifig].figtype=='timeseries' || RG_fig[ifig].figtype=='spectrum')
        		{
                    if (signaltext.slice(0,5)=='pmin=')
            		    RG_fig[ifig].ymin=parseFloat(signaltext.slice(5))
            		if (signaltext.slice(0,5)=='pmax=')
                	    RG_fig[ifig].ymax=parseFloat(signaltext.slice(5))
    		    }else
    		    {
            		if (signaltext.slice(0,5)=='pmin=')
            		{
            		    RG_fig[ifig].cmin=parseFloat(signaltext.slice(5))
            		}
            		else
            		{
            		    RG_fig[ifig].cmax=parseFloat(signaltext.slice(5))
        		    }
    		    }
        		RG_fig[ifig].overridelimit=1;
        	    redrawfigure(ifig)
                handle_data_user_event('setzoom,'+ifig+','+RG_fig[ifig].xmin+','+RG_fig[ifig].xmax+','+RG_fig[ifig].ymin+','+RG_fig[ifig].ymax+','+RG_fig[ifig].cmin+','+RG_fig[ifig].cmax)
            }
    }
    else if (signaltext=='console on')
    {
        document.getElementById("consoletext").style.display = 'block'
    }else if (signaltext=='console off')
    {
        document.getElementById("consoletext").style.display = 'none'
    }else if (signaltext=='console clear')
    {
        document.getElementById("consoletext").style.display = 'block'
        document.getElementById("consoletext").innerHTML=''
    }else if (signaltext=='users')
    {   
        handle_data_user_event('getusers');
    }else if (signaltext=='inputs')
	{
		handle_data_user_event('inputs');
    }else if (signaltext=='info')
	{
		handle_data_user_event('info');
	}else if (signaltext=='memoryleak')
	{
		handle_data_user_event('memoryleak');
	}else if (signaltext=='restartspead')
	{
		handle_data_user_event('restartspead');
	}else if (signaltext=='timing on')
    {
        document.getElementById("consoletext").style.display = 'block'
        console_timing='on'
    }else if (signaltext=='timing off')
    {
        console_timing='off'
    }else if (signaltext.slice(0,7)=='update ')//note space# nvars, byte
    {
        valid=['off','nvars','byte','mb','kb','status','servertime','receivetime','drawtime','rendertime','action'];
        if (valid.indexOf(signaltext.slice(7)) >= 0)
        {
            document.getElementById("consoletext").style.display = 'block'
            console_update=signaltext.slice(7)
        }
    }
    else if (signaltext=='update nvars')
    {
        document.getElementById("consoletext").style.display = 'block'
        console_update='nvars'
    }else if (signaltext=='update byte' )
    {
        document.getElementById("consoletext").style.display = 'block'
        console_update='byte'
    }else if (signaltext=='update kb' || signaltext=='update kilobyte')
    {
        document.getElementById("consoletext").style.display = 'block'
        console_update='kb'
    }else if (signaltext=='update mb' || signaltext=='update megabyte')
    {
        document.getElementById("consoletext").style.display = 'block'
        console_update='mb'
    }else if (signaltext=='update off')
    {
        console_update='off'
    }else if (signaltext=='sendfigure on')
    {
        document.getElementById("consoletext").style.display = 'block'
        console_sendfigure='on'
    }else if (signaltext=='sendfigure off')
    {
        console_sendfigure='off'
    }else if (signaltext=='server top')
    {
        document.getElementById("consoletext").style.display = 'block'
        handle_data_user_event('server,'+'top -bn 1 | head -20');
    }else if (signaltext=='server ps')
    {
        document.getElementById("consoletext").style.display = 'block'
        handle_data_user_event('server,'+'ps aux | grep time_plot.py');
    }else if (signaltext.slice(0,4)=='save')
    {
        if (signaltext.length>4)
            handle_data_user_event('save,'+signaltext.slice(5));
        else
            handle_data_user_event('save');
    }else if (signaltext.slice(0,4)=='load')
    {
        if (signaltext.length>4)
            handle_data_user_event('load,'+signaltext.slice(5));
        else
            handle_data_user_event('load');
    }else if (signaltext.slice(0,7)=='delete ')
	{
		handle_data_user_event('delete,'+signaltext.slice(7));
	}else if (signaltext.slice(0,4)=='loop')
    {
		if (signaltext=='looptime')
		{
			logconsole('looptime='+looptime,true,true,true)
		}else if (signaltext.slice(0,9)=='looptime=')
        {
			looptime=parseFloat(signaltext.slice(9))
        }else if (signaltext=='loop off')
        {
            clearTimeout(looptimer)
        }else
        {
            newusernames=signaltext.slice(5).split(',')
            if (newusernames.length>1)
            {
	            clearTimeout(looptimer)
				loopusernames=newusernames
                looptimer=setTimeout(loopfunction,looptime*1000.0,loopusernames,0)
            }else
            {
                logconsole('Current loop view profiles: '+loopusernames.join(', '),true,true,true)
            }
        }
    }else if (signaltext.slice(0,4)=='help')
    {
        document.getElementById("consoletext").style.display = 'block'
        handle_data_user_event('help,'+signaltext.slice(5))
    }else if (signaltext=='metadata')//see also restartspead
    { //ssh-keygen -t rsa
      //scp .ssh/id_rsa.pub kat@obs.kat7.karoo
      //ssh kat@obs.kat7.karoo 'cat id_rsa.pub >> .ssh/authorized_keys; rm id_rsa.pub'
      //handle_data_user_event('server,'+'ssh kat@obs.kat7.karoo \"python -c \'import katuilib; k7w=katuilib.build_client(\\\"k7w\\\",\\\"192.168.193.5\\\",2040,controlled=True); k7w.req.add_sdisp_ip(\\\"192.168.193.7\\\"); k7w.req.add_sdisp_ip(\\\"192.168.6.110\\\"); k7w.req.sd_metadata_issue();\'\"');
	  
      //handle_data_user_event('server,'+'ssh kat@obs.kat7.karoo \"python -c \'import katuilib; k7w=katuilib.build_client(\\\"k7w\\\",\\\"192.168.193.5\\\",2040,controlled=True); k7w.req.add_sdisp_ip(\\\"192.168.6.54\\\"); k7w.req.add_sdisp_ip(\\\"192.168.193.7\\\"); k7w.req.add_sdisp_ip(\\\"192.168.6.110\\\"); k7w.req.sd_metadata_issue();\'\"');
      handle_data_user_event('metadata');
      //'ssh kat@obs.kat7.karoo \"python -c \'import socket;rv=socket.gethostbyaddr(\\\"kat-dp2\\\");print rv[2];\'\"'
    }
    else
    handle_data_user_event('setsignals,'+signaltext);
}

function loopfunction(usernames,iusername)
{
    iusername=iusername%usernames.length
    handle_data_user_event('load,'+usernames[iusername]);
    looptimer=setTimeout(loopfunction,looptime*1000.0,usernames,iusername+1)
}

//FIGURE LAYOUT FUNCTIONS================================================================
function ApplyViewLayout(nfig,nfigcols)
{        
    nfigures=nfig
    nfigcolumns=nfigcols
    var listoffigures = document.getElementById("listoffigures")
    var consolectl=document.getElementById("consoletext")
    innerHTML='<table width="100%">'
    RG_fig=[]
    rowcomplete=1;
    consolectl.style.width=window.innerWidth-listoffigures.offsetLeft*2-5
    figwidth=(window.innerWidth-listoffigures.offsetLeft*2)/nfigcols-5
    if (figwidth<200)
    {
        figwidth=200
        figheight=200
    }else
    {
        figheight=figwidth*figureaspect
    }
    for (ifig=0;ifig<nfig;ifig++)
    {
        if (ifig%nfigcols==0)
        {
            innerHTML+="<tr>"
            rowcomplete=0;
        }
        RG_fig[ifig]=[]
        RG_fig[ifig].xdata=[]
        RG_fig[ifig].version=-1
        RG_fig[ifig].viewwidth=parseInt(figwidth)
        RG_fig[ifig].figureupdated=true
        menuname='figmenu'+ifig
        thismenu = { attributes: "attr_ifig,attr_type,attr_xtype,cond" ,

                  items: [
                           {type:RightContext.TYPE_MENU,
                            text:"Power",                          
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],type,pow')} },

                           {type:RightContext.TYPE_MENU,
                            text:"Magnitude",
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],type,mag')} },

                           {type:RightContext.TYPE_MENU,
                            text:"Phase",
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],type,arg')} },

                           {type: RightContext.TYPE_SEPERATOR },

                           {type:RightContext.TYPE_MENU,
                            text:"Channel",
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],xtype,ch')} },

                           {type:RightContext.TYPE_MENU,
                            text:"MHz",
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],xtype,mhz')} },

                           {type:RightContext.TYPE_MENU,
                            text:"GHz",
                            onclick:function() {handle_data_user_event('setfigparam,[attr_ifig],xtype,ghz')} },

                           {type:RightContext.TYPE_MENU,
                            text:"Extra",
                            requires: ["cond", "Y"],
                            onclick:function() {alert('This is a custom javascript')} },

                           {type: RightContext.TYPE_SEPERATOR },
                          
                           {type:RightContext.TYPE_MENU,
                            text:"PNG figure",
                            onclick:function() {saveFigure([attr_ifig]);} },
                            
                           {type:RightContext.TYPE_MENU,
                            text:"Delete figure",
                            onclick:function() {handle_data_user_event('deletefigure,[attr_ifig]')} }
                         ]
                 };
        innerHTML+='<td valign="top"><div id="myfigurediv'+ifig+'" context="'+menuname+'" attr_ifig="'+ifig+'" attr_type="" attr_xtype="" style="z-index: 2; position: relative ; width: '+figwidth+'; height: '+figheight+';">'+
        '<canvas id="myfigurecanvas'+ifig+'"  width="'+figwidth+'" height= "'+figheight+'" style="z-index: 2; position: absolute; left:0; top:0"></canvas>'+
        '<canvas id="myaxiscanvas'+ifig+'"  width="0" height= "0" style="z-index: 1; position: absolute; left:0; top:0"></canvas>'+
        '</div></td>'
        if (ifig%nfigcols==nfigcols-1)
        {
            innerHTML+='</tr>'
            rowcomplete=1;
        }
        RightContext.addMenu(menuname, thismenu);        
    }
    if (rowcomplete==0)
    {
        innerHTML+='</tr>'
        rowcomplete=1;
    }
    innerHTML+='</table>'
    listoffigures.innerHTML=innerHTML
    RightContext.initialize();    
    updateFigure()
}

function updateFigure()
{
    reqts=(new Date()).getTime()/1000.0
	time0=(new Date()).getTime();
	if (timedrawcomplete!=0 && (time0-time_receive_data_user_cmd>10000) && (time0-time_receive_user_cmd>10000))
	{
		document.getElementById("healthtext").innerHTML='server not responding for '+Math.round((time0-time_receive_data_user_cmd)/1000)+'s'
	}
	summary=[]
	for (ifig=0;ifig<nfigures;ifig++)
	{
        if (console_update=='byte')
            summary[ifig]=''+ifig+': '+RG_fig[ifig].ntxbytes
        else if (console_update=='kb')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].ntxbytes/1024).toFixed(2)
        else if (console_update=='mb')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].ntxbytes/1024/1024).toFixed(2)
        else if (console_update=='nvars')
            summary[ifig]=''+ifig+': '+RG_fig[ifig].recvcount
        else if (console_update=='servertime')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].receivingts-RG_fig[ifig].reqts).toFixed(3)
        else if (console_update=='receivetime')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].receivedts-RG_fig[ifig].receivingts).toFixed(3)
        else if (console_update=='drawtime')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].drawstoptts-RG_fig[ifig].drawstartts).toFixed(3)
        else if (console_update=='rendertime')
            summary[ifig]=''+ifig+': '+(RG_fig[ifig].renderts-RG_fig[ifig].drawstoptts).toFixed(3)
        else if (console_update=='action')
            summary[ifig]=''+ifig+': '+RG_fig[ifig].action
        
	    if (RG_fig[ifig].figureupdated)
	    {
	        //var axiscanvas = document.getElementById('myaxiscanvas'+ifig)
		    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
	        RG_fig[ifig].figureupdated=false
	        RG_fig[ifig].reqts=reqts
            oldwidth=RG_fig[ifig].viewwidth
            //if (axiscanvas.width!=0)RG_fig[ifig].viewwidth=axiscanvas.width//else already has value from applyviewlayout
			if (figcanvas.width!=0)RG_fig[ifig].viewwidth=figcanvas.width//else already has value from applyviewlayout
	        if (RG_fig.length==nfigures && RG_fig[ifig].xdata.length && oldwidth==RG_fig[ifig].viewwidth)
	        {
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': Ok'
	            handle_data_user_event("sendfigure,"+ifig+","+RG_fig[ifig].reqts+","+RG_fig[ifig].lastts+","+RG_fig[ifig].version+","+RG_fig[ifig].viewwidth+","+RG_fig[ifig].outlierhash)
	            if (console_sendfigure=='on') logconsole("sendfigure,"+ifig+","+RG_fig[ifig].reqts+","+RG_fig[ifig].lastts+","+RG_fig[ifig].version+","+RG_fig[ifig].viewwidth+","+RG_fig[ifig].outlierhash,true,false,true)
	            //if (console_timing=='on') logconsole('figure '+ifig+": serverlag "+(RG_fig[ifig].receivingts-RG_fig[ifig].reqts).toFixed(3)+", receive "+(RG_fig[ifig].receivedts-RG_fig[ifig].receivingts).toFixed(3)+", draw "+(RG_fig[ifig].drawstoptts-RG_fig[ifig].drawstartts).toFixed(3)+", render "+(RG_fig[ifig].renderts-RG_fig[ifig].drawstoptts).toFixed(3),true,false,true)
            }else 
	        {
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': reloading'
	            handle_data_user_event("sendfigure,"+ifig+","+RG_fig[ifig].reqts+",0,-1"+","+RG_fig[ifig].viewwidth+",0")
            }
        }else
        {
            if (timedrawcomplete!=0 && time0-time_receive_data_user_cmd>10000)
            {
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': waiting for server orig'
				logconsole('No data received from server in '+((time0-time_receive_data_user_cmd)/1000.0).toFixed(0)+'s despite request '+(reqts-RG_fig[ifig].reqts).toFixed(0)+'s ago for figure '+ifig+' reloading page',true,false,true)
				stop_data()
				restore_data()
				return
            }else
            if ((reqts-RG_fig[ifig].receivingts>120) && (time0-time_receive_data_user_cmd)<10000)
            {//assumes 120 seconds is long enough to wait for a page to load all its figures, then starts requesting figures anew
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': waiting for server'
                logconsole('No data received from server for figure '+ifig+' in '+(reqts-RG_fig[ifig].receivingts).toFixed(0)+'s despite request '+(reqts-RG_fig[ifig].reqts).toFixed(0)+'s ago for figure '+ifig,true,false,true)
                RG_fig[ifig].figureupdated=true
            }else if (typeof(RG_fig[ifig].receivingts)=="undefined" && RG_fig[ifig].version>0)//something wrong with the figure, probably due to broken network connection
			{//BEWARE this might never happen!
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': undefined error'
                logconsole('Undefined variables in figure '+ifig+' attempting to restore figure'+ifig,true,false,true)
				//RG_fig[ifig].version=-1//should perhaps try this
                RG_fig[ifig].figureupdated=true
			}else
            {
	            if (console_update=='status')
	                summary[ifig]=''+ifig+': waiting'
            }
        }
    }
    if (console_update=='byte')
        logconsole('byte: '+summary.join(', '),true,false,true)
    if (console_update=='kb')
        logconsole('kb: '+summary.join(', '),true,false,true)
    if (console_update=='mb')
        logconsole('mb: '+summary.join(', '),true,false,true)
    if (console_update=='status')
        logconsole('status: '+summary.join(', '),true,false,true)
    if (console_update=='nvars')
        logconsole('nvars: '+summary.join(', '),true,false,true)
    if (console_update=='servertime')
        logconsole('servertime: '+summary.join(', '),true,false,true)
    if (console_update=='receivetime')
        logconsole('receivetime: '+summary.join(', '),true,false,true)
    if (console_update=='drawtime')
        logconsole('drawtime: '+summary.join(', '),true,false,true)
    if (console_update=='rendertime')
        logconsole('rendertime: '+summary.join(', '),true,false,true)
    if (console_update=='action')
        logconsole('action: '+summary.join(', '),true,false,true)
    
    if (RG_fig.length && typeof(RG_fig[0].lastdt)!="undefined")
    {
        dt2=RG_fig[0].lastdt.toFixed(2)
        
    	if ((reqts-local_last_lastts_change)>(dt2*2+1) && ((time0-time_receive_data_user_cmd)/1000.0) <(dt2) )
    	{//checks that longer than dump local delay occur for change in last timestamp while still having received updates within this time
    	    document.getElementById("healthtext").innerHTML='halted stream'
    	}else
    	{
        	dt1=RG_fig[0].lastdt.toFixed(1)
        	dt0=RG_fig[0].lastdt.toFixed(0)
        	if (Math.abs(dt0-dt2)<0.01)
                document.getElementById("healthtext").innerHTML=''+dt0+'s dumps'
            else if (Math.abs(dt1-dt2)<0.01)
                document.getElementById("healthtext").innerHTML=''+dt1+'s dumps'
            else
                document.getElementById("healthtext").innerHTML=''+dt2+'s dumps'
        }
    }
}

timerid=setInterval(updateFigure,1000)
