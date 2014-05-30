from twisted.internet.protocol import Factory, Protocol #@UnresolvedImport
from twisted.internet import reactor #@UnresolvedImport
from twisted.protocols.basic import LineReceiver
import json
#import time

#maps the session id to a list of client sockets
sessionToClientsTable = {}
#maps the client join port to the host send port
hostToJoineeTable = {}
#maps the host send port to the client socket it sends to
portToSocketTable = {}
#maps the client control ip to the client join ip
remoteIpToServerPortTable = {}
#maps the port number to the listening port object
listenPorts = {}
#maps join client's ip to the host send port
clientIpToHostPort = {}
#maps host port to expected file size
hostPortToFilesize = {}
#maps a port to the session it is being used for
portToSessionTable = {}
#maps the session to the bulk receive sockets
sessionToBulkReceiveTable = {}
 
class IphoneChat(Protocol):
    
    #state can be HOST, NORMAL, JOIN, END
    myState = 'NORMAL'
    mySession = ""
    myRemoteIp = ""
    isPolicyRequest = False
    buffer = ""
    
    def connectionMade(self):
        #temporaryCache
        #print "a client connected"
        t = self.transport
        addr = t.getPeer()
        ip = addr.host
        port = addr.port
        print ip + ":" + str(port) + " connected to server ..."
        self.myRemoteIp = ip + ":" + str(port)
        #testerList.append(self)
    
    '''
    def startJoinProcedure(self):
        #open up a new port to receive data from host
        factory = Factory()
        factory.protocol = IphoneChat
        reactor.listenTCP(8082, factory)
    '''
    
    def dataReceived(self, data):
        #a = data.split(':')
        #print data
        #data isn't flushing to server, it seems to wait until the write has finished entirely before
        #it reaches server, as soon as it writes it doesn't hit server ...
        try:
            t = self.transport
            addr = t.getPeer()
            ip = addr.host
            port = addr.port
        
            #need to test this out, in theory, this will allow socket connections
            #from flex, basically flex requests the cross domain file through this
            #socket and we reply with the following string below ...
            if (data == "<policy-file-request/>\0"):
                self.isPolicyRequest = True
                self.transport.write("<cross-domain-policy><allow-access-from domain='*' to-ports='*' /></cross-domain-policy>\0");
                return
            #print str(data)
            #print "----------------------------- this is what i received ---------------------"

            splitData = str(data).splitlines()
            for s in splitData:
                #print "----- start chunk of data ------"
                #print str(s)
                #print "----- end   chunk of data ------"
                
                #ignore the new line character
                if s == '\n':
                    continue
                
                bufferedStr = s
                if (self.buffer != None):
                    bufferedStr = self.buffer + s
                
                print "----- start chunk of data ------"
                print self.buffer
                print s
                print "----- end   chunk of data ------"
                    
                #obj = json.loads(s)
                obj = json.loads(bufferedStr)
                if (self.buffer != None):
                    self.buffer = ""
                
                request = obj["request"]
                sessionID = obj["sessionID"]
                if (request == "startSession"):
                    #sessionID = "tester" #hardcoding session to 'tester' just to make things easier
                    if not sessionToClientsTable.has_key(sessionID):
                        clientList = []
                        sessionToClientsTable[sessionID] = clientList
                        self.myState = 'HOST'
                        clientList.append(self)
                        print ip + ":" + str(port) + " started session = " + sessionID
                        self.mySession = sessionID
                    else:
                        print sessionID + " already exists ... maybe should send an error response back ??"
                elif request == "joinSession":
                    #self.myState = 'JOIN'
                    #add self to the client list
                    clientList = sessionToClientsTable[sessionID]
                    clientList.append(self)
                    print ip + ":" + str(port) + " joining session = " + sessionID
                    self.mySession = sessionID
                    
                    hostSocket = self.getHostForSession(sessionID)
                    #very rare case, if client becomes host (only 2 people, host d/c)
                    if (hostSocket == self):
                        return
                    
                    hostTransport = hostSocket.transport
                    hostAddr = hostTransport.getPeer()
            
                    clientSocket = self
                    #TODO: i need to cache the two listening sockets somewhere
                    #so i can close them later!! i'm gonna leave them open for
                    #now but it's really not good!!
                    serverHostAddr = self.createSenderChannel()
                    serverHostIp = serverHostAddr.host
                    serverHostPort = serverHostAddr.port
                    serverJoineeAddr = self.createReceiverChannel()
                    serverJoineeIp = serverJoineeAddr.host
                    serverJoineePort = serverJoineeAddr.port
                    #cache the server joinee address to inform client the new
                    #socket to connect to
                    clientIP = ip + ":" + str(port)
                    remoteIpToServerPortTable[clientIP] = serverJoineeIp + ":" + str(serverJoineePort)
                    clientIpToHostPort[clientIP] = serverHostPort
                    #create mapping so i can remember which client to server
                    hostToJoineeTable[serverJoineePort] = serverHostPort
                    
                    #locate the host for this session then send the state request to him
                    host = self.getHostForSession(sessionID)
                    getStateRequest = {}
                    getStateRequest['request'] = 'getState'
                    getStateRequest['sessionID'] = sessionID
                    getStateRequest['clientHost'] = ip
                    getStateRequest['clientPort'] = port
                    getStateRequest['ip'] = serverHostIp
                    getStateRequest['port'] = serverHostPort
                    getStateRequestStr = json.dumps(getStateRequest) + "\n"
                    host.transport.write(getStateRequestStr)
                    #set up how the server will know how to send the state data back to current user!
                    #print "new client joined"
                elif request == "connect":
                    self.connectToSession(sessionID)
                elif (request == "updateData" or request == "trash"):
                    #recvData = obj["data"]
                    #print "Server received this data: " + recvData
                    for c in sessionToClientsTable[sessionID]:
                        if c != self:
                            #c.transport.write(str(s) + "\n")
                            c.transport.write(bufferedStr + "\n")
                            ct = self.transport
                            peerAddr = ct.getPeer()
                            peerIp = peerAddr.host
                            peerPort = peerAddr.port
                            print peerIp + ":" + str(peerPort) + " is the peer"
                            '''
                            hostAddr = ct.getHost()
                            hostIp = hostAddr.host
                            hostPort = hostAddr.port
                            print hostIp + ":" + str(hostPort) + " is the peer"
                            '''
                elif request == "ackGetState":
                    sessionID = obj['sessionID']
                    fileSize = obj['length']
                    clientHost = obj['clientHost']
                    clientPort = obj['clientPort']
                    #retrieve socket with these conditions and send returnState
                    socket = self.getSocketFor(sessionID, clientHost, clientPort)
                    if socket == None:
                        print "I screwed up somewhere cause i can't find this socket"
                    else:
                        clientIP = clientHost + ":" + str(clientPort)
                        serverJoineeIp = remoteIpToServerPortTable[clientIP]
                        del remoteIpToServerPortTable[clientIP]
                        #set the file size the host port is expecting
                        hostPort = clientIpToHostPort[clientIP]
                        del clientIpToHostPort[clientIP]
                        hostPortToFilesize[hostPort] = fileSize
                        
                        ipParts = serverJoineeIp.split(":")
                        ip = ipParts[0]
                        port = ipParts[1]
                        
                        returnState = {}
                        returnState['request'] = 'returnState'
                        returnState['sessionID'] = sessionID
                        returnState['clientHost'] = clientHost
                        returnState['clientPort'] = clientPort
                        returnState['ip'] = ip
                        returnState['port'] = port
                        returnState['length'] = fileSize
                        returnStateStr = json.dumps(returnState) + "\n"
                        socket.transport.write(returnStateStr)
                elif request == "ackReturnState":
                    #ok we now know both host and client know the file length
                    #we are not ready to open the two new channels for them
                    #to transfer and receive binary data
                    
                    #get the host, tell him to start sending data, cause
                    #in theory everyone should be connected ...
                    hostSocket = self.getHostForSession(sessionID)
                    startSendRequest = {}
                    startSendRequest['request'] = 'startSend'
                    startSendRequest['clientHost'] = ip
                    startSendRequest['clientPort'] = port
                    startSendRequestStr = json.dumps(startSendRequest) + "\n"
                    hostSocket.transport.write(startSendRequestStr)
                    print startSendRequestStr
                elif request == "joinComplete":
                    #i'm thinking this is unnecessary, on server side the socket
                    #seems to be closing ...
                    joinPort = obj['port']
                    clientIP = ip + ":" + str(port)
                    hostIp = remoteIpToServerPortTable[clientIP]
                    ipParts = hostIp.split(":")
                    hostAddr = ipParts[0]
                    hostPort = int(ipParts[1])
                    serverHostPort = int(hostToJoineeTable[hostPort])
                    socket = portToSocketTable[serverHostPort]
                    peerTransport = socket.transport
                    peerAddr = peerTransport.getPeer()
                    peerIp = peerAddr.host
                    peerPort = peerAddr.port
                    print peerIp + ":" + str(peerPort) + " is being closed!"        
                    socket.transport.loseConnection()
                    #also i need to remove the listener on joinPort
                    print "closing raw receiver socket"
                elif request == "sendComplete":
                    #remove close transport and the listener socket
                    print "closing raw sender socket"
                elif request == "leaveSession":
                    print ip + ":" + str(port) + " leaving session"
                    #remove self from the client list
                    #replace host if host is leaving
                    self.removeSelfFromSession()
                elif request == "startBulkSend":
                    bulkSenderAddr = self.createBulkSenderChannel()
                    bulkSenderPort = bulkSenderAddr.port
                    fileSize = obj['length']
                    portToSessionTable[bulkSenderPort] = self.mySession
                    hostPortToFilesize[bulkSenderPort] = fileSize
                    self.myState += "BULK_SENDER"
                    #notify sender which port to use for the bulk send
                    ackStartBulkSend = {}
                    ackStartBulkSend['request'] = 'ackStartBulkSend'
                    ackStartBulkSend['sessionID'] = sessionID
                    ackStartBulkSend['port'] = bulkSenderPort
                    ackStartBulkSendStr = json.dumps(ackStartBulkSend) + "\n"
                    self.transport.write(ackStartBulkSendStr)
        except ValueError, err:
            #print 'ERROR:', err
            print ".... json parse error ...."
            print s
            print ".... json parse error ...."
            self.buffer = self.buffer + s
    
    def getHostForSession(self, sessionID):
        clientList = sessionToClientsTable[sessionID]
        for client in clientList:
            if (client.myState.find('HOST') != -1):
                return client
    
    def getSocketFor(self, sessionID, ip, port):
        clientList = sessionToClientsTable[sessionID]
        for client in clientList:
            t = client.transport
            addr = t.getPeer()
            clientIp = addr.host
            clientPort = addr.port
            if clientIp == ip and clientPort == port:
                return client
        return None
    
    def createSenderChannel(self):
        factory = Factory()
        factory.protocol = RawDataSender
        listenPort = reactor.listenTCP(0, factory)
        testAddr = listenPort.getHost()
        testPort = testAddr.port
        print "created new send channel listening on " + str(testPort)
        listenPorts[testPort] = listenPort
        return testAddr
    
    def createReceiverChannel(self):
        factory = Factory()
        factory.protocol = RawDataReceiver
        listenPort = reactor.listenTCP(0, factory)
        testAddr = listenPort.getHost()
        testPort = testAddr.port
        listenPorts[testPort] = listenPort
        print "created new receive channel listening on " + str(testPort)
        return testAddr
    
    def createBulkSenderChannel(self):
        factory = Factory()
        factory.protocol = BulkDataSender
        listenPort = reactor.listenTCP(0, factory)
        testAddr = listenPort.getHost()
        testPort = testAddr.port
        print "created new send channel listening on " + str(testPort)
        listenPorts[testPort] = listenPort
        return testAddr
    
    def removeSelfFromSession(self):
        print "removing " + self.myRemoteIp + " from session: " + self.mySession
        #locate session list and remove self
        clientList = sessionToClientsTable[self.mySession]
        clientList.remove(self)
        #if self.myState == 'HOST' then get next client from session and deem
        #him the host
        if (self.myState == "HOST"):
            if (len(clientList) <= 0):
                #no more hosts, time to just end session then!
                print "deleting session: " + self.mySession
                del sessionToClientsTable[self.mySession]
            else:
                #need to locate a new host, picking first guy in clientList
                newHost = clientList[0]
                newHost.myState = "HOST"
                
    def connectionLost(self, reason):
        self.transport.loseConnection()
        if (self.isPolicyRequest):
            #ignore this guy if it was just a policy request from flex client!
            print self.myRemoteIp + " was a policy request made by flex, disconnecting now ..."
            return
        self.removeSelfFromSession()
        
    def connectToSession(self, sessionID):
        t = self.transport
        addr = t.getPeer()
        ip = addr.host
        port = addr.port
        if not sessionToClientsTable.has_key(sessionID):
            clientList = []
            sessionToClientsTable[sessionID] = clientList
            self.myState = 'HOST'
            clientList.append(self)
            print ip + ":" + str(port) + " started session = " + sessionID
            self.mySession = sessionID
        else:
            clientList = sessionToClientsTable[sessionID]
            clientList.append(self)
            print ip + ":" + str(port) + " joining session = " + sessionID
            self.mySession = sessionID
            
            hostSocket = self.getHostForSession(sessionID)
            #very rare case, if client becomes host (only 2 people, host d/c)
            if (hostSocket == self):
                return
            
            #TODO: i need to cache the two listening sockets somewhere
            #so i can close them later!! i'm gonna leave them open for
            #now but it's really not good!!
            serverHostAddr = self.createSenderChannel()
            serverHostIp = serverHostAddr.host
            serverHostPort = serverHostAddr.port
            serverJoineeAddr = self.createReceiverChannel()
            serverJoineeIp = serverJoineeAddr.host
            serverJoineePort = serverJoineeAddr.port
            #cache the server joinee address to inform client the new
            #socket to connect to
            clientIP = ip + ":" + str(port)
            remoteIpToServerPortTable[clientIP] = serverJoineeIp + ":" + str(serverJoineePort)
            clientIpToHostPort[clientIP] = serverHostPort
            #create mapping so i can remember which client to server
            hostToJoineeTable[serverJoineePort] = serverHostPort
            
            #locate the host for this session then send the state request to him
            host = self.getHostForSession(sessionID)
            getStateRequest = {}
            getStateRequest['request'] = 'getState'
            getStateRequest['sessionID'] = sessionID
            getStateRequest['clientHost'] = ip
            getStateRequest['clientPort'] = port
            getStateRequest['ip'] = serverHostIp
            getStateRequest['port'] = serverHostPort
            getStateRequestStr = json.dumps(getStateRequest) + "\n"
            host.transport.write(getStateRequestStr)
             
