var username=''

RG_fig[0].xdata=[]
RG_fig[0].version=-1

var datasocket = 0;
var the_lastts = 0;
var local_last_lastts_change = 0;

var time_receive_data_user_cmd=0
var time_receive_user_cmd=0

//COOKIE CODE=============================================
function createCookie(name,value,days) 
{
    if (days) 
    {
		var date = new Date();
		date.setTime(date.getTime()+(days*24*60*60*1000));
		var expires = "; expires="+date.toGMTString();
	}else var expires = "";
	document.cookie = name+"="+value+expires+"; path=/";
}

function readCookie(name) 
{
	var nameEQ = name + "=";
	var ca = document.cookie.split(';');
	for(var i=0;i < ca.length;i++) 
	{
		var c = ca[i];
		while (c.charAt(0)==' ') c = c.substring(1,c.length);
		if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
	}
	return null;
}

function checkCookie()
{
    var sessionusername=sessionStorage.getItem('username');    
	var username=readCookie("username");
    if (sessionusername!=null)//this tab is probably reloaded - reuse username for this page which may be different from official username
    {
		document.getElementById("usrname").innerHTML=sessionusername
		setTimeout(function(){handle_data_user_event("setusername,"+sessionusername)},500)        
    }else
	if (username!=null && username!="") 
	{        
        sessionStorage.setItem('username',username);
		document.getElementById("usrname").innerHTML=username
		setTimeout(function(){handle_data_user_event("setusername,"+username)},500)
	}else 
	{
	  	username=prompt("Please enter your name:","");
	  	if (username!=null && username!="")
	    {
            sessionStorage.setItem('username',username);
	    	createCookie("username",username,365);
			document.getElementById("usrname").innerHTML=username
			setTimeout(function(){handle_data_user_event("setusername,"+username)},500)
	    }
	}
}

function newCookie()
{
		var username=readCookie("username");
	  	username=prompt("Please enter your name:",username);
	  	if (username!=null && username!="")
	    {
            sessionStorage.setItem('username',username);
	    	createCookie("username",username,365);
			document.getElementById("usrname").innerHTML=username
			handle_data_user_event("setusername,"+username)
	    }
}

//MESSAGE LOGGING ===================================

function logconsole(msg,dotimestamp,doshow,doscroll)
{    
    consolectl=document.getElementById("consoletext")
    if (dotimestamp)
    {
        date=(new Date()).toLocaleString();
        consolectl.innerHTML+=date+' '+msg+'\n'
    }else consolectl.innerHTML+=msg+'\n'
    if (doscroll) consolectl.scrollTop = consolectl.scrollHeight;
    if (doshow && consolectl.style.display=='none')
        consolectl.style.display = 'block'
}

//DATA TRANSPORT FUNCTIONS===============================================================		
function loadpage()
{
	start_data();
	checkCookie()	
}

function start_data() 
{
    datasocket = new WebSocket(webdataURL);
	var supports_binary = (datasocket.binaryType != undefined);
	datasocket.binaryType = 'arraybuffer';
	datasocket.onerror = function(e) 
	{
        logconsole('Websocket error occurred',true,false,true)
	}
	datasocket.onmessage = function(e) 
	{
	    if (e.data instanceof ArrayBuffer)
	    {
		    time_receive_data_user_cmd=(new Date()).getTime();
			unpack_binarydata_msg(e.data,time_receive_data_user_cmd/1000.0)
		}else if (e.data.indexOf("/*exec_user_cmd*/") == 0) 
		{
		    time_receive_user_cmd=(new Date()).getTime();
		    exec_data_user_cmd(e.data);
        }
    }
}

function stop_data() 
{
    datasocket.onmessage = function(e) {};
	datasocket.close();
}

function restore_data()
{
 	clearInterval(timerid)
	if (datasocket.readyState==1)
	{
		checkCookie()
		for (ifig=0;ifig<nfigures;ifig++)
		{
	    	RG_fig[ifig].figureupdated=true
			window['RCV_fig'][ifig]=undefined
		}
		timerid=setInterval(updateFigure,1000)
		logconsole('Connection restored',true,false,true)
	}else
	{
		start_data();
		timerid=setTimeout(restore_data,5000)
		logconsole('Attempting to restore connection',true,false,true)
	}
}

