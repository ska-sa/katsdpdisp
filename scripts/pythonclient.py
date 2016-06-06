from websocket import create_connection
ws = create_connection("ws://10.98.2.101:8001")
#set username
ws.send(u"<data_user_event_timeseries args='setusername,pythonclient'>")
result =  ws.recv()#ignore this reply
ws.send(u"<data_user_event_timeseries args='inputs'>")
result2=ws.recv()#ignore this reply
inputs=ws.recv().split("\"")[1]
print 'Available inputs:',inputs

#get whole spectrum
ws.send(u"<data_user_event_timeseries args='sendfiguredata,-1,-1,-1,complex,14h15h'>")
result2=ws.recv()
spectrum =  eval(result2)
plot(angle(spectrum))


#query channel 200 only
ws.send(u"<data_user_event_timeseries args='sendfiguredata,-1,200,201,mag,2h2h'>")
chan200 =  eval(ws.recv())
print chan200

ws.close()