class RawDataSender(LineReceiver):
    
    senderIp = None;
    listeningPort = -1
    expectingAmount = -1
    amountSent = 0;
    
    def connectionMade(self):
        #super important setting to raw mode means data comes in raw
        self.setRawMode()
        t = self.transport
        addr = t.getPeer()
        ip = addr.host
        port = addr.port
        print ip + ":" + str(port) + " is a raw data sender connected to server ..."
        self.senderIp = ip + ":" + str(port)
        listenAddr = t.getHost()
        listenPort = listenAddr.port
        self.listeningPort = listenPort

    def rawDataReceived(self, data):
        #first locate port i am on
        t = self.transport
        addr = t.getHost()
        #ip = addr.host
        port = addr.port
        #set the expected amount now, cause it hasn't been set yet!
        if (self.expectingAmount == -1):
            self.expectingAmount = hostPortToFilesize[self.listeningPort]
        #portStr = str(port)
        #there should be a mapping in portToSocketTable with my port
        #which returns the client who is requesting data
        if not portToSocketTable[port]:
            print str(port) + " has no idea who to send data to !!!"
        else:
            #i've found who to send the data to so i'm just gonna
            #write whatever crap i have in data
            self.amountSent += len(data)
            #print str(self.amountSent) + " bytes sent to client"
            socket = portToSocketTable[port]
            socket.transport.write(data)
    
    def connectionLost(self, reason):
        #seems the server/host socket is gone by now ...
        print self.senderIp + " raw data sender has disconnected"
        self.transport.loseConnection()
        print str(self.listeningPort) + " is a listening port that should be closed!"
        listenPort = listenPorts[self.listeningPort]
        listenPort.stopListening()
        #if we sent less data than we should've then we need to d/c the receiver cause
        #at this point the receiver won't be getting anymore data from us for whatever reason!
        if (self.amountSent < self.expectingAmount):
            socket = portToSocketTable[self.listeningPort]
            socket.transport.loseConnection()
        #clean-up: removing host port to client socket mapping,
        #removing host port to file size mapping, removing host port to listen socket mapping
        del portToSocketTable[self.listeningPort]
        del hostPortToFilesize[self.listeningPort]
        del listenPorts[self.listeningPort]