function handle_data_user_event(arg_string) 
{
  try {
        if (datasocket.readyState==1)
        {
            datasocket.send(arg_string);
        }else if (datasocket.readyState==3)
        {
            logconsole('Websocket connection closed, trying to reestablish',true,false,true)
			restore_data()
        }else
        {
            logconsole('Websocket state is '+datasocket.readyState+'. Command forfeited: '+arg_string,true,false,true)
			restore_data()
        }
      } catch (err) {}
 } 

 function exec_data_user_cmd(cmd_str) 
 {
     var ret_str = "";
     try 
     {
       	ret_str=eval(cmd_str);
     } catch(err) { ret_str = "user command failed: " + err;}
 }

 //ASSIGNMENT CODE=============================================
 //performs assignment of data to global variable
 function unpack_binarydata_msg(arraybuffer,arrivets)
 {
 	varname='RCV_'
 	offset=0;
 	data = new Uint8Array(arraybuffer)			
 	while(data[offset]){varname+=String.fromCharCode(data[offset++]);}	
 	offset++;
 	dtype=String.fromCharCode(data[offset++]);
 	ndims=data[offset++]
 	dims=new Uint16Array(arraybuffer.slice(offset,offset+ndims*2))
 	offset+=ndims*2
 	for (idim=0,totdata=1;idim<ndims;idim++)totdata*=dims[idim];
 	if (dtype=='s')//assumed one dimensional in this case
 	{
 		val=new Array(totdata)
 		for (idata=0;idata<totdata;idata++)
 		{
 			val[idata]=''
 			while(data[offset]){val[idata]+=String.fromCharCode(data[offset++]);}
 			offset++;
 		}
 	}else if (dtype=='b' || dtype=='B')
 	{
 		val=new Uint8Array(arraybuffer.slice(offset,offset+totdata*1))
 		offset+=totdata*1
 	}else if (dtype=='h' || dtype=='H')
 	{
 		val=new Uint16Array(arraybuffer.slice(offset,offset+totdata*2))
 		offset+=totdata*2
 	}else if (dtype=='i' || dtype=='I')
 	{
 		val=new Uint32Array(arraybuffer.slice(offset,offset+totdata*4))
 		offset+=totdata*4
 	}else if (dtype=='f')
 	{
 		val=new Float32Array(arraybuffer.slice(offset,offset+totdata*4))
 		offset+=totdata*4
 	}else if (dtype=='d')
 	{
 		val=new Float64Array(arraybuffer.slice(offset,offset+totdata*8))
 		offset+=totdata*8
 	}else if (dtype=='m')
 	{
 		vmm=new Float32Array(arraybuffer.slice(offset,offset+2*4))
 		val=new Float32Array(totdata)
 		for(ind=0;ind<totdata;ind++)
 		    val[ind]=ind*(vmm[1]-vmm[0])/(totdata-1)+vmm[0]
 		offset+=2*4
 	}
 	else if (dtype=='M')
 	{
 		vmm=new Float64Array(arraybuffer.slice(offset,offset+2*8))
 		val=new Float64Array(totdata)
 		for(ind=0;ind<totdata;ind++)
 		    val[ind]=ind*(vmm[1]-vmm[0])/(totdata-1)+vmm[0]
 		offset+=2*8
 	}	
 	//seperate decode			
 	if (dtype=='B'||dtype=='H')
 	{
 		val=new Float32Array(val)
 		convertminmax=new Float32Array(arraybuffer.slice(offset,offset+2*4))
 		offset+=2*4
 		if (dtype=='B') scale=(convertminmax[1]-convertminmax[0])/(256.0-4.0)
 		else scale=(convertminmax[1]-convertminmax[0])/(65536.0-4.0)
 		for (idata=0;idata<totdata;idata++)
 		{
 			if (val[idata]==0) val[idata]=-Infinity
 			else if (val[idata]==1) val[idata]=Infinity
 			else if (val[idata]==2) val[idata]=NaN
 			else val[idata]=convertminmax[0]+(val[idata]-3)*scale
 		}
 	}else if (dtype=='I')
 	{
 		val=new Float64Array(val)
 		convertminmax=new Float64Array(arraybuffer.slice(offset,offset+2*8))
 		offset+=2*8
 		scale=(convertminmax[1]-convertminmax[0])/(4294967296.0-4.0)
 		for (idata=0;idata<totdata;idata++)
 		{
 			if (val[idata]==0) val[idata]=-Infinity
 			else if (val[idata]==1) val[idata]=Infinity
 			else if (val[idata]==2) val[idata]=NaN
 			else val[idata]=convertminmax[0]+(val[idata]-3)*scale
 		}				
 	}
 	if (ndims==0)
 	{
 		val=val[0]
 	}else if (ndims>1 && dtype!='s')//perform reshape
 	{
     	entry=[]
     	stateindex=[]
     	varoffset=0
     	for (ilev=0;ilev<ndims;ilev++){entry=[entry];stateindex[ilev]=0;}
     	while(varoffset<totdata)
     	{
     		for (thisentry=entry[0],ilev=0;ilev<ndims-2;ilev++)//ensure array elements exist
     		{
     			if (typeof(thisentry[stateindex[ilev]])=="undefined") thisentry[stateindex[ilev]]=[];
     			thisentry=thisentry[stateindex[ilev]];
     		}
     		thisentry[stateindex[ilev]]=val.subarray(varoffset,varoffset+dims[ndims-1]);//assign data
     		varoffset+=dims[ndims-1];
     		stateindex[ilev]++;//increment state index
     		for (ilev=ndims-2;ilev>=0;ilev--)// and perform carry overs
     			if (stateindex[ilev]>=dims[ilev])
     			{
     				stateindex[ilev]=0;
     			 	if (ilev>0)stateindex[ilev-1]++;
     			}
     	}
     	val=entry[0];
 	}
 	assignvariable(varname,val,arraybuffer.byteLength,arrivets)
 }


 //typical calls would be...
 // figure[ifigure].title='hello'
 // figure[ifigure].legend=['er','re','e']
 // figure[ifigure].ydata[itwin][iline]=linedata
 function assignvariable(varname,val,ntxbytes,arrivets)
 {
 	sublist=[]
 	thisname=''
 	for (ic=0;ic<varname.length;ic++)
 	{
 		if (varname[ic]=='.' || varname[ic]==']' || varname[ic]=='[')
 		{
 			if (thisname.length>0)
 			{						
 				if (varname[ic]==']') sublist[sublist.length]=parseInt(thisname);
 				else sublist[sublist.length]=thisname;
 				thisname='';
 			}
 		}else
 		{
 			thisname+=varname[ic];
 		}
 	}
 	if (thisname.length)sublist[sublist.length]=thisname;
 	theobj=window;
 	lastnamedobj=[]
 	lastnamedobjlev=0
 	for (ilev=0;ilev<sublist.length-1;ilev++)
 	{
 		if (typeof(theobj[sublist[ilev]])=="undefined") theobj[sublist[ilev]]=[];
 		theobj=theobj[sublist[ilev]];
 		if (typeof(sublist[ilev])=="string") 
 		{
 			lastnamedobj=theobj
 			lastnamedobjlev=ilev
 		}
 	}
 	if (sublist[ilev]=='lastts' && Math.abs(the_lastts-val)>0.1)
 	{//the most recent local time that a change in data timestamp is detected
 	    the_lastts=val;
 	    local_last_lastts_change=arrivets
 	}
 	theobj[sublist[ilev]]=val
 	if (sublist[0]!='RCV_fig') return
 	rcvfig=window[sublist[0]][sublist[1]]
    thisfigure=window['RG_fig'][sublist[1]]
 	if (typeof(rcvfig.recvcount)=="undefined")//receiving first variable of a figure
 	{
 	    rcvfig.recvcount=1;
 		rcvfig['receivingts']=arrivets;
 		rcvfig['reqts']=thisfigure['reqts']//steals reqts
 		rcvfig['ntxbytes']=0
     }else//receiving subsequent variables of a figure 
     {
         rcvfig.recvcount++;
         rcvfig['ntxbytes']+=ntxbytes
     }
 	if (typeof(rcvfig.totcount)!="undefined" && rcvfig.totcount<rcvfig.recvcount)
 	{//note that server could possibly still be busy sending an old figure update so future received data may become misaligned even if fresh update requested!
         logconsole('More than expected variables received, reloading figure '+sublist[1],true,false,true)
         thisfigure['version']=-1
         window[sublist[0]][sublist[1]]=undefined
         window['RG_fig'][sublist[1]].figureupdated=true
         return;
 	}
 	if (typeof(rcvfig.totcount)!="undefined" && rcvfig.totcount==rcvfig.recvcount)//received complete figure/figure update
 	{
 		if (window['RCV_fig'][sublist[1]].version>window['RG_fig'][sublist[1]].version)
 			window['RG_fig'][sublist[1]].overridelimit=0
 		if (typeof(window['RG_fig'][sublist[1]].overridelimit)!="undefined" && window['RG_fig'][sublist[1]].overridelimit==1)
 			overridevars={'xmin':0,'xmax':0,'ymin':0,'ymax':0,'cmin':0,'cmax':0}//just use as a list of variable names
 		else overridevars={}
		
 		rcvfig['receivedts']=Date.now()/1000;
 	    if (rcvfig.action=='none')
 	    {
 		    thisfigure.figureupdated=true
 			thisfigure.action='none'
 			thisfigure.receivingts=rcvfig.receivingts
 			thisfigure.receivedts=rcvfig.receivedts
 			thisfigure.ntxbytes=rcvfig.ntxbytes
 			thisfigure.recvcount=rcvfig.recvcount
 			thisfigure.drawstartts=(new Date()).getTime()/1000.0
 			thisfigure.drawstoptts=thisfigure.drawstartts
 		    window['RCV_fig'][sublist[1]]=undefined			
 			completefigure(sublist[1])//RG_fig[sublist[1]].figureupdated=true;set RG_fig[sublist[1]].renderts
 		    return
 	    }else if (rcvfig.action=='reset')
 		{
 		    lastts=thisfigure.lastts//this might be a bug - why not [sublist[1]]
 		    viewwidth=thisfigure.viewwidth
 			overridelimit=thisfigure.overridelimit
 			xmin=thisfigure.xmin
 			xmax=thisfigure.xmax
 			ymin=thisfigure.ymin
 			ymax=thisfigure.ymax
 			cmin=thisfigure.cmin
 			cmax=thisfigure.cmax
 		    window['RG_fig'][sublist[1]]=[]
 		    window['RG_fig'][sublist[1]].viewwidth=viewwidth
 		    window['RG_fig'][sublist[1]].lastts=lastts
 			window['RG_fig'][sublist[1]].overridelimit=overridelimit
 			window['RG_fig'][sublist[1]].xmin=xmin
 			window['RG_fig'][sublist[1]].xmax=xmax
 			window['RG_fig'][sublist[1]].ymin=ymin
 			window['RG_fig'][sublist[1]].ymax=ymax
 			window['RG_fig'][sublist[1]].cmin=cmin
 			window['RG_fig'][sublist[1]].cmax=cmax
 		    for (var thevar in window['RCV_fig'][sublist[1]])
 				if (!(thevar in overridevars))
 					window['RG_fig'][sublist[1]][thevar]=window['RCV_fig'][sublist[1]][thevar]
 		    window['RCV_fig'][sublist[1]]=undefined
 		}else if (rcvfig.action=='set')
 		{
 		    for (var thevar in window['RCV_fig'][sublist[1]])
 				if (!(thevar in overridevars))
 		        	window['RG_fig'][sublist[1]][thevar]=window['RCV_fig'][sublist[1]][thevar]
 		    window['RCV_fig'][sublist[1]]=undefined
 		}else if (rcvfig.action=='augmentydata')
 		{
 		    aug='ydata'
 		    if (typeof(thisfigure[aug])=="undefined")
 		    {
 		        logconsole('Timeseries figure ydata incorrectly shaped, reloading figure '+sublist[1],true,false,true)
                 thisfigure['version']=-1
                 window[sublist[0]][sublist[1]]=undefined//NOTE DEBUG TODO SHOULD PERHAPS set .figureupdated=true here and likewise below to ensure update will occur!!!
     		     window['RG_fig'][sublist[1]].figureupdated=true
                 return;
 		    }
 		    ntwin=thisfigure[aug].length
 			for (itwin=0;itwin<ntwin;itwin++)
 			{
                 if (thisfigure[aug][itwin].length!=rcvfig[aug][itwin].length)
                 {
                     logconsole('Timeseries number lines changed unexpectedly from '+thisfigure[aug][itwin].length+' to '+rcvfig[aug][itwin].length+', reloading figure '+sublist[1],true,false,true)
                     thisfigure['version']=-1
                     window[sublist[0]][sublist[1]]=undefined
         		     window['RG_fig'][sublist[1]].figureupdated=true
                     return;
                 }
     		    misalignment=thisfigure['lastts']-rcvfig['xdata'][rcvfig['xdata'].length-rcvfig[aug][itwin][0].length-1]
                 if (Math.abs(misalignment)>0.1)
                 {
                     logconsole('Timeseries time data misaligned by '+misalignment+ 's; current figure lastts: '+thisfigure['lastts']+'; aug prestart ts: '+(rcvfig['xdata'][rcvfig['xdata'].length-rcvfig[aug][itwin][0].length-1])+'; reloading figure '+sublist[1],true,false,true)
                     for (it=0;it<rcvfig[aug][itwin].length;it++)
                         logconsole(' t['+(it-rcvfig[aug][itwin].length+1)+']='+rcvfig['xdata'][rcvfig['xdata'].length-rcvfig[aug][itwin][0].length+it],true,false,true)

                     thisfigure['version']=-1
                     window[sublist[0]][sublist[1]]=undefined
         		     window['RG_fig'][sublist[1]].figureupdated=true
                     return;
                 }else
 				for (iline=0;iline<thisfigure[aug][itwin].length;iline++)//loops through each line to augment
 				{
 					diff=rcvfig['xdata'].length-thisfigure[aug][itwin][iline].length
 					newvals=rcvfig[aug][itwin][iline]
 					rcvfig[aug][itwin][iline]=[]
 					for (iv=0;iv<rcvfig['xdata'].length-newvals.length;iv++)
 					    rcvfig[aug][itwin][iline][iv]=thisfigure[aug][itwin][iline][iv+newvals.length-diff]
 					for (iv=0;iv<newvals.length;iv++)
 						rcvfig[aug][itwin][iline][rcvfig['xdata'].length-newvals.length+iv]=newvals[iv];
 				}
 			}
 			for (var thevar in window['RCV_fig'][sublist[1]])
 				if (!(thevar in overridevars))
 					window['RG_fig'][sublist[1]][thevar]=window['RCV_fig'][sublist[1]][thevar]
 		    window['RCV_fig'][sublist[1]]=undefined		    
 		}else if (rcvfig.action=='augmentcdata')
 		{
 		    aug='cdata'
 		    if (typeof(thisfigure[aug])=="undefined")
 		    {
 		        logconsole('Waterfall figure cdata incorrectly shaped, reloading figure '+sublist[1],true,false,true)
                 thisfigure['version']=-1
                 window[sublist[0]][sublist[1]]=undefined//NOTE DEBUG TODO SHOULD PERHAPS set .figureupdated=true here and likewise below to ensure update will occur!!!
     		     window['RG_fig'][sublist[1]].figureupdated=true
                 return;
 		    }
 		    misalignment=thisfigure['lastts']-rcvfig['ydata'][rcvfig['ydata'].length-rcvfig[aug].length-1]
             if (Math.abs(misalignment)>0.1)
             {
                 logconsole('Waterfall time data misaligned by '+misalignment+ 's; current figure lastts: '+thisfigure['lastts']+'; aug prestart ts: '+(rcvfig['ydata'][rcvfig['ydata'].length-rcvfig[aug].length-1])+'; reloading figure '+sublist[1],true,false,true)
                 for (it=0;it<rcvfig[aug].length;it++)
                     logconsole(' t['+(it-rcvfig[aug].length+1)+']='+rcvfig['ydata'][rcvfig['ydata'].length-rcvfig[aug].length+it],true,false,true)
                 thisfigure['version']=-1
                 window[sublist[0]][sublist[1]]=undefined
     		     window['RG_fig'][sublist[1]].figureupdated=true
                 return;
             }else
             {
 				diff=rcvfig['ydata'].length-thisfigure[aug].length
 				newvals=rcvfig[aug]
 				rcvfig[aug]=[]
 				for (iv=0;iv<rcvfig['ydata'].length-newvals.length;iv++)
 				    rcvfig[aug][iv]=thisfigure[aug][iv+newvals.length-diff]
 				for (iv=0;iv<newvals.length;iv++)
 					rcvfig[aug][rcvfig['ydata'].length-newvals.length+iv]=newvals[iv];
 			}
 			for (var thevar in window['RCV_fig'][sublist[1]])
 				if (!(thevar in overridevars))
 		        	window['RG_fig'][sublist[1]][thevar]=window['RCV_fig'][sublist[1]][thevar]
 		    window['RCV_fig'][sublist[1]]=undefined				
 		}else//unknown action
 		{
             logconsole('Unknown augment action requested: '+rcvfig.action+'; reloading figure '+sublist[1],true,false,true)
             thisfigure['version']=-1
             window[sublist[0]][sublist[1]]=undefined
 		     window['RG_fig'][sublist[1]].figureupdated=true
             return;
         }
 		//issue draw instruction
 		setTimeout(redrawfigure,1,sublist[1])
 	}
 }
