var log10=Math.log(10);
var tickfontHeight=15;
var tickfont2Height=tickfontHeight*0.7;
var tickfont2Heightspace=tickfont2Height/5
var titlefontHeight=20;
var titlefontHeightspace=titlefontHeight/5
var labelfontHeight=18;
var labelfontHeightspace=labelfontHeight/5
var tickfontHeightspace=tickfontHeight/5
var majorticklength=tickfontHeight/3; //4 for 12 pt font
var minorticklength=tickfontHeight/6; //2 for 12 pt font

var swapaxes=false
var figureaspect=0.5
var timedrawcomplete=0

var corrlinepoly=[0,1,0,0,0,0,0,0]
var corrlinewidth=[2,2,1,1,1,1,1,1]//HH,VV,HV,VH,crossHH,VV,HV,VH
var corrlinealpha=[1,0.25,1,1,1,0.75,0.5,0.25]//HH,VV,HV,VH,crossHH,VV,HV,VH
var corrlinedash=[[0],[3,3],[0],[3,3],[0],[0],[0],[0]]//HH,VV,HV,VH,crossHH,VV,HV,VH
var jetRGB256=[]
var rubberbandDiv;
var rubberbandmousedown = {}
var rubberbandRectangle = {}
var rubberbanddragging = false;

var figdragmode=0
var figdragstart=[0,0]
var figdragstartevent=0
var figdragsizestart=[0,0]
var mouseclick=0
var ifigure=0

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

function intensityToSpectral(inten,min,max)
{
    idx=[0.0,12.7,25.5,38.3,51.1,63.9,76.7,89.5,102.3,115.1,153.4,166.2,179.0,191.8,204.6,217.4,230.2,243.0,256.0];
    R=[0.,118.12488863,135.87204162,0.90342145,0.,0.,0.,0.,0.,0.,0.,185.01855334,237.47332884,254.83383646,255.,255.,221.3007286,204.13957737,204.];
    G=[0.,0.,0.,0.,0.,118.31091208,152.81403634,169.92209496,170.0085,153.07311196,254.62807268,255.,238.16431008,204.33207796,153.47831184,1.37514654,0.,0.,204.];
    B=[0.,134.98179367,152.88036225,169.89550879,220.68962544,221.0085,221.0085,170.26758558,136.151017,0.58456682,0.,0.,0.,0.,0.,0.,0.,0.,204.];
    len=idx.length
    in256=(inten-min)/(max-min)*256.0;
    if (in256<=0.0)
    {
        return [Math.floor(R[0]),Math.floor(G[0]),Math.floor(B[0])]
    }else
    {
        for (var c=1;c<len;c++)
        {
            if (in256<idx[c])
            {
                f=(in256-idx[c-1])/(idx[c]-idx[c-1])
                return [Math.floor(R[c]*f+R[c-1]*(1.0-f)),Math.floor(G[c]*f+G[c-1]*(1.0-f)),Math.floor(B[c]*f+B[c-1]*(1.0-f))]
            }
        }
    }
    return [Math.floor(R[len-1]),Math.floor(G[len-1]),Math.floor(B[len-1])]
}

function makejet()
{
    for (c=0;c<256;c++)
        // jetRGB256[c]=intensityToJet(c,0,255)
        jetRGB256[c]=intensityToSpectral(c,0,255)
    jetRGB256[NaN]=[255,255,255]
}