class RawDataReceiver(LineReceiver):
    
    receiverIp = None
    listeningPort = -1
    
    def connectionMade(self):
        #super important setting to raw mode means data comes in raw
        self.setRawMode()
        t = self.transport
        addr = t.getHost()
        ip = addr.host
        port = addr.port
        self.listeningPort = port
        #todo: actually, shouldn't i just kill listen port here? we only expect
        #one person to connect to this right ...
        
        peerAddr = t.getPeer()
        peerIp = peerAddr.host
        peerPort = peerAddr.port
        print peerIp + ":" + str(peerPort) + " is a raw data receiver connected to server ..."
        self.receiverIp = peerIp + ":" + str(peerPort)
        #now becauses i'm the receiver, i need to make myself accessible so that
        #when the host is ready he can send to me
        myHost = hostToJoineeTable[port]
        del hostToJoineeTable[port]
        #myHost is the port the host for the session will send me data
        portToSocketTable[myHost] = self
        
    def connectionLost(self, reason):
        print self.receiverIp + " raw data receiver has disconnected"
        #t = self.transport
        #this defintely closes the connection between server and client
        #but i wonder, does this stop the host socket from listening???
        self.transport.loseConnection()
        #do i need to cache the IListeningPort and call stopListening?
        #YES, you need to close the listening socket here!!
        print str(self.listeningPort) + " is a listening port that should be closed!"
        listenPort = listenPorts[self.listeningPort]
        listenPort.stopListening()
        del listenPorts[self.listeningPort]
        
