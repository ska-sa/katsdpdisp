var username=''
var log10=Math.log(10);
var tickfontHeight=15;
var tickfont2Height=tickfontHeight*0.7;
var tickfont2Heightspace=tickfont2Height/5
var titlefontHeight=20;
var titlefontHeightspace=titlefontHeight/5
var labelfontHeight=18;
var tickfontHeightspace=tickfontHeight/5
var majorticklength=tickfontHeight/3; //4 for 12 pt font
var minorticklength=tickfontHeight/6; //2 for 12 pt font

var nfigures=0
var console_timing='off'
var console_sendfigure='off'
var console_update='off'

var looptimer= null
var looptime=5
var loopusernames=[]
var RG_fig=[[]]
RG_fig[0].xdata=[]
RG_fig[0].version=-1

var timedrawcomplete=0
var datasocket = 0;
var the_lastts = 0;
var local_last_lastts_change = 0;

var time_receive_data_user_cmd=0
var time_receive_user_cmd=0

var corrlinepoly=[0,1,0,0,0,0,0,0]
var corrlinewidth=[2,2,1,1,1,1,1,1]//HH,VV,HV,VH,crossHH,VV,HV,VH
var corrlinealpha=[1,0.25,1,1,1,0.75,0.5,0.25]//HH,VV,HV,VH,crossHH,VV,HV,VH
var corrlinedash=[[0],[3,3],[0],[3,3],[0],[0],[0],[0]]//HH,VV,HV,VH,crossHH,VV,HV,VH
var rubberbandDiv;
var rubberbandmousedown = {}
var rubberbandRectangle = {}
var rubberbanddragging = false;

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
	var username=readCookie("username");
	if (username!=null && username!="") 
	{
		document.getElementById("usrname").innerHTML=username
		setTimeout(function(){handle_data_user_event("setusername,"+username)},500)
	}else 
	{
	  	username=prompt("Please enter your name:","");
	  	if (username!=null && username!="")
	    {
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

//RUBBER-BANDING CODE================================

function rubberbandStart(x, y) 
{
   rubberbandmousedown.x = x;
   rubberbandmousedown.y = y;
   rubberbandRectangle.left = x;
   rubberbandRectangle.top = y;
   moveRubberbandDiv();
   showRubberbandDiv();
   rubberbanddragging = true;
}

function rubberbandStretch(x, y) 
{
   rubberbandRectangle.left = x < rubberbandmousedown.x ? x : rubberbandmousedown.x;
   rubberbandRectangle.top  = y < rubberbandmousedown.y ? y : rubberbandmousedown.y;
   rubberbandRectangle.width  = Math.abs(x - rubberbandmousedown.x),
   rubberbandRectangle.height = Math.abs(y - rubberbandmousedown.y);
   moveRubberbandDiv();
   resizeRubberbandDiv();
}

function rubberbandEnd() 
{
    rubberbandDiv = document.getElementById('rubberbandDiv')
    resetRubberbandRectangle();
	rubberbandDiv.style.width = 0;
	rubberbandDiv.style.height = 0;
	hideRubberbandDiv();
	rubberbanddragging = false;
}

function moveRubberbandDiv() 
{
    rubberbandDiv = document.getElementById('rubberbandDiv')
	rubberbandDiv.style.top  = rubberbandRectangle.top  + 'px';
	rubberbandDiv.style.left = rubberbandRectangle.left + 'px';
}

function resizeRubberbandDiv() 
{
    rubberbandDiv = document.getElementById('rubberbandDiv')
    rubberbandDiv.style.width  = rubberbandRectangle.width  + 'px';
    rubberbandDiv.style.height = rubberbandRectangle.height + 'px';
}

function showRubberbandDiv() 
{
	rubberbandDiv = document.getElementById('rubberbandDiv')
    rubberbandDiv.style.display = 'inline';
}

function hideRubberbandDiv() 
{
    rubberbandDiv = document.getElementById('rubberbandDiv')
	rubberbandDiv.style.display = 'none';
}

function resetRubberbandRectangle() 
{
   rubberbandRectangle = { top: 0, left: 0, width: 0, height: 0 };
}

//FIGURE PLOTTING CODE =================================================

var jetR256=[]
var jetG256=[]
var jetB256=[]
var jetRGB256=[]

function intensityToJet(inten,min,max)
{
	frac=(inten-min)/(max-min);
	if (frac<=0.0)
	{
		return [0,0,127]
	}else if (frac<0.125)
	{
		return [0,0,Math.floor(255.0*(0.5+frac*4.0))]
	}else if (frac<0.375)
	{
		return [0,Math.floor(255.0*(frac-0.125)*4.0),255];
	}else if (frac<0.625)
	{				
		r=Math.floor(255.0*(frac-0.375)*4.0);
		return [r,255,255-r]
	}else if (frac<0.875)
	{
		return [255,Math.floor(255.0*(1.0-(frac-0.625)*4.0)),0]
	}else if (frac<1.0)
	{
		return [Math.floor(255.0*(1.0-(frac-0.875)*4.0)),0,0]
	}else
	{
		return [127,0,0]
	}
}

function makejet()
{
	for (c=0;c<256;c++)
		jetRGB256[c]=intensityToJet(c,0,255)
	jetRGB256[NaN]=[255,255,255]
}

function unitPrefixFromIndex(iprefix,units)
{
 	var g_metricPREFIX="kMGTPEZY"; 
 	var g_metricprefix="mμnpfazy";
	if (iprefix>0)
	{
		if (iprefix<8)	return g_metricPREFIX[(iprefix-1)]+units;
		else			return "10e"+(iprefix*3)+units;
	}else if (iprefix<0)
	{
		if (-iprefix<8)	return g_metricprefix[(-iprefix-1)]+units;
		else			return "10e"+(iprefix*3)+units;
	}
    return units;
}

function calcLinearTicksFrom(biggestValue, scale)
{
    var textwidth=20;
	if (biggestValue)
	{
	    var charwidth=tickfontHeight*0.73*scale;//width of a significant digit in physical space
		var ndecimal=(Math.log(biggestValue/charwidth)/log10);//highest decimal space
		textwidth=tickfontHeight*(3.33+0.73*ndecimal);
	}
	var dtext=scale*textwidth;//approx
	var d0text=Math.pow(10.0,Math.round(Math.log(dtext)/log10));
	var d1text=0.5*d0text;
	var d2text=2.0*d0text;

	var tot=Math.abs(d0text/scale-textwidth);
	var m_nTicksMajor=2;
	var m_TickMinor=d0text/m_nTicksMajor;

	if (tot>Math.abs(d1text/scale-textwidth))
	{
	    tot=Math.abs(d1text/scale-textwidth);m_nTicksMajor=5;m_TickMinor=d1text/m_nTicksMajor;
	}
	if (tot>Math.abs(d2text/scale-textwidth))
	{   
	    m_nTicksMajor=2;m_TickMinor=d2text/m_nTicksMajor;
	}
    return [m_nTicksMajor,m_TickMinor]
}

function roundprecision(val,numsigfig)
{
	if (val==0) return '0'
	if (val<0)
	{
		sgn=1
		aval=-val
	}else
	{
		sgn=0
		aval=val
	}
	expn=(Math.floor(Math.log(aval)/log10))-numsigfig+1
	valstr=''+Math.round(aval*Math.pow(10.0,(-expn)))

	while (expn<0 && valstr.slice(-1)=='0')
	{
		valstr=valstr.slice(0,-1)
		expn+=1
	}
	while (expn>0)
	{
		valstr=valstr+'0'
		expn-=1
	}
	if (expn<0)
	{
		fp=valstr.length+expn
		while (fp<0)
		{
			valstr='0'+valstr
			fp+=1
		}
		if (fp>0) valstr=valstr.slice(0,fp)+'.'+valstr.slice(fp)
		else valstr='0.'+valstr
	}
	if (sgn)
		valstr='-'+valstr+' '
	return valstr
}

//timelabel can be '' to indicate none or of form '12:34:35'
function drawMetricLinearAtPt(context, viewmin, viewmax, pixspan, pixx, pixy, units, label, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix, timelabel)
{
    var physicalspan=viewmax-viewmin;
	var scale=physicalspan/pixspan;
	var maxval=Math.max(Math.abs(viewmax),Math.abs(viewmin));
	if (doprefix)
	 	var iprefix=Math.floor(Math.floor(Math.log(maxval)/log10)/3);
	else 
		var iprefix=0	   
	var multiplier= Math.pow(10,3*iprefix);
	var unitwithprefix=unitPrefixFromIndex(iprefix,units);
	var numberrightmax;
	var timenow=0

	if (timelabel)
	{
		nowtimehh=parseInt(timelabel.slice(-13,-11))
		nowtimemm=parseInt(timelabel.slice(-10,-8))
		nowtimess=parseInt(timelabel.slice(-7,-5))
		timenow=nowtimess+nowtimemm*60+nowtimehh*60*60;
	}
		
	context.font=""+labelfontHeight+"px sans-serif";
	sz=context.measureText(label)
    if (labelpos)	context.fillText(label,pixx+pixspan/2-sz.width/2.0,pixy-((numberpos)?tickfontHeight:0)-((timelabel!='')?tickfont2Height:0)-tickfontHeightspace*2-((dotickpos)?majorticklength:0))
    else context.fillText(label,pixx+pixspan/2-sz.width/2.0,pixy+labelfontHeight+((numberpos==0)?tickfontHeight:0)+((timelabel!='')?tickfont2Height:0)+tickfontHeightspace+((dotickneg)?majorticklength:0))
		
	context.font=""+tickfontHeight+"px sans-serif";
	ticks=calcLinearTicksFrom(maxval,scale);
	m_nTicksMajor=ticks[0]
	m_TickMinor=ticks[1]

	unitsz = context.measureText(unitwithprefix)
	if (doticklabel) context.fillText(unitwithprefix,pixx+pixspan-unitsz.width,pixy+((numberpos)?-majorticklength*dotickpos-tickfontHeightspace:majorticklength*dotickneg+tickfontHeight))
	numberrightmax=unitsz.width;

	var sofar=(-viewmin/(m_TickMinor*m_nTicksMajor));
	sofar=-(Math.ceil(sofar)-sofar)*m_TickMinor*m_nTicksMajor;

	context.beginPath();
	for (i=0;sofar<0;sofar+=m_TickMinor)i++;//pass over the hidden ticks

	for(;sofar<physicalspan;sofar+=m_TickMinor,i++)
	{
	  var x,y;
	  if (roundScreen)
	  {
		x=Math.floor(pixx+sofar/scale)+0.5;
		y=Math.floor(pixy);
	  }else
	  {
		x=pixx+sofar/scale+0.5;
		y=pixy;
	  }
	  if (i%m_nTicksMajor==0)
      {
	     if (dotickmajor)
		 {
			if ((dovertical)==0)
			{
				context.moveTo(x, y-((dotickpos)?majorticklength-roundScreen:0));
				context.lineTo(x, y+((dotickneg)?majorticklength:roundScreen));
			}else
			{
				context.moveTo(x, y-((dotickpos)?majorticklength-roundScreen:0));
				context.lineTo(x, y+((dotickneg)?majorticklength:0));
			}
		 }
		 var val=(sofar+viewmin)/multiplier;
		 var absval=Math.abs(val)
		 if (absval>1e-5) valstr=roundprecision(val,8)
		 else valstr='0'

		 sz=context.measureText(valstr)

		 if (x-sz.width/2.0>pixx-7 && x+sz.width/2.0<pixx+pixspan-numberrightmax)
		 {
		    if (doticklabel)
		    {
			    context.fillText(valstr,x-sz.width/2.0,y+((numberpos)?-majorticklength*dotickpos-tickfontHeightspace:majorticklength*dotickneg+tickfontHeight)) 
			    if (timelabel!='')
			    {					
				    val+=timenow
				    if (val<0)val+=24*60*60
				    hh=Math.floor(val/60/60)
				    mm=Math.floor((val-hh*60*60)/60)
				    ss=Math.floor(val-hh*60*60-mm*60)
				    valstr=''+((hh<10)?'0':'')+hh+':'+((mm<10)?'0':'')+mm+':'+((ss<10)?'0':'')+ss;					
			 	    context.font=""+tickfont2Height+"px sans-serif";				
			 	    sz=context.measureText(valstr)
	                context.fillText(valstr,x-sz.width/2.0,y+((numberpos)?-majorticklength*dotickpos-tickfontHeightspace-tickfontHeight:majorticklength*dotickneg+tickfontHeight+tickfont2Height+tickfont2Heightspace))
	 			    context.font=""+tickfontHeight+"px sans-serif";					
			    }
		    }
		 }
        }else
		{
		    if (dotickminor)
			{
			    if ((dovertical)==0)
				{
					context.moveTo(x, y-((dotickpos)?minorticklength-roundScreen:0));
					context.lineTo(x, y+((dotickneg)?minorticklength:roundScreen));
				}else
				{
					context.moveTo(x, y-((dotickpos)?minorticklength-roundScreen:0));
					context.lineTo(x, y+((dotickneg)?minorticklength:0));
				}
			 }
		 }
	}
	context.stroke();	
	context.closePath();
}

function getminmax(datalist)
{
    if (datalist.length==0) return [NaN,NaN]
	mn=datalist[0][0]
	mx=mn
	if (typeof(mn)=="undefined")//so it is just a vector, not a vector of vector
	{
	    mn=Math.min.apply(Math, datalist)
	    mx=Math.max.apply(Math, datalist)
	    
    	if (!isFinite(mn) || !isFinite(mx))
    	{
    		mn=NaN
    		mx=NaN
			for (iel=0;iel<datalist.length;iel++)
			{
				if (isFinite(datalist[iel]))
				{
					if (!isFinite(mn))
					{
						mn=datalist[iel];
						mx=datalist[iel];
					}else if (mn>datalist[iel])
					{
						mn=datalist[iel];
					}else if (mx<datalist[iel])
					{
						mx=datalist[iel];
					}
				}
			}						
    	}
	    return [mn,mx]
    }
	for (iline=0;iline<datalist.length;iline++)
	{
	    try 
        {
          	thismin=Math.min.apply(Math, datalist[iline])
        } catch(err) 
        { 
            ret_str = "user command failed: " + err;
        }
        
		thismin=Math.min.apply(Math, datalist[iline])
		thismax=Math.max.apply(Math, datalist[iline])
		mn=Math.min(thismin,mn)
		mx=Math.max(thismax,mx)
	}
	if (!isFinite(mn) || !isFinite(mx))
	{
		mn=NaN
		mx=NaN
		for (iline=0;iline<datalist.length;iline++)
		{
			theline=datalist[iline]
			for (iel=0;iel<theline.length;iel++)
			{
				if (isFinite(theline[iel]))
				{
					if (!isFinite(mn))
					{
						mn=theline[iel];
						mx=theline[iel];
					}else if (mn>theline[iel])
					{
						mn=theline[iel];
					}else if (mx<theline[iel])
					{
						mx=theline[iel];
					}
				}
			}						
		}					
	}
	return [mn,mx]
}

function redrawfigure(ifig)
{
    if (typeof(RG_fig[ifig])=="undefined")
        return
    
    RG_fig[ifig].drawstartts=(new Date()).getTime()/1000.0
	setaxiscanvasrect(ifig)
    if (typeof(RG_fig[ifig].xmin)!="number")RG_fig[ifig].xmin=NaN
    if (typeof(RG_fig[ifig].xmax)!="number")RG_fig[ifig].xmax=NaN
    if (typeof(RG_fig[ifig].ymin)!="number")RG_fig[ifig].ymin=NaN
    if (typeof(RG_fig[ifig].ymax)!="number")RG_fig[ifig].ymax=NaN
    if (typeof(RG_fig[ifig].cmin)!="number")RG_fig[ifig].cmin=NaN
    if (typeof(RG_fig[ifig].cmax)!="number")RG_fig[ifig].cmax=NaN
	if (RG_fig[ifig].cdata==undefined)
        drawFigure(ifig,RG_fig[ifig].xdata,RG_fig[ifig].ydata,RG_fig[ifig].color,RG_fig[ifig].xmin,RG_fig[ifig].xmax,RG_fig[ifig].ymin,RG_fig[ifig].ymax,RG_fig[ifig].title,RG_fig[ifig].xlabel,RG_fig[ifig].ylabel,RG_fig[ifig].xunit,RG_fig[ifig].yunit,RG_fig[ifig].legend,RG_fig[ifig].span,RG_fig[ifig].spancolor);
    else
        drawImageFigure(ifig,RG_fig[ifig].xdata,RG_fig[ifig].ydata,RG_fig[ifig].cdata,RG_fig[ifig].color,RG_fig[ifig].xmin,RG_fig[ifig].xmax,RG_fig[ifig].ymin,RG_fig[ifig].ymax,RG_fig[ifig].cmin,RG_fig[ifig].cmax,RG_fig[ifig].title,RG_fig[ifig].xlabel,RG_fig[ifig].ylabel,RG_fig[ifig].clabel,RG_fig[ifig].xunit,RG_fig[ifig].yunit,RG_fig[ifig].cunit,RG_fig[ifig].legend,RG_fig[ifig].span,RG_fig[ifig].spancolor);

	RG_fig[ifig].drawstoptts=(new Date()).getTime()/1000.0
	setTimeout(completefigure,1,ifig)
}

function completefigure(ifig)
{    
	timedrawcomplete=(new Date()).getTime();
	if (typeof(RG_fig[ifig])!="undefined")
	{
		RG_fig[ifig].renderts=timedrawcomplete/1000.0
		RG_fig[ifig].figureupdated=true
		if (console_timing=='on') logconsole('figure '+ifig+": serverlag "+(RG_fig[ifig].receivingts-RG_fig[ifig].reqts).toFixed(3)+", receive "+(RG_fig[ifig].receivedts-RG_fig[ifig].receivingts).toFixed(3)+", draw "+(RG_fig[ifig].drawstoptts-RG_fig[ifig].drawstartts).toFixed(3)+", render "+(RG_fig[ifig].renderts-RG_fig[ifig].drawstoptts).toFixed(3),true,false,true)
	}
}

function drawFigure(ifig,datax,dataylist,clrlist,xmin,xmax,ymin,ymax,title,xlabel,ylabel,xunit,yunit,legend,spanlist,spancolorlist)
{
	if (document.getElementById('myfigurediv'+ifig).style.display=='none' || typeof datax=="undefined" || typeof dataylist=="undefined" || typeof dataylist.length=="undefined"  || typeof(dataylist[0])=="undefined")
	{
		return;
	}
	vviewmin=[]
	vviewmax=[]			
	var localdatax
	if (datax.length==2 && (dataylist[0][0]).length>2)
	{
		localdatax=new Array((dataylist[0][0]).length)
		if ((xunit=='s'))
			for (i=0;i<localdatax.length;i++)
				localdatax[i]=datax[0]-datax[datax.length-1]+(datax[1]-datax[0])*i/(localdatax.length-1)
		else
			for (i=0;i<localdatax.length;i++)
				localdatax[i]=datax[0]+(datax[1]-datax[0])*i/(localdatax.length-1)
	}else
	{
		localdatax=new Array(datax.length)
		if ((xunit=='s'))
			for (i=0;i<localdatax.length;i++)
				localdatax[i]=datax[i]-datax[datax.length-1]
		else
			for (i=0;i<localdatax.length;i++)
				localdatax[i]=datax[i]				
	}
	hviewmin=Math.min(localdatax[0],localdatax[localdatax.length-1])
	hviewmax=Math.max(localdatax[0],localdatax[localdatax.length-1])				
	if (!isNaN(xmin)) hviewmin=xmin
	if (!isNaN(xmax)) hviewmax=xmax
	if (hviewmax==hviewmin)
	{
		hviewmax+=0.5;
		hviewmin-=0.5;
	}
    var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
	axisposx=axiscanvas.offsetLeft
	axisposy=axiscanvas.offsetTop
	var figcontext = figcanvas.getContext('2d');
	if (figcontext)
	{
		figcontext.fillStyle = "#FFFFFF";
		figcontext.clearRect(axisposx, axisposy, axiscanvas.width, axiscanvas.height);
        figcontext.fillRect(0, 0, axisposx, figcanvas.height);
        figcontext.fillRect(axisposx+axiscanvas.width, 0, figcanvas.width-(axisposx+axiscanvas.width), figcanvas.height);
        figcontext.fillRect(0, 0, figcanvas.width, axisposy);
        figcontext.fillRect(0, axisposy+axiscanvas.height, figcanvas.width, figcanvas.height-(axisposy+axiscanvas.height));
		figcontext.fillStyle = "#000000";
	}
	var context = axiscanvas.getContext('2d');
	ixstart=0;ixend=0;
	if (context &&typeof(dataylist[0])!="undefined")
	{
	    oldlinewidth=context.lineWidth
	  	context.fillStyle = "#FFFFFF";
	  	context.fillRect(0, 0, axiscanvas.width, axiscanvas.height);
		context.fillStyle = "#000000";
		xscale=axiscanvas.width/(hviewmax-hviewmin)
		xoff=-hviewmin*xscale;
		for (x=0;x<localdatax.length && (xoff+xscale*localdatax[x])<0;x++);
		if (x>1)ixstart=x-2;else ixstart=0;
		for (x=localdatax.length-1;x>=0 && (xoff+xscale*localdatax[x])>axiscanvas.width;x--);
		if (x<localdatax.length-1)ixend=x+2;else ixend=localdatax.length;
		for (itwin=0;itwin<dataylist.length;itwin++)
		{
			vviewmin[itwin]=-60
			vviewmax[itwin]=20
			minmax=getminmax(dataylist[itwin])
			span=minmax[1]-minmax[0]
			if (!isNaN(ymin)) vviewmin[itwin]=ymin
			else vviewmin[itwin]=minmax[0]-span*0.05
			if (!isNaN(ymax)) vviewmax[itwin]=ymax
			else vviewmax[itwin]=minmax[1]+span*0.05
			if (vviewmax[itwin]==vviewmin[itwin])
			{
				vviewmax[itwin]+=0.5;
				vviewmin[itwin]-=0.5;
			}
		    yscale=axiscanvas.height/(vviewmax[itwin]-vviewmin[itwin])
			yoff=axiscanvas.height+vviewmin[itwin]*yscale
			for (iline=0;iline<dataylist[itwin].length;iline++)
			{
			        context.beginPath();
					if (ixend-ixstart<=1024)
					{
						context.lineWidth=corrlinewidth[clrlist[iline][3]]
						//context.setLineDash(corrlinedash[clrlist[iline][3]])
					}
					// context.strokeStyle = "rgb("+(clrlist[iline][0])+","+(clrlist[iline][1])+","+(clrlist[iline][2])+")";
					if (corrlinepoly[clrlist[iline][3]])
					{
					    context.fillStyle = "rgba("+(clrlist[iline][0])+","+(clrlist[iline][1])+","+(clrlist[iline][2])+","+(corrlinealpha[clrlist[iline][3]])+")";
			    	    context.moveTo(xoff+xscale*localdatax[ixstart],yoff-yscale*dataylist[itwin][iline][ixstart]);
					    for (x=ixstart+1;x<ixend;x++)
					    {
				   		    context.lineTo(xoff+xscale*localdatax[x],yoff-yscale*dataylist[itwin][iline][x]);
					    }
					    iline++;
					    for (x=ixend-1;x>=ixstart;x--)
					    {
				   		    context.lineTo(xoff+xscale*localdatax[x],yoff-yscale*dataylist[itwin][iline][x]);
					    }
					    context.closePath();
					    context.fill()
					}else
					{
					    context.strokeStyle = "rgba("+(clrlist[iline][0])+","+(clrlist[iline][1])+","+(clrlist[iline][2])+","+(corrlinealpha[clrlist[iline][3]])+")";
			    	    context.moveTo(xoff+xscale*localdatax[ixstart],yoff-yscale*dataylist[itwin][iline][ixstart]);
					    for (x=ixstart+1;x<ixend;x++)
					    {
				   		    context.lineTo(xoff+xscale*localdatax[x],yoff-yscale*dataylist[itwin][iline][x]);
					    }
				        context.stroke();
					    context.closePath();
				    }
			}
		}
			context.lineWidth=oldlinewidth;
			//context.setLineDash([0])
			for (ispancolor=0;ispancolor<spancolorlist.length;ispancolor++)
			{
				context.fillStyle='rgba('+spancolorlist[ispancolor][0]+','+spancolorlist[ispancolor][1]+','+spancolorlist[ispancolor][2]+','+spancolorlist[ispancolor][3]/255.0+')'
				for (ispan=0;ispan<spanlist[ispancolor].length;ispan++)							context.fillRect(xoff+xscale*spanlist[ispancolor][ispan][0],0,xscale*(spanlist[ispancolor][ispan][1]-spanlist[ispancolor][ispan][0]),axiscanvas.height)
			}
		}
		if (figcontext)
		{
			figcontext.font=""+titlefontHeight+"px sans-serif";
			figcontext.strokeStyle = "#000000";
			if (RG_fig[ifig].showtitle=='on')
			{
    		 	sz=figcontext.measureText(title)
    		    //fillText by default draws at this height ___ and starts at start of string
    			figcontext.fillText(title,axisposx+axiscanvas.width/2-sz.width/2.0,axisposy/2+(titlefontHeight-titlefontHeightspace)/2)
		    }

			units=xunit
			dovertical=0
			numberpos=0
			labelpos=0
			roundScreen=0
			dotickmajor=1
			dotickminor=1
			dotickpos=0
			dotickneg=1
			doprefix=0
			timelabel=(units=='s')?xlabel:''
			if (RG_fig[ifig].showxlabel!='on') xlabel=''
			if (RG_fig[ifig].showxticklabel!='on') doticklabel=0; else doticklabel=1
				
			drawMetricLinearAtPt(figcontext, hviewmin, hviewmax, axiscanvas.width, axisposx, axisposy+axiscanvas.height, units, xlabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

			figcontext.save();
			figcontext.rotate(-Math.PI/2);

			units=yunit[0]
			dovertical=1
			numberpos=1
			labelpos=1
			dotickpos=1
			dotickneg=0
			doprefix=1
			timelabel=''
			if (RG_fig[ifig].showylabel!='on') ylabel[0]=''
			if (RG_fig[ifig].showyticklabel!='on') doticklabel=0; else doticklabel=1
			
			drawMetricLinearAtPt(figcontext, vviewmin[0], vviewmax[0], axiscanvas.height, -(axisposy+axiscanvas.height),axisposx, units, ylabel[0], dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

			if (ylabel.length>1)//twin axis
			{
				units=yunit[1]
				dovertical=1
				numberpos=0
				labelpos=0
				dotickpos=0
				dotickneg=1
				doprefix=1
				timelabel=''
    			if (RG_fig[ifig].showylabel!='on') ylabel[1]=''
				if (RG_fig[ifig].showyticklabel!='on') doticklabel=0; else doticklabel=1
				
				drawMetricLinearAtPt(figcontext, vviewmin[1], vviewmax[1], axiscanvas.height, -(axisposy+axiscanvas.height),axisposx+axiscanvas.width, units, ylabel[1], dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)
			}
			figcontext.restore();

			if (RG_fig[ifig].showlegend=='on')
			{
    			if (legend.length)
    			{
    			    legendfontHeight=labelfontHeight*0.9
    				figcontext.font=""+legendfontHeight+"px sans-serif";
    				x=axisposx+axiscanvas.width+((ylabel.length>1)?(dotickneg*majorticklength)+((numberpos==0)*tickfontHeight)+(labelpos==0)*legendfontHeight:0)+legendfontHeight/4
    				for (iline=0,y=axisposy+legendfontHeight;iline<legend.length && y<axisposy+axiscanvas.height-legendfontHeight/5;iline++,y+=legendfontHeight)
    				{	
    				    if (corrlinepoly[clrlist[iline][3]])
    				    {
    				        y-=legendfontHeight;
    				        continue;
    				    }
    				    figcontext.beginPath();
    					if (ixend-ixstart<=1024)
    					{
    						figcontext.lineWidth=corrlinewidth[clrlist[iline][3]]
    						//figcontext.setLineDash(corrlinedash[clrlist[iline][3]])
    					}
    					figcontext.strokeStyle = "rgba("+(clrlist[iline][0])+","+(clrlist[iline][1])+","+(clrlist[iline][2])+","+(corrlinealpha[clrlist[iline][3]])+")";
    			    	figcontext.moveTo(x,y-legendfontHeight/2.0+legendfontHeight/5.0);
    				   	figcontext.lineTo(x+legendfontHeight*0.75,y-legendfontHeight/2.0+legendfontHeight/5.0);
    				    figcontext.stroke();
    					figcontext.closePath();
    				    figcontext.strokeStyle = "#000000";
    					figcontext.fillText(legend[iline],x+legendfontHeight*0.75+2,y)
    				}
    				figcontext.lineWidth=1;
    				//figcontext.setLineDash([0])
    			}
		    }
			figcontext.strokeRect(axisposx, axisposy, axiscanvas.width, axiscanvas.height);
		}		
	RG_fig[ifig].xmin_eval=hviewmin;
    RG_fig[ifig].xmax_eval=hviewmax;
    RG_fig[ifig].ymin_eval=vviewmin[0];
    RG_fig[ifig].ymax_eval=vviewmax[0];
}

function drawImageFigure(ifig,datax,datay,dataylist,clrlist,xmin,xmax,ymin,ymax,cmin,cmax,title,xlabel,ylabel,clabel,xunit,yunit,cunit,legend,spanlist,spancolorlist)
{
			if (document.getElementById('myfigurediv'+ifig).style.display=='none' || typeof datax=="undefined" || typeof dataylist=="undefined" || typeof dataylist.length=="undefined" || typeof(dataylist[0])=="undefined")
			{
				return;
			}
			var localdatay			
			if (yunit=='s')
			{
				localdatay=new Array(datay.length)
				for (i=0;i<datay.length;i++)
					localdatay[i]=datay[i]-datay[datay.length-1];
			}else
			{
				localdatay=datay
			}			
			vviewmin=[]
			vviewmax=[]
			lenx=datax.length
			if (datax.length==2 && (dataylist[0]).length>2)
			{
				localdatax=new Array((dataylist[0]).length)
				for (i=0;i<localdatax.length;i++)
					localdatax[i]=datax[0]+(datax[1]-datax[0])*i/(localdatax.length-1)
				datax=localdatax;
			}
			dataxmin=Math.min(datax[0],datax[datax.length-1])
			hviewmin=dataxmin
			dataxmax=Math.max(datax[0],datax[datax.length-1])
			hviewmax=dataxmax
			if (!isNaN(xmin)) hviewmin=xmin
			if (!isNaN(xmax)) hviewmax=xmax
			if (hviewmax==hviewmin)
			{
				hviewmax+=0.5;
				hviewmin-=0.5;
			}
			dataymin=Math.min(localdatay[0],localdatay[localdatay.length-1])
			vviewmin=dataymin
			dataymax=Math.max(localdatay[0],localdatay[localdatay.length-1])
			vviewmax=dataymax
			if (!isNaN(ymin)) vviewmin=ymin
			if (!isNaN(ymax)) vviewmax=ymax
			if (vviewmax==vviewmin)
			{
				vviewmax+=0.5;
				vviewmin-=0.5;
			}
		  var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
		  var figcanvas = document.getElementById('myfigurecanvas'+ifig);
		  axisposx=axiscanvas.offsetLeft
		  axisposy=axiscanvas.offsetTop
		  var figcontext = figcanvas.getContext('2d');
		  if (figcontext){
		  			figcontext.fillStyle = "#FFFFFF";
		  			figcontext.clearRect(axisposx, axisposy, axiscanvas.width, axiscanvas.height);
                    figcontext.fillRect(0, 0, axisposx, figcanvas.height);
                    figcontext.fillRect(axisposx+axiscanvas.width, 0, figcanvas.width-(axisposx+axiscanvas.width), figcanvas.height);
                    figcontext.fillRect(0, 0, figcanvas.width, axisposy);
                    figcontext.fillRect(0, axisposy+axiscanvas.height, figcanvas.width, figcanvas.height-(axisposy+axiscanvas.height));
		  			figcontext.fillStyle = "#000000";
		  }
		   var context = axiscanvas.getContext('2d');
			ixstart=0;ixend=0;
			if (context){
				oldlinewidth=context.lineWidth
                context.fillStyle = "#FFFFFF";
                context.fillRect(0, 0, axiscanvas.width, axiscanvas.height);
				context.fillStyle = "#000000";
				xscale=axiscanvas.width/(hviewmax-hviewmin)
				xoff=-hviewmin*xscale;
					cviewmin=-60
					cviewmax=20
					minmax=getminmax(dataylist)
					if (!isNaN(cmin)) cviewmin=cmin
					else cviewmin=minmax[0]
					if (!isNaN(cmax)) cviewmax=cmax
					else cviewmax=minmax[1]
					if (cviewmax==cviewmin)
					{
						cviewmax+=0.5;
						cviewmin-=0.5;
					}
					cscale=255.0/(cviewmax-cviewmin)
					
					var imgdata = context.getImageData(0,0,axiscanvas.width,axiscanvas.height);
			        var imgdatalen = imgdata.data.length;
					rowscale=(dataylist.length)/(dataymax-dataymin)
					colscale=(dataylist[0].length)/(dataxmax-dataxmin)

					if (xunit=='')
			        for(var i=0;i<imgdatalen-4;i+=4)
			        {
//				        imgdata.data[i+3] = 255;//A			    
						ih=(i/4)/axiscanvas.width
						iw=(i/4)%axiscanvas.width
						irow=Math.floor((((axiscanvas.height-ih-1)/axiscanvas.height)*(vviewmax-vviewmin)+vviewmin-dataymin)*rowscale)
						if (irow>=0 && irow<dataylist.length)
						{
							icol=Math.floor(((iw/axiscanvas.width)*(hviewmax-hviewmin)+hviewmin-dataxmin)*colscale)
							if (icol>=0 && icol<dataylist[irow].length)
							{
								c256=Math.floor((dataylist[irow][icol]-cviewmin)*cscale);
								if (c256<0)c256=0
								else if (c256>255)c256=255
								imgdata.data.set(jetRGB256[c256],i)
                                //RGB=jetRGB256[c256]
                                //imgdata.data[i] = RGB[0];//R
                                //imgdata.data[i+1] = RGB[1];//G
                                //imgdata.data[i+2] = RGB[2];//B
							}
						}
			        }//for
					else
					for(var i=0;i<imgdatalen-4;i+=4)
			        {
//				        imgdata.data[i+3] = 255;//A			    
						ih=(i/4)/axiscanvas.width
						iw=(i/4)%axiscanvas.width
						irow=Math.floor((((axiscanvas.height-ih-1)/axiscanvas.height)*(vviewmax-vviewmin)+vviewmin-dataymin)*rowscale)
						if (irow>=0 && irow<dataylist.length)
						{
							icol=Math.floor(((iw/axiscanvas.width)*(hviewmax-hviewmin)+hviewmin-dataxmin)*colscale)
							if (icol>=0 && icol<dataylist[irow].length)
							{
								icol=dataylist[irow].length-icol-1
								c256=Math.floor((dataylist[irow][icol]-cviewmin)*cscale);
								if (c256<0)c256=0
								else if (c256>255)c256=255
								imgdata.data.set(jetRGB256[c256],i)
                                //RGB=jetRGB256[c256]
                                //imgdata.data[i] = RGB[0];//R
                                //imgdata.data[i+1] = RGB[1];//G
                                //imgdata.data[i+2] = RGB[2];//B
							}
						}
			        }
			
					context.putImageData(imgdata,0,0);
				
			}
			if (figcontext){
				figcontext.font=""+titlefontHeight+"px sans-serif";
				figcontext.strokeStyle = "#000000";
				
				if (RG_fig[ifig].showtitle=='on')
				{
			 	    sz=figcontext.measureText(title)
			        //fillText by default draws at this height ___ and starts at start of string
				    figcontext.fillText(title,axisposx+axiscanvas.width/2-sz.width/2.0,axisposy/2+(titlefontHeight-titlefontHeightspace)/2)
				}

				units=xunit
				dovertical=0
				numberpos=0
				labelpos=0
				roundScreen=0
				dotickmajor=1
				dotickminor=1
				dotickpos=0
				dotickneg=1
				doprefix=0
				timelabel=''
			  	displaxisx={viewmin:hviewmin,viewmax:hviewmax,pixspan:axiscanvas.width};
				if (RG_fig[ifig].showxlabel!='on') xlabel=''
				if (RG_fig[ifig].showxticklabel!='on') doticklabel=0; else doticklabel=1
				
				drawMetricLinearAtPt(figcontext, hviewmin, hviewmax, axiscanvas.width, axisposx, axisposy+axiscanvas.height, units, xlabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

				figcontext.save();
			 	figcontext.rotate(-Math.PI/2);

				units=yunit
				dovertical=1
				numberpos=1
				labelpos=1
				dotickpos=1
				dotickneg=0
				doprefix=0
				timelabel=(units=='s')?ylabel:''
				displaxisy={viewmin:vviewmin,viewmax:vviewmax,pixspan:axiscanvas.height};
				if (RG_fig[ifig].showylabel!='on') ylabel=''
			  	if (RG_fig[ifig].showyticklabel!='on') doticklabel=0; else doticklabel=1
			  	
				drawMetricLinearAtPt(figcontext, vviewmin, vviewmax, axiscanvas.height, -(axisposy+axiscanvas.height),axisposx, units, ylabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

                if (RG_fig[ifig].showlegend=='on')
                {
    				units=cunit
    				dovertical=1
    				numberpos=0
    				labelpos=0
    				dotickpos=0
    				dotickneg=1
    				doprefix=1
    				doticklabel=1
        			timelabel=(units=='s')?clabel:''
    				displaxisc={viewmin:cviewmin,viewmax:cviewmax,pixspan:axiscanvas.height};
    				colorbaroff=titlefontHeightspace*2;
    				colorbarwidth=titlefontHeight;

    				drawMetricLinearAtPt(figcontext, cviewmin, cviewmax, axiscanvas.height, -(axisposy+axiscanvas.height),colorbaroff+colorbarwidth+axisposx+axiscanvas.width, units, clabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)
                }
				figcontext.restore();

				figcontext.strokeRect(axisposx, axisposy, axiscanvas.width, axiscanvas.height);
				//draw colorbar
				if (RG_fig[ifig].showlegend=='on')
				{
    				var imgdata = figcontext.getImageData(axisposx+axiscanvas.width+colorbaroff, axisposy, colorbarwidth, axiscanvas.height);
    		        var imgdatalen = imgdata.data.length;

    		        for(var i=0;i<imgdatalen-4;i+=4)
    		        {
    					ih=(i/4)/colorbarwidth;//height
    					c256=Math.floor(((axiscanvas.height-ih)/axiscanvas.height)*255)
    					if (c256<0)c256=0
    					else if (c256>255)c256=255
    					imgdata.data.set(jetRGB256[c256],i)
    					//RGB=jetRGB256[c256]
                        //imgdata.data[i] = RGB[0];//R
                        //imgdata.data[i+1] = RGB[1];//G
                        //imgdata.data[i+2] = RGB[2];//B
                        //imgdata.data[i+3] = 255;//A
    				}
    				figcontext.putImageData(imgdata,axisposx+axiscanvas.width+colorbaroff, axisposy);
    				figcontext.strokeRect(axisposx+axiscanvas.width+colorbaroff, axisposy, colorbarwidth, axiscanvas.height);
			    }
				
		}
    	RG_fig[ifig].xmin_eval=hviewmin;
        RG_fig[ifig].xmax_eval=hviewmax;
        RG_fig[ifig].ymin_eval=vviewmin;
        RG_fig[ifig].ymax_eval=vviewmax;
}

//FIGURE MOUSE EVENTS ===================================================================
var figdragmode=0
var figdragstart=[0,0]
var figdragstartevent=0
var figdragsizestart=[0,0]
var mouseclick=0
var ifigure=0

function onFigureMouseDown(event){
    RightContext.killMenu();
    for (ifigure=0;ifigure<nfigures;ifigure++)
    {
        var figdiv = document.getElementById("myfigurediv"+ifigure);
	    x=event.pageX-figdiv.offsetLeft
	    y=event.pageY-figdiv.offsetTop
	    if (x>0 && x<figdiv.offsetWidth && y>0 && y<figdiv.offsetHeight)
	        break
    }
    if (ifigure==nfigures)
        ifigure=0
    if (event.button==2 || event.which==3 || event.ctrlKey)//right clicked
    {
	    event.preventDefault();
        return
    }
	
	var figurediv = document.getElementById("myfigurediv"+ifigure);
	var canvas = document.getElementById("myfigurecanvas"+ifigure);
	var axiscanvas = document.getElementById("myaxiscanvas"+ifigure);
	if ((Math.abs(event.layerX-(axiscanvas.offsetLeft+axiscanvas.width))<tickfontHeight && Math.abs(event.layerY-(axiscanvas.offsetTop+axiscanvas.height))<tickfontHeight))
	{
		figdragmode=1;
		figdragstart=[event.clientX+document.body.scrollLeft,event.clientY+document.body.scrollTop]
		figdragstartevent=event
		figdragsizestart=[canvas.width,canvas.height]
        if (window.addEventListener) 
        {  // all browsers except IE before version 9
            window.addEventListener ("mousemove", onFigureMouseMove, true);
            window.addEventListener ("mouseup", onFigureMouseUp, true);
        }else 
        {
            if (figurediv.setCapture) 
            {    // IE before version 9
                figurediv.setCapture ();
            }
        }					
	}else if (event.layerX>axiscanvas.offsetLeft && event.layerX<axiscanvas.offsetLeft+axiscanvas.width && event.layerY>axiscanvas.offsetTop && event.layerY<axiscanvas.offsetTop+axiscanvas.height)
	{					
		if (mouseclick!=0 && mouseclick[0]==event.layerX-axiscanvas.offsetLeft && mouseclick[1]==event.layerY-axiscanvas.offsetTop)
		{//detect own double click - at some point doubleclick did not fire
			//onFigureDblclick(event);
		}else
		{
		figdragmode=2;
		figdragstart=[event.clientX,event.clientY]
		figdragstartevent=event
		figdragsizestart=[canvas.width,canvas.height]
        if (window.addEventListener) 
        {  // all browsers except IE before version 9
            window.addEventListener ("mousemove", onFigureMouseMove, true);
            window.addEventListener ("mouseup", onFigureMouseUp, true);
        }else 
        {
            if (figurediv.setCapture) 
            {    // IE before version 9
                figurediv.setCapture ();
            }
        }
		var x = event.clientX+document.body.scrollLeft;
		var y = event.clientY+document.body.scrollTop;

		rubberbandStart(x, y);
		}

	}
	event.preventDefault();
}
function onFigureLoseCapture(event){
	
    rubberbandEnd();
	event.preventDefault();
}

//given dimensions of figure canvas, calc axis canvas position and dimensions
function setaxiscanvasrect(ifig)
{
    var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
    if (ifig==-1)
    {
        _left=50;_top=55;_width=figcanvas.width-130;_height=figcanvas.height-130;
    }else
    {
        if (RG_fig[ifig].showyticklabel=='on')
            _left=30
        else
            _left=0
        if (RG_fig[ifig].showylabel=='on')
            _left+=20
        else
            _left+=3
        if (RG_fig[ifig].showtitle=='on')
            _top=50
        else
            _top=7
        if (RG_fig[ifig].showlegend=='on')
        	_width=figcanvas.width-80-_left
        else
        	_width=figcanvas.width-7-_left
        if (RG_fig[ifig].showxlabel=='on')
        	_height=figcanvas.height-55-_top;
        else
        	_height=figcanvas.height-33-_top
        if (RG_fig[ifig].showxticklabel=='on')
            _height-=0
        else
            _height+=30
	}
	if (axiscanvas.style.left!=_left)
        axiscanvas.style.left = _left + 'px';
	if (axiscanvas.style.top!=_top)
        axiscanvas.style.top = _top + 'px';
    if (axiscanvas.width!=_width)
    {
        axiscanvas.style.width = _width + 'px';
        axiscanvas.width=_width;
    }
    if (axiscanvas.height!=_height)
    {
        axiscanvas.style.height = _height + 'px';
        axiscanvas.height=_height;
    }
    //return {'left':_left,'top':_top,'width':_width,'height':_height}
}

function onFigureMouseUp(event){
	var figurediv = document.getElementById("myfigurediv"+ifigure);
	var canvas = document.getElementById("myfigurecanvas"+ifigure);
	var axiscanvas = document.getElementById("myaxiscanvas"+ifigure);
	if (figdragmode==1)//resize figure
	{
		newsizex=event.clientX+document.body.scrollLeft-figdragstart[0]+figdragsizestart[0]
		newsizey=event.clientY+document.body.scrollTop-figdragstart[1]+figdragsizestart[1]
		// newsizex=event.clientX-figdragstart[0]+figurediv.offsetWidth
		// newsizey=event.clientY-figdragstart[1]+figurediv.offsetHeight
		if (newsizex<300)newsizex=300;
		if (newsizey<300)newsizey=300;
        figurediv.style.width = newsizex + 'px';
        figurediv.style.height = newsizey + 'px';
		figurediv.offsetWidth=newsizex
		figurediv.offsetHeight=newsizey
        canvas.style.width = newsizex + 'px';
        canvas.style.height = newsizey + 'px';
		canvas.width=newsizex;
		canvas.height=newsizey;
		document.body.style.cursor = 'default';
		redrawfigure(ifigure)
		figdragmode=0;
        if (window.removeEventListener) 
        {   // all browsers except IE before version 9
            window.removeEventListener ("mousemove", onFigureMouseMove, true);
            window.removeEventListener ("mouseup", onFigureMouseUp, true);
        }else 
        {
            if (figurediv.releaseCapture) 
            {    // IE before version 9
                figurediv.releaseCapture ();
            }
        }
	}else if (figdragmode==2)//zoom figure
	{	
		pixx0=event.clientX+document.body.scrollLeft-axiscanvas.offsetLeft-figurediv.offsetLeft
		pixy0=axiscanvas.height-(event.clientY+document.body.scrollTop-axiscanvas.offsetTop-figurediv.offsetTop)
		pixx1=figdragstartevent.layerX-axiscanvas.offsetLeft
		pixy1=axiscanvas.height-(figdragstartevent.layerY-axiscanvas.offsetTop)
	
    	figx0=(pixx0)/axiscanvas.width*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
    	figy0=(pixy0)/axiscanvas.height*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;
    	figx1=(pixx1)/axiscanvas.width*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
    	figy1=(pixy1)/axiscanvas.height*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;

		if (Math.abs(figx0-figx1)>0 && Math.abs(figy0-figy1)>0)
		{
			RG_fig[ifigure].xmin=Math.min(figx0,figx1)
			RG_fig[ifigure].xmax=Math.max(figx0,figx1)
			RG_fig[ifigure].ymin=Math.min(figy0,figy1)
			RG_fig[ifigure].ymax=Math.max(figy0,figy1)
			RG_fig[ifigure].overridelimit=1;
		    redrawfigure(ifigure)
		    handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
		    mouseclick=0;
		}else
		{
			mouseclick=[pixx0,axiscanvas.height-pixy0];
		}
		
		figdragmode=0;
        if (window.removeEventListener) 
        {   // all browsers except IE before version 9
            window.removeEventListener ("mousemove", onFigureMouseMove, true);
            window.removeEventListener ("mouseup", onFigureMouseUp, true);
        }else 
        {
            if (figurediv.releaseCapture) 
            {    // IE before version 9
                figurediv.releaseCapture ();
            }
        }

	    rubberbandEnd();
	}
    event.preventDefault();
}

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
    }else if (signaltext=='outlierthreshold')
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
    }else if (signaltext=='flags off')
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
    }else if (signaltext.slice(0,5)=='tmin=' || signaltext.slice(0,5)=='tmax=' )
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
	}else if (signaltext=='restartspead')
	{
		handle_data_user_event('restartspead');
		setTimeout(function(){handle_data_user_event('server,'+'ssh kat@kat-ops.karoo \"python -c \'import katuilib; k7w=katuilib.build_client(\\\"k7w\\\",\\\"192.168.193.5\\\",2040,controlled=True); k7w.req.add_sdisp_ip(\\\"192.168.6.54\\\"); k7w.req.add_sdisp_ip(\\\"192.168.193.7\\\"); k7w.req.add_sdisp_ip(\\\"192.168.6.110\\\"); k7w.req.sd_metadata_issue();\'\"')},1000)
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
        handle_data_user_event('server,'+'top -bd1n2 | grep time_plot.py | tail -n 2');
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
      //scp .ssh/id_rsa.pub kat@kat-ops.karoo
      //ssh kat@kat-ops.karoo 'cat id_rsa.pub >> .ssh/authorized_keys; rm id_rsa.pub'
      //handle_data_user_event('server,'+'ssh kat@kat-ops.karoo \"python -c \'import katuilib; k7w=katuilib.build_client(\\\"k7w\\\",\\\"192.168.193.5\\\",2040,controlled=True); k7w.req.add_sdisp_ip(\\\"192.168.193.7\\\"); k7w.req.add_sdisp_ip(\\\"192.168.6.110\\\"); k7w.req.sd_metadata_issue();\'\"');
	  
      handle_data_user_event('server,'+'ssh kat@kat-ops.karoo \"python -c \'import katuilib; k7w=katuilib.build_client(\\\"k7w\\\",\\\"192.168.193.5\\\",2040,controlled=True); k7w.req.add_sdisp_ip(\\\"192.168.6.54\\\"); k7w.req.add_sdisp_ip(\\\"192.168.193.7\\\"); k7w.req.add_sdisp_ip(\\\"192.168.6.110\\\"); k7w.req.sd_metadata_issue();\'\"');
      //'ssh kat@kat-ops.karoo \"python -c \'import socket;rv=socket.gethostbyaddr(\\\"kat-dp2\\\");print rv[2];\'\"'
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

function onFigureKeyUp(event){
	event = event || window.event
	if (event.keyCode == 27)
	{
		document.getElementById("consoletext").style.display = 'none'
		event.cancelBubble = true;				
		return false;
	}
}

function onFigureDblclick(event){
	var axiscanvas = document.getElementById("myaxiscanvas"+ifigure);
	if (event.layerX>axiscanvas.offsetLeft && event.layerX<axiscanvas.offsetLeft+axiscanvas.width && event.layerY>axiscanvas.offsetTop && event.layerY<axiscanvas.offsetTop+axiscanvas.height)
	{//double click in central plot area - unzoom all	
		RG_fig[ifigure].xmin=NaN
		RG_fig[ifigure].xmax=NaN
		RG_fig[ifigure].ymin=NaN
		RG_fig[ifigure].ymax=NaN
		RG_fig[ifigure].overridelimit=1;
	    redrawfigure(ifigure)
	    handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
        // handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax)
	}else if (event.layerX>axiscanvas.offsetLeft && event.layerX<axiscanvas.offsetLeft+axiscanvas.width && event.layerY>axiscanvas.offsetTop+axiscanvas.height && event.layerY<axiscanvas.offsetTop+axiscanvas.height+majorticklength+tickfontHeight+tickfont2Height+tickfont2Heightspace)
	{
		RG_fig[ifigure].xmin=NaN
		RG_fig[ifigure].xmax=NaN
		RG_fig[ifigure].overridelimit=1;
	    redrawfigure(ifigure)
	    handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
        // handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax)
	}	else if (event.layerX>axiscanvas.offsetLeft-(majorticklength+tickfontHeight) && event.layerX<axiscanvas.offsetLeft && event.layerY>axiscanvas.offsetTop && event.layerY<axiscanvas.offsetTop+axiscanvas.height)
		{
			RG_fig[ifigure].ymin=NaN
			RG_fig[ifigure].ymax=NaN
			RG_fig[ifigure].overridelimit=1;
		    redrawfigure(ifigure)
		    handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
            // handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax)
		}
         event.preventDefault();
        // return false
}

function onFigureMouseMove(event){
    if (figdragmode==0)
    {
        for (tempifigure=0;tempifigure<nfigures;tempifigure++)
        {
            var figdiv = document.getElementById("myfigurediv"+tempifigure);
    	    x=event.pageX-figdiv.offsetLeft
    	    y=event.pageY-figdiv.offsetTop
    	    if (x>0 && x<figdiv.offsetWidth && y>0 && y<figdiv.offsetHeight)
    	        break
        }
        if (tempifigure==nfigures)
            tempifigure=0        
    }else
    {
        tempifigure=ifigure;
    }
	var figurediv = document.getElementById("myfigurediv"+tempifigure);
	var canvas = document.getElementById("myfigurecanvas"+tempifigure);
	var axiscanvas = document.getElementById("myaxiscanvas"+tempifigure);
	mouseclick=0;
	if (figdragmode==2)
	{
		var x = event.clientX+document.body.scrollLeft;
		var y = event.clientY+document.body.scrollTop;
		event.preventDefault();
		if (rubberbanddragging) 
		{
		     rubberbandStretch(x, y);
		}
		document.body.style.cursor = 'crosshair';
	}else
	if (figdragmode==1)
	{
		if (1)
		{
    		newsizex=event.clientX+document.body.scrollLeft-figdragstart[0]+figdragsizestart[0]
    		newsizey=event.clientY+document.body.scrollTop-figdragstart[1]+figdragsizestart[1]
    		if (newsizex<200)newsizex=200;
    		if (newsizey<200)newsizey=200;
            figurediv.style.width = newsizex + 'px';
            figurediv.style.height = newsizey + 'px';
    		figurediv.offsetWidth=newsizex
    		figurediv.offsetHeight=newsizey
            canvas.style.width = newsizex + 'px';
            canvas.style.height = newsizey + 'px';
    		canvas.width=newsizex;
    		canvas.height=newsizey;
    		redrawfigure(ifigure)
    	}
		document.body.style.cursor = 'se-resize';
	}else if ((Math.abs(event.layerX-(axiscanvas.offsetLeft+axiscanvas.width))<tickfontHeight && Math.abs(event.layerY-(axiscanvas.offsetTop+axiscanvas.height))<tickfontHeight))
	{
		document.body.style.cursor = 'se-resize';
	}else if (event.layerX>axiscanvas.offsetLeft && event.layerX<axiscanvas.offsetLeft+axiscanvas.width && event.layerY>axiscanvas.offsetTop && event.layerY<axiscanvas.offsetTop+axiscanvas.height)
	{ 
	    document.body.style.cursor = 'crosshair';
	}else
	{
		document.body.style.cursor = 'default';
	}
}
function onFigureMouseOut(event){
	document.body.style.cursor = 'default';
	return;
}

function saveFigure(ifig){
	var canvas = document.getElementById("myfigurecanvas"+ifig);
	var axiscanvas = document.getElementById("myaxiscanvas"+ifig);
	var context = canvas.getContext("2d");
	context.drawImage(axiscanvas,axiscanvas.offsetLeft,axiscanvas.offsetTop)
	context.strokeStyle = "#000000";
	context.strokeRect(axiscanvas.offsetLeft,axiscanvas.offsetTop, axiscanvas.width, axiscanvas.height)
	var img     = canvas.toDataURL("image/png");
	context.clearRect (axiscanvas.offsetLeft,axiscanvas.offsetTop, axiscanvas.width, axiscanvas.height)
	window.open(img);
}

//FIGURE LAYOUT FUNCTIONS================================================================
function ApplyViewLayout(nfig,nfigcols)
{        
    nfigures=nfig
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
        figheight=figwidth/2
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

//DATA TRANSPORT FUNCTIONS===============================================================		
function exec_data_user_cmd(cmd_str) 
{
    var ret_str = "";
    try 
    {
      	ret_str=eval(cmd_str);
    } catch(err) { ret_str = "user command failed: " + err;}
}

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
			

function loadpage()
{
	start_data();
	checkCookie()	
}

function start_data() 
{
    datasocket = new WebSocket('ws://'+document.domain+':'+webdataportnumber);	
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
            datasocket.send("<data_user_event_timeseries args='" + arg_string + "'>");
        }else if (datasocket.readyState==3)
        {
            logconsole('Websocket connection closed, trying to reestablish',true,false,true)
			restore_data()
        }else
        {
            logconsole('Websocket state is '+datasocket.readyState+'. Command forfeited: '+arg_string,true,false,true)
        }
      } catch (err) {}
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