function unitPrefixFromIndex(iprefix,units)
{
    var g_metricPREFIX="kMGTPEZY";
    var g_metricprefix="m"+String.fromCharCode(181)+"npfazy";
    if (iprefix>0)
    {
        if (iprefix<8)  return g_metricPREFIX[(iprefix-1)]+units;
        else            return "10e"+(iprefix*3)+units;
    }else if (iprefix<0)
    {
        if (-iprefix<8) return g_metricprefix[(-iprefix-1)]+units;
        else            return "10e"+(iprefix*3)+units;
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
    if (labelpos)   context.fillText(label,pixx+pixspan/2-sz.width/2.0,pixy-((numberpos)?tickfontHeight:0)-((timelabel!='')?tickfont2Height:0)-tickfontHeightspace*2-((dotickpos)?majorticklength:0))
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

function getminmax(datalist,istart,iend)
{
    if (datalist.length==0) return [NaN,NaN]
    mn=datalist[0][0]
    mx=mn
    if (typeof(mn)=="undefined")//so it is just a vector, not a vector of vector
    {
        if (istart===undefined && iend===undefined)
        {
            mn=Math.min.apply(Math, datalist)
            mx=Math.max.apply(Math, datalist)
        }else
        {
            mn=Math.min.apply(Math, datalist.slice(istart,iend))
            mx=Math.max.apply(Math, datalist.slice(istart,iend))
        }
        if (!isFinite(mn) || !isFinite(mx))
        {
            mn=NaN
            mx=NaN
            if (istart===undefined)
                iistart=0
            else
                iistart=istart
            if (iend===undefined)
                iiend=datalist.length
            else
                iiend=iend
            for (iel=iistart;iel<iiend;iel++)
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
            if (istart===undefined)
                iistart=0
            else
                iistart=istart
            if (iend===undefined)
                iiend=theline.length
            else
                iiend=iend
            for (iel=iistart;iel<iiend;iel++)
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


function drawFigure(ifig,datax,dataylist,clrlist,xsensor,ysensor,sensorname,xtextsensor,textsensor,xmin,xmax,ymin,ymax,title,xlabel,ylabel,xunit,yunit,legend,spanlist,spancolorlist)
{
    if (document.getElementById('myfigurediv'+ifig).style.display=='none' || typeof datax=="undefined" || typeof dataylist=="undefined" || typeof dataylist.length=="undefined"  || typeof(dataylist[0])=="undefined")
    {
        return;
    }
    yviewmin=[]
    yviewmax=[]
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
    xviewmin=Math.min(localdatax[0],localdatax[localdatax.length-1])
    xviewmax=Math.max(localdatax[0],localdatax[localdatax.length-1])
    if (!isNaN(xmin)) xviewmin=xmin
    if (!isNaN(xmax)) xviewmax=xmax
    if (xviewmax==xviewmin)
    {
        xviewmax+=0.5;
        xviewmin-=0.5;
    }
    var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
    axisposh=axiscanvas.offsetLeft
    axisposv=axiscanvas.offsetTop
    xspan=axiscanvas.width
    yspan=axiscanvas.height
    var figcontext = figcanvas.getContext('2d');
    if (figcontext)
    {
        figcontext.fillStyle = "#FFFFFF";
        figcontext.clearRect(axisposh, axisposv, axiscanvas.width, axiscanvas.height);
        figcontext.fillRect(0, 0, axisposh, figcanvas.height);
        figcontext.fillRect(axisposh+axiscanvas.width, 0, figcanvas.width-(axisposh+axiscanvas.width), figcanvas.height);
        figcontext.fillRect(0, 0, figcanvas.width, axisposv);
        figcontext.fillRect(0, axisposv+axiscanvas.height, figcanvas.width, figcanvas.height-(axisposv+axiscanvas.height));
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
        xscale=xspan/(xviewmax-xviewmin)
        xoff=-xviewmin*xscale;
        for (x=0;x<localdatax.length && (xoff+xscale*localdatax[x])<0;x++);
        if (x>1)ixstart=x-2;else ixstart=0;
        for (x=localdatax.length-1;x>=0 && (xoff+xscale*localdatax[x])>xspan;x--);
        if (x<localdatax.length-1)ixend=x+2;else ixend=localdatax.length;
        for (itwin=0;itwin<dataylist.length;itwin++)
        {
            if (itwin<1)  minmax=getminmax(dataylist[itwin])
            else minmax=getminmax(dataylist[itwin],ixstart,ixend)
            span=minmax[1]-minmax[0]
            if (itwin<1 && !isNaN(ymin)) yviewmin[itwin]=ymin
            else yviewmin[itwin]=minmax[0]-span*0.05
            if (itwin<1 && !isNaN(ymax)) yviewmax[itwin]=ymax
            else yviewmax[itwin]=minmax[1]+span*0.05
            if (yviewmax[itwin]==yviewmin[itwin])
            {
                yviewmax[itwin]+=0.5;
                yviewmin[itwin]-=0.5;
            }
            yscale=yspan/(yviewmax[itwin]-yviewmin[itwin])
            yoff=yspan+yviewmin[itwin]*yscale
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
        //sensors
        if (xsensor.length>1)
        {
            var localdatax
            if (xsensor.length==2 && ysensor.length>2)
            {
                localdatax=new Array(ysensor.length)
                if ((xunit=='s'))
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xsensor[0]-datax[datax.length-1]+(xsensor[1]-xsensor[0])*i/(localdatax.length-1)
                else
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xsensor[0]+(xsensor[1]-xsensor[0])*i/(localdatax.length-1)
            }else
            {
                localdatax=new Array(xsensor.length)
                if ((xunit=='s'))
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xsensor[i]-datax[datax.length-1]
                else
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xsensor[i]
            }
            itwin=1
            ixstart=0;ixend=0;
            xscale=xspan/(xviewmax-xviewmin)
            xoff=-xviewmin*xscale;
            for (x=0;x<localdatax.length && (xoff+xscale*localdatax[x])<0;x++);
            if (x>1)ixstart=x-2;else ixstart=0;
            for (x=localdatax.length-1;x>=0 && (xoff+xscale*localdatax[x])>xspan;x--);
            if (x<localdatax.length-1)ixend=x+2;else ixend=localdatax.length;
            minmax=getminmax(ysensor,ixstart,ixend)
            span=minmax[1]-minmax[0]
            yviewmin[itwin]=minmax[0]-span*0.05
            yviewmax[itwin]=minmax[1]+span*0.05
            if (yviewmax[itwin]==yviewmin[itwin])
            {
                yviewmax[itwin]+=0.5;
                yviewmin[itwin]-=0.5;
            }
            yscale=yspan/(yviewmax[itwin]-yviewmin[itwin])
            yoff=yspan+yviewmin[itwin]*yscale
            context.beginPath();
            context.lineWidth=1
            context.strokeStyle = "rgb(0,0,0)";
            context.moveTo(xoff+xscale*localdatax[ixstart],yoff-yscale*ysensor[ixstart]);
            for (x=ixstart+1;x<ixend;x++)
            {
                context.lineTo(xoff+xscale*localdatax[x],yoff-yscale*ysensor[x]);
            }
            context.stroke();
            context.closePath();
        }
        if (typeof(textsensor)!="undefined" && textsensor.length>0)
        {
            var localdatax
            if (xtextsensor.length==2 && textsensor.length>2)
            {
                localdatax=new Array(textsensor.length)
                if ((xunit=='s'))
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xtextsensor[0]-datax[datax.length-1]+(xtextsensor[1]-xtextsensor[0])*i/(localdatax.length-1)
                else
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xtextsensor[0]+(xtextsensor[1]-xtextsensor[0])*i/(localdatax.length-1)
            }else
            {
                localdatax=new Array(xtextsensor.length)
                if ((xunit=='s'))
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xtextsensor[i]-datax[datax.length-1]
                else
                    for (i=0;i<localdatax.length;i++)
                        localdatax[i]=xtextsensor[i]
            }
            ixstart=0;ixend=0;
            xscale=xspan/(xviewmax-xviewmin)
            xoff=-xviewmin*xscale;
            for (x=0;x<localdatax.length && (xoff+xscale*localdatax[x])<0;x++);
            if (x>1)ixstart=x-2;else ixstart=0;
            for (x=localdatax.length-1;x>=0 && (xoff+xscale*localdatax[x])>xspan;x--);
            if (x<localdatax.length-1)ixend=x+2;else ixend=localdatax.length;

            textsensorfontheight=labelfontHeight;
            for (x=0;x<textsensor.length-1;x++)
            {
                if (xscale*(localdatax[x+1]-localdatax[x])<textsensorfontheight*2)
                {
                    textsensorfontheight=tickfontHeight;
                    break;
                }
            }
            for (x=0;x<textsensor.length-1;x++)
            {
                if (xscale*(localdatax[x+1]-localdatax[x])<textsensorfontheight*2)
                {
                    textsensorfontheight=tickfont2Height;
                    break;
                }
            }
            textsensorfontheightspace=textsensorfontheight/5
            context.rotate(-Math.PI/2);
            context.strokeStyle = "#000000";
            context.fillStyle = "rgba(0,0,0,0.5)";
            context.font=""+textsensorfontheight+"px sans-serif";
            xlast=1e100
            //plot text from right to left, ensuring rightmost (latest) entry is plotted, continue plotting ensuring no overlap
            for (x=textsensor.length-1;x>=0;x--)
            {
                sz=context.measureText(textsensor[x]);
                xhere=(xoff+xscale*localdatax[x])+textsensorfontheight;
                if (xhere<textsensorfontheight)//ensures there is text showing targetname if zoomed in, part 1
                    xhere=textsensorfontheight
                if (xhere<xlast-textsensorfontheight)
                {
                    context.fillText(textsensor[x],-sz.width-textsensorfontheightspace,xhere);
                    xlast=xhere;
                }
                if (xhere<=textsensorfontheight)break;//ensures there is text showing targetname if zoomed in, part 2
            }
            context.rotate(Math.PI/2);
            context.fillStyle = "#000000";
        }
            context.lineWidth=oldlinewidth;
            //context.setLineDash([0])
            if (xunit=='s')
                for (ispancolor=0;ispancolor<spancolorlist.length;ispancolor++)
                {
                    context.fillStyle='rgba('+spancolorlist[ispancolor][0]+','+spancolorlist[ispancolor][1]+','+spancolorlist[ispancolor][2]+','+spancolorlist[ispancolor][3]/255.0+')'
                    for (ispan=0;ispan<spanlist[ispancolor].length;ispan++)
                        context.fillRect(xoff+xscale*(spanlist[ispancolor][ispan][0]-datax[datax.length-1]),0,xscale*(spanlist[ispancolor][ispan][1]-spanlist[ispancolor][ispan][0]),yspan)
                }
            else
                for (ispancolor=0;ispancolor<spancolorlist.length;ispancolor++)
                {
                    context.fillStyle='rgba('+spancolorlist[ispancolor][0]+','+spancolorlist[ispancolor][1]+','+spancolorlist[ispancolor][2]+','+spancolorlist[ispancolor][3]/255.0+')'
                    for (ispan=0;ispan<spanlist[ispancolor].length;ispan++)
                        context.fillRect(xoff+xscale*spanlist[ispancolor][ispan][0],0,xscale*(spanlist[ispancolor][ispan][1]-spanlist[ispancolor][ispan][0]),yspan)
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
                figcontext.fillText(title,axisposh+axiscanvas.width/2-sz.width/2.0,axisposv/2+(titlefontHeight-titlefontHeightspace)/2)
            }

            roundScreen=0
            units=xunit
            dovertical=0
            numberpos=0
            labelpos=0
            dotickmajor=1
            dotickminor=1
            dotickpos=0
            dotickneg=1
            doprefix=0
            timelabel=(units=='s')?xlabel:''
            if (RG_fig[ifig].showxlabel!='on') xlabel=''
            if (RG_fig[ifig].showxticklabel!='on') doticklabel=0; else doticklabel=1

            drawMetricLinearAtPt(figcontext, xviewmin, xviewmax, xspan, axisposh, axisposv+axiscanvas.height, units, xlabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

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

            drawMetricLinearAtPt(figcontext, yviewmin[0], yviewmax[0], yspan, -(axisposv+axiscanvas.height),axisposh, units, ylabel[0], dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

            if (sensorname.length>0)//twin axis
            {
                units=''
                label=sensorname
                dovertical=1
                numberpos=0
                labelpos=0
                dotickpos=0
                dotickneg=1
                doprefix=1
                timelabel=''
                if (RG_fig[ifig].showylabel!='on') ylabel[1]=''
                if (RG_fig[ifig].showyticklabel!='on') doticklabel=0; else doticklabel=1

                drawMetricLinearAtPt(figcontext, yviewmin[1], yviewmax[1], axiscanvas.height, -(axisposv+axiscanvas.height),axisposh+axiscanvas.width, units, label, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)
            }
            figcontext.restore();

            if (RG_fig[ifig].showlegend=='on')
            {
                if (legend.length)
                {
                    legendfontHeight=labelfontHeight*0.9
                    figcontext.font=""+legendfontHeight+"px sans-serif";
                    x=figcanvas.width-75
                    for (iline=0,y=axisposv+legendfontHeight;iline<legend.length && y<axisposv+axiscanvas.height-legendfontHeight/5;iline++,y+=legendfontHeight)
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
            figcontext.strokeRect(axisposh, axisposv, axiscanvas.width, axiscanvas.height);
        }
    RG_fig[ifig].xmin_eval=xviewmin;
    RG_fig[ifig].xmax_eval=xviewmax;
    RG_fig[ifig].ymin_eval=yviewmin[0];
    RG_fig[ifig].ymax_eval=yviewmax[0];
}

function drawRelationFigure(ifig,datax,dataylist,clrlist,xmin,xmax,ymin,ymax,title,xlabel,ylabel,xunit,yunit,legend,spanlist,spancolorlist)
{
    if (document.getElementById('myfigurediv'+ifig).style.display=='none' || typeof datax=="undefined" || typeof dataylist=="undefined" || typeof dataylist.length=="undefined"  || typeof(dataylist[0])=="undefined")
    {
        return;
    }
    yviewmin=[]
    yviewmax=[]
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
    xviewmin=Math.min(localdatax[0],localdatax[localdatax.length-1])
    xviewmax=Math.max(localdatax[0],localdatax[localdatax.length-1])
    if (!isNaN(xmin)) xviewmin=xmin
    if (!isNaN(xmax)) xviewmax=xmax
    if (xviewmax==xviewmin)
    {
        xviewmax+=0.5;
        xviewmin-=0.5;
    }
    var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
    axisposh=axiscanvas.offsetLeft
    axisposv=axiscanvas.offsetTop
    // xspan=axiscanvas.width
    // yspan=axiscanvas.height
    xspan=axiscanvas.height
    yspan=axiscanvas.width
    var figcontext = figcanvas.getContext('2d');
    if (figcontext)
    {
        figcontext.fillStyle = "#FFFFFF";
        figcontext.clearRect(axisposh, axisposv, axiscanvas.width, axiscanvas.height);
        figcontext.fillRect(0, 0, axisposh, figcanvas.height);
        figcontext.fillRect(axisposh+axiscanvas.width, 0, figcanvas.width-(axisposh+axiscanvas.width), figcanvas.height);
        figcontext.fillRect(0, 0, figcanvas.width, axisposv);
        figcontext.fillRect(0, axisposv+axiscanvas.height, figcanvas.width, figcanvas.height-(axisposv+axiscanvas.height));
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
        xscale=xspan/(xviewmax-xviewmin)
        xoff=xspan+xviewmin*xscale;
        for (x=0;x<localdatax.length && (xoff-xscale*localdatax[x])<0;x++);
        if (x>1)ixstart=x-2;else ixstart=0;
        for (x=localdatax.length-1;x>=0 && (xoff-xscale*localdatax[x])>xspan;x--);
        if (x<localdatax.length-1)ixend=x+2;else ixend=localdatax.length;
        for (itwin=0;itwin<dataylist.length;itwin++)
        {
            minmax=getminmax(dataylist[itwin])
            span=minmax[1]-minmax[0]
            if (!isNaN(ymin)) yviewmin[itwin]=ymin
            else yviewmin[itwin]=minmax[0]-span*0.05
            if (!isNaN(ymax)) yviewmax[itwin]=ymax
            else yviewmax[itwin]=minmax[1]+span*0.05
            if (yviewmax[itwin]==yviewmin[itwin])
            {
                yviewmax[itwin]+=0.5;
                yviewmin[itwin]-=0.5;
            }
            yscale=yspan/(yviewmax[itwin]-yviewmin[itwin])
            yoff=-yviewmin[itwin]*yscale
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
                        context.moveTo(yoff+yscale*dataylist[itwin][iline][ixstart],xoff-xscale*localdatax[ixstart]);
                        for (x=ixstart+1;x<ixend;x++)
                        {
                            context.lineTo(yoff+yscale*dataylist[itwin][iline][x],xoff-xscale*localdatax[x]);
                        }
                        iline++;
                        for (x=ixend-1;x>=ixstart;x--)
                        {
                            context.lineTo(yoff+yscale*dataylist[itwin][iline][x],xoff-xscale*localdatax[x]);
                        }
                        context.closePath();
                        context.fill()
                    }else
                    {
                        context.strokeStyle = "rgba("+(clrlist[iline][0])+","+(clrlist[iline][1])+","+(clrlist[iline][2])+","+(corrlinealpha[clrlist[iline][3]])+")";
                        context.moveTo(yoff+yscale*dataylist[itwin][iline][ixstart],xoff-xscale*localdatax[ixstart]);
                        for (x=ixstart+1;x<ixend;x++)
                        {
                            context.lineTo(yoff+yscale*dataylist[itwin][iline][x],xoff-xscale*localdatax[x]);
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
                for (ispan=0;ispan<spanlist[ispancolor].length;ispan++)
                    context.fillRect(0,xoff-xscale*spanlist[ispancolor][ispan][0],yspan,xscale*(spanlist[ispancolor][ispan][1]-spanlist[ispancolor][ispan][0]))
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
                figcontext.fillText(title,axisposh+axiscanvas.width/2-sz.width/2.0,axisposv/2+(titlefontHeight-titlefontHeightspace)/2)
            }

            roundScreen=0
            units=yunit[0]
            dovertical=0
            numberpos=0
            labelpos=0
            dotickmajor=1
            dotickminor=1
            dotickpos=0
            dotickneg=1
            doprefix=1
            timelabel=''
            if (RG_fig[ifig].showylabel!='on') ylabel[0]=''
            if (RG_fig[ifig].showyticklabel!='on') doticklabel=0; else doticklabel=1

            drawMetricLinearAtPt(figcontext, yviewmin[0], yviewmax[0], yspan, axisposh, axisposv+axiscanvas.height, units, ylabel[0], dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

            figcontext.save();
            figcontext.rotate(-Math.PI/2);


            units=xunit
            dovertical=1
            numberpos=1
            labelpos=1
            dotickpos=1
            dotickneg=0
            doprefix=0
            timelabel=(units=='s')?xlabel:''
            if (RG_fig[ifig].showxlabel!='on') xlabel=''
            if (RG_fig[ifig].showxticklabel!='on') doticklabel=0; else doticklabel=1

            drawMetricLinearAtPt(figcontext, xviewmin, xviewmax, xspan, -(axisposv+axiscanvas.height), axisposh, units, xlabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

            figcontext.restore();

            if (RG_fig[ifig].showlegend=='on')
            {
                if (legend.length)
                {
                    legendfontHeight=labelfontHeight*0.9
                    figcontext.font=""+legendfontHeight+"px sans-serif";
                    x=axisposh+axiscanvas.width+((ylabel.length>1)?(dotickneg*majorticklength)+((numberpos==0)*tickfontHeight)+(labelpos==0)*legendfontHeight:0)+legendfontHeight/4
                    for (iline=0,y=axisposv+legendfontHeight;iline<legend.length && y<axisposv+axiscanvas.height-legendfontHeight/5;iline++,y+=legendfontHeight)
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
            figcontext.strokeRect(axisposh, axisposv, axiscanvas.width, axiscanvas.height);
        }
    RG_fig[ifig].xmin_eval=xviewmin;
    RG_fig[ifig].xmax_eval=xviewmax;
    RG_fig[ifig].ymin_eval=yviewmin[0];
    RG_fig[ifig].ymax_eval=yviewmax[0];
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

                    if (1)//xunit=='')
                    for(var i=0;i<imgdatalen-4;i+=4)
                    {
//                      imgdata.data[i+3] = 255;//A
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
//                      imgdata.data[i+3] = 255;//A
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
                }else if (RG_fig[ifig].showtitle=='in')
                {
                    if (title.slice(0,10)=='Waterfall ')
                    {
                        trimtitle=title.slice(10)
                        if (axiscanvas.width>200)
                            thefontHeight=titlefontHeight
                        else
                            thefontHeight=labelfontHeight
                        thefontHeightspace=thefontHeight/5
                        context.font=""+thefontHeight+"px sans-serif";
                        sz=context.measureText(trimtitle)
                        context.fillStyle = "rgba(255,255,255,0.5)";
                        context.fillRect(thefontHeightspace,thefontHeightspace,sz.width+thefontHeightspace,thefontHeight+thefontHeightspace)
                        context.fillStyle = "#000000";
                        context.fillText(trimtitle,thefontHeightspace+thefontHeightspace/2,thefontHeight+thefontHeightspace)
                    }
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
                doprefix=(units=='s')?1:0 //for lag plot
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

function drawMatrixFigure(ifig,mxdata,phdata,legendx,legendy,title,cunit,clabel)
{
    var cmin=NaN,cmax=NaN,pmin=NaN,pmax=NaN;
    for(var i=0;i<phdata.length;i++)
        phdata[i]=Math.abs(phdata[i]);

            if (document.getElementById('myfigurediv'+ifig).style.display=='none' || typeof mxdata=="undefined")
            {
                return;
            }
          var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
          var figcanvas = document.getElementById('myfigurecanvas'+ifig);
          axisposx=axiscanvas.offsetLeft
          axisposy=axiscanvas.offsetTop
          var figcontext = figcanvas.getContext('2d');
          cdata=new Array(legendx.length)
          var hviewmin=0
          var hviewmax=legendx.length
          var vviewmin=0
          var vviewmax=legendy.length
          var dataxmin=0
          var dataxmax=legendx.length
          var dataymin=0
          var dataymax=legendy.length
          for (var i=0;i<legendx.length;i++)
          {
              cdata[i]=new Array(legendy.length);
              cdata[i][i]=mxdata[i];
          }
          var c=legendx.length;
          for (var i=0;i<legendx.length;i++)
          {
              for (var j=i+1;j<legendy.length;j++)
              {
                  cdata[i][j]=mxdata[c];
                  cdata[j][i]=phdata[c];
                  c++;
              }
          }
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
                    minmax=getminmax(mxdata)
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

                    pviewmin=-60
                    pviewmax=20
                    minmax=getminmax(phdata)
                    if (!isNaN(pmin)) pviewmin=pmin
                    else pviewmin=minmax[0]
                        if (!isNaN(pmax)) pviewmax=pmax
                    else pviewmax=minmax[1]
                    if (pviewmax==pviewmin)
                    {
                        pviewmax+=0.5;
                        pviewmin-=0.5;
                    }
                    pscale=255.0/(pviewmax-pviewmin)

                    var imgdata = context.getImageData(0,0,axiscanvas.width,axiscanvas.height);
                    var imgdatalen = imgdata.data.length;
                    rowscale=(cdata.length)/(dataymax-dataymin)
                    colscale=(cdata[0].length)/(dataxmax-dataxmin)

                    if (1)//xunit=='')
                    for(var i=0;i<imgdatalen-4;i+=4)
                    {
//                      imgdata.data[i+3] = 255;//A
                        ih=(i/4)/axiscanvas.width
                        iw=(i/4)%axiscanvas.width
                        irow=Math.floor(((ih/axiscanvas.height)*(vviewmax-vviewmin)+vviewmin-dataymin)*rowscale)
                        if (irow>=0 && irow<cdata.length)
                        {
                            icol=Math.floor(((iw/axiscanvas.width)*(hviewmax-hviewmin)+hviewmin-dataxmin)*colscale)
                            if (icol>=0 && icol<cdata[irow].length)
                            {
                                if (icol<irow)
                                {
                                    c256=Math.floor((cdata[irow][icol]-pviewmin)*pscale);
                                    if (c256<0)c256=0
                                    else if (c256>255)c256=255
                                    imgdata.data.set(jetRGB256[c256],i)
                                }else
                                {
                                    c256=Math.floor((cdata[irow][icol]-cviewmin)*cscale);
                                    if (c256<0)c256=0
                                    else if (c256>255)c256=255
                                    imgdata.data.set(jetRGB256[c256],i)
                                }
                            }
                        }
                    }//for
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
                figcontext.font=""+tickfont2Height+"px sans-serif";
                for (i=0;i<legendy.length;i++)
                {
                    sz=figcontext.measureText(legendy[i])
                    figcontext.fillText(legendy[i],axisposx-sz.width-2,axisposy+tickfont2Height/2+(i+0.5)*axiscanvas.height/legendy.length)
                }
                figcontext.save();
                figcontext.rotate(-Math.PI/2);
                figcontext.font=""+tickfont2Height+"px sans-serif";
                for (i=0;i<legendx.length;i++)
                {
                    sz=figcontext.measureText(legendx[i])
                    figcontext.fillText(legendx[i],-axiscanvas.height-axisposy-sz.width-2,axisposx+tickfont2Height/2+(i+0.5)*axiscanvas.width/legendy.length)
                }
                roundScreen=0
                dotickmajor=1
                dotickminor=1
                dotickpos=0
                dotickneg=1
                doprefix=0
                halfgap=titlefontHeightspace
                if (RG_fig[ifig].showlegend=='on')
                {
                    units=cunit//power
                    dovertical=1
                    numberpos=0
                    labelpos=0
                    dotickpos=0
                    dotickneg=1
                    doprefix=1
                    doticklabel=1
                    timelabel=(units=='s')?clabel:''
                    displaxisc={viewmin:cviewmin,viewmax:cviewmax,pixspan:axiscanvas.height/2.0-halfgap};
                    colorbaroff=titlefontHeightspace*2;
                    colorbarwidth=titlefontHeight;

                    drawMetricLinearAtPt(figcontext, cviewmin, cviewmax, axiscanvas.height/2.0-halfgap, -(axisposy+axiscanvas.height/2.0-halfgap),colorbaroff+colorbarwidth+axisposx+axiscanvas.width, units, clabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)

                    clabel='Phase'
                    units=''
                    dovertical=1
                    numberpos=0
                    labelpos=0
                    dotickpos=0
                    dotickneg=1
                    doprefix=1
                    doticklabel=1
                    timelabel=(units=='s')?clabel:''
                    displaxisc={viewmin:pviewmin,viewmax:pviewmax,pixspan:axiscanvas.height/2.0-halfgap};
                    colorbaroff=titlefontHeightspace*2;
                    colorbarwidth=titlefontHeight;

                    drawMetricLinearAtPt(figcontext, pviewmin, pviewmax, axiscanvas.height/2.0-halfgap, -(axisposy+axiscanvas.height),colorbaroff+colorbarwidth+axisposx+axiscanvas.width, units, clabel, dovertical, numberpos, labelpos, roundScreen, doticklabel, dotickmajor, dotickminor, dotickpos, dotickneg, doprefix,timelabel)
                }
                figcontext.restore();

                figcontext.strokeRect(axisposx, axisposy, axiscanvas.width, axiscanvas.height);
                // draw colorbar
                if (RG_fig[ifig].showlegend=='on')
                {
                    var imgdata = figcontext.getImageData(axisposx+axiscanvas.width+colorbaroff, axisposy, colorbarwidth, axiscanvas.height/2.0-halfgap);
                    var imgdatalen = imgdata.data.length;

                    for(var i=0;i<imgdatalen-4;i+=4)
                    {
                        ih=(i/4)/colorbarwidth;//height
                        c256=Math.floor((((axiscanvas.height/2-halfgap)-ih)/(axiscanvas.height/2-halfgap))*255)
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
                    figcontext.strokeRect(axisposx+axiscanvas.width+colorbaroff, axisposy, colorbarwidth, axiscanvas.height/2-halfgap);

                    imgdata = figcontext.getImageData(axisposx+axiscanvas.width+colorbaroff, axisposy+axiscanvas.height/2.0+halfgap, colorbarwidth, axiscanvas.height/2.0-halfgap);
                    imgdatalen = imgdata.data.length;

                    for(var i=0;i<imgdatalen-4;i+=4)
                    {
                        ih=(i/4)/colorbarwidth;//height
                        c256=Math.floor((((axiscanvas.height/2-halfgap)-ih)/(axiscanvas.height/2-halfgap))*255)
                        if (c256<0)c256=0
                        else if (c256>255)c256=255
                        imgdata.data.set(jetRGB256[c256],i)
                        //RGB=jetRGB256[c256]
                        //imgdata.data[i] = RGB[0];//R
                        //imgdata.data[i+1] = RGB[1];//G
                        //imgdata.data[i+2] = RGB[2];//B
                        //imgdata.data[i+3] = 255;//A
                    }
                    figcontext.putImageData(imgdata,axisposx+axiscanvas.width+colorbaroff, axisposy+axiscanvas.height/2.0+halfgap);
                    figcontext.strokeRect(axisposx+axiscanvas.width+colorbaroff, axisposy+axiscanvas.height/2.0+halfgap, colorbarwidth, axiscanvas.height/2-halfgap);
                }
        }
        RG_fig[ifig].xmin_eval=hviewmin;
        RG_fig[ifig].xmax_eval=hviewmax;
        RG_fig[ifig].ymin_eval=vviewmin;
        RG_fig[ifig].ymax_eval=vviewmax;
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

function savePage(){
    var limitxmax=0,limitymax=0,limitxmin=1e100,limitymin=1e100;
    for (ifig=0;ifig<nfigures;ifig++)
    {
        var fig = document.getElementById("myfigurediv"+ifig);
        if (fig.offsetLeft<limitxmin)limitxmin=fig.offsetLeft;
        if (fig.offsetTop<limitymin)limitymin=fig.offsetTop;
        if (fig.offsetLeft+fig.offsetWidth>limitxmax)limitxmax=fig.offsetLeft+fig.offsetWidth;
        if (fig.offsetTop+fig.offsetHeight>limitymax)limitymax=fig.offsetTop+fig.offsetHeight;
    }
    var newcanvas = document.createElement('canvas')
    newcanvas.width  = limitxmax-limitxmin;
    newcanvas.height = limitymax-limitymin;
    var context = newcanvas.getContext("2d");
    for (ifig=0;ifig<nfigures;ifig++)
    {
        var fig = document.getElementById("myfigurediv"+ifig);
        var canvas = document.getElementById("myfigurecanvas"+ifig);
        context.drawImage(canvas,fig.offsetLeft-limitxmin,fig.offsetTop-limitymin)
        var axiscanvas = document.getElementById("myaxiscanvas"+ifig);
        context.drawImage(axiscanvas,fig.offsetLeft-limitxmin+canvas.offsetLeft+axiscanvas.offsetLeft,fig.offsetTop-limitymin+canvas.offsetTop+axiscanvas.offsetTop)
        context.strokeStyle = "#000000";
        context.strokeRect(fig.offsetLeft-limitxmin+canvas.offsetLeft+axiscanvas.offsetLeft,fig.offsetTop-limitymin+canvas.offsetTop+axiscanvas.offsetTop, axiscanvas.width, axiscanvas.height)
    }
    var img = newcanvas.toDataURL("image/png");
    window.open(img);
}

//FIGURE MOUSE EVENTS ===================================================================

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
        if (newsizex<200)newsizex=200;
        if (newsizey<100)newsizey=100;
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

        if (swapaxes && (RG_fig[ifigure].figtype=='timeseries'))
        {
            figx0=(pixy0)/axiscanvas.height*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
            figy0=(pixx0)/axiscanvas.width*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;
            figx1=(pixy1)/axiscanvas.height*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
            figy1=(pixx1)/axiscanvas.width*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;
        }else
        {
            figx0=(pixx0)/axiscanvas.width*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
            figy0=(pixy0)/axiscanvas.height*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;
            figx1=(pixx1)/axiscanvas.width*(RG_fig[ifigure].xmax_eval-RG_fig[ifigure].xmin_eval)+RG_fig[ifigure].xmin_eval;
            figy1=(pixy1)/axiscanvas.height*(RG_fig[ifigure].ymax_eval-RG_fig[ifigure].ymin_eval)+RG_fig[ifigure].ymin_eval;
        }

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
    {//double click in central plot area
        if (RG_fig[ifigure].figtype.slice(0,4)=='blmx')//make waterfall plot of selected product
        {
            ix=Math.floor(RG_fig[ifigure].legendx.length*(event.layerX-axiscanvas.offsetLeft)/axiscanvas.width);
            iy=Math.floor(RG_fig[ifigure].legendy.length*(event.layerY-axiscanvas.offsetTop)/axiscanvas.height);
            if (iy<=ix)//abs
                handle_data_user_event('waterfall'+RG_fig[ifigure].legendy[iy].slice(0,-1)+RG_fig[ifigure].figtype[4]+RG_fig[ifigure].legendx[ix].slice(0,-1)+RG_fig[ifigure].figtype[5])
            else//phase
                handle_data_user_event('waterfallphase'+RG_fig[ifigure].legendx[ix].slice(0,-1)+RG_fig[ifigure].figtype[4]+RG_fig[ifigure].legendy[iy].slice(0,-1)+RG_fig[ifigure].figtype[5])
        }else//unzoom all
        {
            RG_fig[ifigure].xmin=NaN
            RG_fig[ifigure].xmax=NaN
            RG_fig[ifigure].ymin=NaN
            RG_fig[ifigure].ymax=NaN
            RG_fig[ifigure].overridelimit=1;
            redrawfigure(ifigure)
            handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
        }
    }else if (event.layerX>axiscanvas.offsetLeft && event.layerX<axiscanvas.offsetLeft+axiscanvas.width && event.layerY>axiscanvas.offsetTop+axiscanvas.height && event.layerY<axiscanvas.offsetTop+axiscanvas.height+majorticklength+tickfontHeight+tickfont2Height+tickfont2Heightspace)
    {
        if (swapaxes && (RG_fig[ifigure].figtype=='timeseries'))
        {
            RG_fig[ifigure].ymin=NaN
            RG_fig[ifigure].ymax=NaN
        }else
        {
            RG_fig[ifigure].xmin=NaN
            RG_fig[ifigure].xmax=NaN
        }
        RG_fig[ifigure].overridelimit=1;
        redrawfigure(ifigure)
        handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
    }   else if (event.layerX>axiscanvas.offsetLeft-(majorticklength+tickfontHeight) && event.layerX<axiscanvas.offsetLeft && event.layerY>axiscanvas.offsetTop && event.layerY<axiscanvas.offsetTop+axiscanvas.height)
        {
            if (swapaxes && (RG_fig[ifigure].figtype=='timeseries'))
            {
                RG_fig[ifigure].xmin=NaN
                RG_fig[ifigure].xmax=NaN
            }else
            {
                RG_fig[ifigure].ymin=NaN
                RG_fig[ifigure].ymax=NaN
            }
            RG_fig[ifigure].overridelimit=1;
            redrawfigure(ifigure)
            handle_data_user_event('setzoom,'+ifigure+','+RG_fig[ifigure].xmin+','+RG_fig[ifigure].xmax+','+RG_fig[ifigure].ymin+','+RG_fig[ifigure].ymax+','+RG_fig[ifigure].cmin+','+RG_fig[ifigure].cmax)
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
            if (newsizey<100)newsizey=100;
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

//REDRAW figure ===================================================================
//given dimensions of figure canvas, calc axis canvas position and dimensions
function setaxiscanvasrect(ifig)
{
    var axiscanvas = document.getElementById('myaxiscanvas'+ifig);
    var figcanvas = document.getElementById('myfigurecanvas'+ifig);
    if (ifig==-1)
    {
        _left=50;_top=55;_width=figcanvas.width-130;_height=figcanvas.height-130;
    }else
    if (swapaxes && (RG_fig[ifig].figtype=='timeseries'))
    {
        if (RG_fig[ifig].showxticklabel=='on')
            _left=30
        else
            _left=0
        if (RG_fig[ifig].showxlabel=='on')
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
        if (RG_fig[ifig].showylabel=='on')
            _height=figcanvas.height-55-_top;
        else
            _height=figcanvas.height-33-_top
        if (RG_fig[ifig].showyticklabel=='on')
            _height-=0
        else
            _height+=30
    }
    else
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
        if ((RG_fig[ifig].figtype=='timeseries') && (RG_fig[ifig].sensorname.length >0))//twinaxis, extra
        {
            _width-=30
            if (RG_fig[ifig].showylabel=='on')
                _width-=20
        }
        if (RG_fig[ifig].showxlabel=='on')
            _height=figcanvas.height-55-_top;
        else
            _height=figcanvas.height-33-_top
        if (RG_fig[ifig].showxticklabel=='on')
            _height-=0
        else
            _height+=30
    }
    if (RG_fig[ifig]!=undefined && RG_fig[ifig].mxdata!=undefined)
    {
        if (_width>_height)
        {
            _left+=(_width-_height)/2.0;
            _width=_height;
        }
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
    {
        if (RG_fig[ifig].mxdata==undefined)
        {
            if (swapaxes && (RG_fig[ifig].figtype=='timeseries'))
                drawRelationFigure(ifig,RG_fig[ifig].xdata,RG_fig[ifig].ydata,RG_fig[ifig].color,RG_fig[ifig].xmin,RG_fig[ifig].xmax,RG_fig[ifig].ymin,RG_fig[ifig].ymax,RG_fig[ifig].title,RG_fig[ifig].xlabel,RG_fig[ifig].ylabel,RG_fig[ifig].xunit,RG_fig[ifig].yunit,RG_fig[ifig].legend,RG_fig[ifig].span,RG_fig[ifig].spancolor);
            else if (RG_fig[ifig].figtype=='timeseries')
                drawFigure(ifig,RG_fig[ifig].xdata,RG_fig[ifig].ydata,RG_fig[ifig].color,RG_fig[ifig].xsensor,RG_fig[ifig].ysensor,RG_fig[ifig].sensorname,RG_fig[ifig].xtextsensor,RG_fig[ifig].textsensor,RG_fig[ifig].xmin,RG_fig[ifig].xmax,RG_fig[ifig].ymin,RG_fig[ifig].ymax,RG_fig[ifig].title,RG_fig[ifig].xlabel,RG_fig[ifig].ylabel,RG_fig[ifig].xunit,RG_fig[ifig].yunit,RG_fig[ifig].legend,RG_fig[ifig].span,RG_fig[ifig].spancolor);
            else drawFigure(ifig,RG_fig[ifig].xdata,RG_fig[ifig].ydata,RG_fig[ifig].color,[],[],[],[],[],RG_fig[ifig].xmin,RG_fig[ifig].xmax,RG_fig[ifig].ymin,RG_fig[ifig].ymax,RG_fig[ifig].title,RG_fig[ifig].xlabel,RG_fig[ifig].ylabel,RG_fig[ifig].xunit,RG_fig[ifig].yunit,RG_fig[ifig].legend,RG_fig[ifig].span,RG_fig[ifig].spancolor);
        }else
        {
            drawMatrixFigure(ifig,RG_fig[ifig].mxdata,RG_fig[ifig].phdata,RG_fig[ifig].legendx,RG_fig[ifig].legendy,RG_fig[ifig].title,RG_fig[ifig].cunit,RG_fig[ifig].clabel)
        }
    }else
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