class BulkDataSender(LineReceiver):
    
    senderIp = None;
    listeningPort = -1
    expectingAmount = -1
    amountSent = 0;
    
    def connectionMade(self):
        #super important setting to raw mode means data comes in raw
        self.setRawMode()
        t = self.transport
        addr = t.getPeer()
        ip = addr.host
        port = addr.port
        print ip + ":" + str(port) + " is a bulk data sender connected to server ..."
        self.senderIp = ip + ":" + str(port)
        listenAddr = t.getHost()
        listenPort = listenAddr.port
        self.listeningPort = listenPort
        sessionID = portToSessionTable[listenPort]
        clients = sessionToClientsTable[sessionID]
        bulkReceiverAddr = self.createBulkReceiverChannel()
        bulkReceiverPort = bulkReceiverAddr.port
        fileSize = hostPortToFilesize[listenPort]
        bulkJoinRequest = self.createBulkJoinRequest(bulkReceiverPort, fileSize)
        portToSessionTable[bulkReceiverPort] = sessionID
        #this notifies everyone in the session to initiate a join bulk!
        for client in clients:
            if (client.myState.find('BULK_SENDER') == -1):
                client.transport.write(bulkJoinRequest)
                    
    def createBulkReceiverChannel(self):
        factory = Factory()
        factory.protocol = BulkDataReceiver
        listenPort = reactor.listenTCP(0, factory)
        testAddr = listenPort.getHost()
        testPort = testAddr.port
        listenPorts[testPort] = listenPort
        print "created new bulk receive channel listening on " + str(testPort)
        return testAddr
    
    def createBulkJoinRequest(self, port, fileSize):
        bulkJoinRequest = {}
        bulkJoinRequest['request'] = 'bulkJoin'
        bulkJoinRequest['port'] = port
        bulkJoinRequest['length'] = fileSize
        bulkJoinRequestStr = json.dumps(bulkJoinRequest) + "\n"
        return bulkJoinRequestStr
        
    def rawDataReceived(self, data):
        sessionID = portToSessionTable[self.listeningPort]
        clients = sessionToBulkReceiveTable[sessionID]
        for client in clients:
            client.transport.write(data)
        self.amountSent += len(data)
        
    def connectionLost(self, reason):
        #seems the server/host socket is gone by now ...
        print self.senderIp + " bulk data sender has disconnected"
        self.transport.loseConnection()
        print str(self.listeningPort) + " is a listening port that should be closed!"
        listenPort = listenPorts[self.listeningPort]
        listenPort.stopListening()
        #if we sent less data than we should've then we need to d/c the receiver cause
        #at this point the receiver won't be getting anymore data from us for whatever reason!
        if (self.amountSent < self.expectingAmount):
            clients = sessionToBulkReceiveTable[self.listeningPort]
            for client in clients:
                client.transport.loseConnection()
        sessionID = portToSessionTable[self.listeningPort]
        mainClients = sessionToClientsTable[sessionID]
        for mainClient in mainClients:
            if (mainClient.myState.find("BULK_SENDER") != -1):
                mainClient.myState = mainClient.myState.replace("BULK_SENDER", "")
                break
        #clean-up: removing host port to client socket mapping,
        #removing host port to file size mapping, removing host port to listen socket mapping
        del portToSessionTable[self.listeningPort]
        del hostPortToFilesize[self.listeningPort]
        del listenPorts[self.listeningPort]

