from websocket import create_connection
ws = create_connection("ws://10.98.2.111:8000/ws")
#set username
ws.send(u'setusername,pythonclient')
result =  ws.recv()#ignore this reply
ws.send(u'inputs')
result2=ws.recv()#ignore this reply
inputs=ws.recv().split("\"")[1]
print 'Available inputs:',inputs

#get whole spectrum
ws.send(u'sendfiguredata,-1,-1,-1,complex,14h15h')
result2=ws.recv()
spectrum =  eval(result2)
plot(angle(spectrum))


#query channel 200 only
ws.send(u'sendfiguredata,-1,200,201,mag,2h2h')
chan200 =  eval(ws.recv())
print chan200

#determine sub array number
ws.send(u'telstate,subarray_product_id,')
subarrayproduct=ws.recv().split("\"")[1].split("'")[1]
print 'product:',subarrayproduct

ws.close()

#scan ports to determine which port is used for which subarray
from websocket import create_connection
baseport=8000
active_timeplots={}
for portoffset in range(0,20):
    try:
        ws = create_connection("ws://10.98.2.111:%d/ws"%(baseport+portoffset))
    except Exception, e:
        print 'port %d'%(baseport+portoffset+1),e
        continue
    #set username
    ws.send(u'setusername,portscannerclient')
    result =  ws.recv()#ignore this reply
    result2 =  ws.recv()#ignore this reply
    ws.send(u'telstate,subarray_product_id,')
    subarrayproduct=ws.recv().split("\"")[1].split("'")[1]
    print 'port:%d '%(baseport+portoffset)+'product:'+subarrayproduct
    active_timeplots[baseport+portoffset]=subarrayproduct
    ws.close()

print active_timeplots