class BulkDataReceiver(LineReceiver):
    
    receiverIp = None
    listeningPort = -1
    
    def connectionMade(self):
        #super important setting to raw mode means data comes in raw
        self.setRawMode()
        t = self.transport
        addr = t.getHost()
        ip = addr.host
        port = addr.port
        self.listeningPort = port
        peerAddr = t.getPeer()
        peerIp = peerAddr.host
        peerPort = peerAddr.port
        print peerIp + ":" + str(peerPort) + " is a bulk data receiver connected to server ..."
        self.receiverIp = peerIp + ":" + str(peerPort)
        #add self to bulk receiver list for session
        sessionID = portToSessionTable[self.listeningPort]
        clientList = None
        if not sessionToBulkReceiveTable.has_key(sessionID):
            clientList = []
            sessionToBulkReceiveTable[sessionID] = clientList
        else:
            clientList = sessionToBulkReceiveTable[sessionID]
        clientList.append(self)
        #check to see if all the bulk recever clients have arrived, if so
        #initiate the bulk send, otherwise just wait until everyone has joined
        numBulkReceiveClients = len(clientList)
        numSessionClients = len(sessionToClientsTable[sessionID])
        if (numBulkReceiveClients == numSessionClients-1):
            self.sendBulkData()
    
    def sendBulkData(self):
        #locate the bulk sender
        sessionID = portToSessionTable[self.listeningPort]
        clients = sessionToClientsTable[sessionID]
        sendBulkDataRequest = {}
        sendBulkDataRequest['request'] = 'sendBulkDataRequest'
        sendBulkDataRequestStr = json.dumps(sendBulkDataRequest) + "\n"
        for client in clients:
            if (client.myState.find("BULK_SENDER") != -1):
                #found him
                client.transport.write(sendBulkDataRequestStr)
                return
            
    def connectionLost(self, reason):
        print self.receiverIp + " bulk data receiver has disconnected"
        sessionID = portToSessionTable[self.listeningPort]
        clients = sessionToBulkReceiveTable[sessionID]
        for client in clients:
            if (client == self):
                clients.remove(self)
                break
        #issue here: if numBulkReceiveClients == 0 we should remove this entry from table!!
        if (len(clients) == 0):
            del sessionToBulkReceiveTable[sessionID]
            print str(self.listeningPort) + " is a listening port that should be closed!"
            listenPort = listenPorts[self.listeningPort]
            listenPort.stopListening()
            del listenPorts[self.listeningPort]
        self.transport.loseConnection()        
        #check to see whether all clients are here, now that someone left
        #issue here: how do you distinguish when the client d/c prematurely OR is d/c after everything went properly??
        '''
        numBulkReceiveClients = len(clients)
        numSessionClients = len(sessionToClientsTable[sessionID])
        if (numBulkReceiveClients == numSessionClients-1):
            self.sendBulkData()
        #this defintely closes the connection between server and client
        #but i wonder, does this stop the host socket from listening???
        #issue here: we need to close this listening port AFTER everyone is through with it, problem is right now
        #every d/c will atempt to close it even though it would be redundant!!
        print str(self.listeningPort) + " is a listening port that should be closed!"
        listenPort = listenPorts[self.listeningPort]
        listenPort.stopListening()
        del listenPorts[self.listeningPort]
        '''

factory = Factory()
factory.protocol = IphoneChat
reactor.listenTCP(8080, factory)

print "whiteboard server started"

reactor.run()